"""SPR-V4 — contrato do `direction_event`: identidade, giro-alvo, prazo e one-shot.

O bug latente que este sprint fecha: `handle_direction_event` gravava o sinal SEM
TTL, SEM consumo único e SEM vínculo a giro. Como a mesa ALTERNA a cada giro, um
veredito CORRETO do giro N é a direção ERRADA do giro N+1 — um produtor que emitisse
uma vez e falhasse na seguinte travaria a direção autoritativa em ~50% de erro até um
reset. Aqui o evento é reconstruído do lado seguro: vira trilha de auditoria, NUNCA
direção.
"""

import asyncio
import json
import time
from unittest.mock import MagicMock

import pytest

from state.game import GameState
from state.phase import HORARIO, ANTI
from server.message_handler import classify_direction_event

TTL = 30000


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, m):
        self.sent.append(m)

    def acks(self):
        return [json.loads(m) for m in self.sent if json.loads(m).get("type") == "ack"]


@pytest.fixture()
def make_handler(tmp_path, monkeypatch):
    import database
    from app_config.settings import settings
    from strategies.sda17 import SDA17Strategy
    from server import message_handler as mh_mod
    from server.message_handler import MessageHandler
    from state import phase_metrics

    database.init_database(str(tmp_path / "d.db"))
    monkeypatch.setattr(settings, "state_file", tmp_path / "state.json")
    monkeypatch.setattr(
        mh_mod.connection_manager, "broadcast",
        MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0)),
    )
    monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: "master")
    phase_metrics.reset()

    def _factory():
        h = MessageHandler(
            game_state=GameState(), strategy=SDA17Strategy(),
            state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"),
        )
        h.current_session_id = "sess-v4"
        return h

    yield _factory
    phase_metrics.reset()


def _send_event(h, ws, **payload):
    data = {"type": "direction_event", "direction": ANTI, "confidence": 0.9}
    data.update(payload)
    asyncio.run(h.process_message(ws, json.dumps(data), "c1"))


# ---------------------------------------------------------------- identidade

def test_evento_sem_event_id_recebe_uuid_do_servidor(make_handler):
    """`event_id` ausente NUNCA rejeita o evento (a coluna é NOT NULL) — o servidor
    gera e registra a ORIGEM do id."""
    h, ws = make_handler(), _FakeWS()
    _send_event(h, ws)
    ev = h.game_state.pending_direction_event
    assert ev["event_id"] and ev["event_id"].startswith("srv-")
    assert ev["meta"]["event_id_origin"] == "server"
    assert ws.acks()[0]["event_id"] == ev["event_id"]


def test_event_id_do_cliente_e_preservado(make_handler):
    h, ws = make_handler(), _FakeWS()
    _send_event(h, ws, event_id="cam-42")
    ev = h.game_state.pending_direction_event
    assert ev["event_id"] == "cam-42"
    assert ev["meta"]["event_id_origin"] == "client"


# ------------------------------------------------------------------- alvo

def test_target_spin_seq_e_do_servidor_formula_fixa(make_handler):
    """`target_spin_seq = spin_seq_corrente + 1`: o evento descreve o giro que AINDA
    VAI ser processado (o `spin_seq` só incrementa quando o resultado é aceito)."""
    h, ws = make_handler(), _FakeWS()
    h.game_state.spin_seq = 7
    _send_event(h, ws)
    assert h.game_state.pending_direction_event["target_spin_seq"] == 8


def test_alvo_do_cliente_e_apenas_diagnostico(make_handler):
    """Um cliente defeituoso NÃO escolhe o alvo dele — senão bastaria mentir o campo
    para vincular o evento a qualquer giro."""
    h, ws = make_handler(), _FakeWS()
    h.game_state.spin_seq = 3
    _send_event(h, ws, target_spin_seq=999)
    ev = h.game_state.pending_direction_event
    assert ev["target_spin_seq"] == 4
    assert ev["meta"]["client_target_spin_seq"] == 999
    # E o binding continua valendo para o giro 4 (o valor errado não interferiu).
    kind, _ = classify_direction_event(
        ev, session_id="sess-v4", spin_seq=4, spin_round_id=None,
        final_direction=ANTI, now_mono=ev["received_at_mono"], ttl_ms=TTL)
    assert kind == "agree"


# -------------------------------------------------------------------- prazo

def _ev(**over):
    base = {
        "event_id": "e1", "direction": ANTI, "confidence": 0.9,
        "session_id": "s1", "round_id": None, "target_spin_seq": 5,
        "received_at_mono": 1000.0, "consumed": False, "self_contradict": False,
        "meta": {},
    }
    base.update(over)
    return base


@pytest.mark.parametrize("captured_at_ms", [0, 1, 10**13, 2 * 10**13])
def test_captured_at_ms_adulterado_nao_muda_classificacao(captured_at_ms):
    """O TTL é do RELÓGIO DO SERVIDOR. Se `captured_at_ms` entrasse na conta, um
    cliente com relógio adulterado renovaria o próprio prazo."""
    ev = _ev(meta={"captured_at_ms": captured_at_ms})
    kind, _ = classify_direction_event(
        ev, session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=ANTI, now_mono=1000.5, ttl_ms=TTL)
    assert kind == "agree"
    kind_velho, _ = classify_direction_event(
        ev, session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=ANTI, now_mono=1000.0 + 31, ttl_ms=TTL)
    assert kind_velho == "stale"


def test_ttl_e_intervalo_semiaberto():
    """Idade EXATAMENTE no limite já expira (`>=`): TTL é intervalo semiaberto."""
    ev = _ev()
    assert classify_direction_event(
        ev, session_id="s1", spin_seq=5, spin_round_id=None, final_direction=ANTI,
        now_mono=1000.0 + 29.999, ttl_ms=TTL)[0] == "agree"
    assert classify_direction_event(
        ev, session_id="s1", spin_seq=5, spin_round_id=None, final_direction=ANTI,
        now_mono=1000.0 + 30.0, ttl_ms=TTL)[0] == "stale"


def test_prazo_vence_antes_do_alvo_ser_avaliado():
    """Evento velho é `stale` mesmo com alvo/round corretos — o prazo é a primeira
    barreira, não um desempate."""
    ev = _ev()
    assert classify_direction_event(
        ev, session_id="s1", spin_seq=5, spin_round_id=None, final_direction=ANTI,
        now_mono=1e6, ttl_ms=TTL)[0] == "stale"


# ------------------------------------------------------- vínculo e one-shot

def test_alvo_divergente_nunca_vincula():
    """Gap de fase recuperado (o `spin_seq` saltou) ⇒ o giro descrito nunca chegou."""
    kind, motivo = classify_direction_event(
        _ev(target_spin_seq=5), session_id="s1", spin_seq=7, spin_round_id=None,
        final_direction=ANTI, now_mono=1000.1, ttl_ms=TTL)
    assert kind == "unbound" and "alvo" in motivo


def test_round_id_divergente_nunca_vincula():
    kind, _ = classify_direction_event(
        _ev(round_id="r-1"), session_id="s1", spin_seq=5, spin_round_id="r-2",
        final_direction=ANTI, now_mono=1000.1, ttl_ms=TTL)
    assert kind == "unbound"


def test_round_id_ausente_de_um_lado_nao_impede_binding():
    """O contrato exige coincidência só quando OS DOIS lados têm `round_id`."""
    assert classify_direction_event(
        _ev(round_id=None), session_id="s1", spin_seq=5, spin_round_id="r-9",
        final_direction=ANTI, now_mono=1000.1, ttl_ms=TTL)[0] == "agree"


def test_sessao_divergente_nunca_vincula():
    kind, _ = classify_direction_event(
        _ev(session_id="outra"), session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=ANTI, now_mono=1000.1, ttl_ms=TTL)
    assert kind == "unbound"


def test_evento_consumido_nao_e_reusado():
    kind, motivo = classify_direction_event(
        _ev(consumed=True), session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=ANTI, now_mono=1000.1, ttl_ms=TTL)
    assert kind == "unbound" and "one-shot" in motivo


def test_sem_evento_e_missing():
    assert classify_direction_event(
        None, session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=ANTI, now_mono=1.0, ttl_ms=TTL)[0] == "missing"


def test_evento_sem_direcao_utilizavel_e_unbound():
    assert classify_direction_event(
        _ev(direction=""), session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=ANTI, now_mono=1000.1, ttl_ms=TTL)[0] == "unbound"


def test_agree_e_disagree_pela_direcao_final():
    assert classify_direction_event(
        _ev(direction=ANTI), session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=ANTI, now_mono=1000.1, ttl_ms=TTL)[0] == "agree"
    assert classify_direction_event(
        _ev(direction=ANTI), session_id="s1", spin_seq=5, spin_round_id=None,
        final_direction=HORARIO, now_mono=1000.1, ttl_ms=TTL)[0] == "disagree"


# ------------------------------------------------------------------ restart

def test_evento_sobrevivente_a_restart_e_stale(make_handler, tmp_path):
    """`time.monotonic()` não sobrevive ao processo: um pendente reconstruído após
    restart JAMAIS volta a ser acionável (senão ganharia prazo de graça)."""
    h, ws = make_handler(), _FakeWS()
    _send_event(h, ws, event_id="cam-restart")
    h.game_state.save()

    novo = GameState.load()
    ev = novo.pending_direction_event
    assert ev["event_id"] == "cam-restart"
    assert "received_at_mono" not in ev and ev["mono_lost"] is True
    kind, motivo = classify_direction_event(
        ev, session_id="sess-v4", spin_seq=ev["target_spin_seq"], spin_round_id=None,
        final_direction=ev["direction"], now_mono=time.monotonic(), ttl_ms=TTL)
    assert kind == "stale" and "monotonic" in motivo


def test_round_trip_preserva_identidade_e_alvo(make_handler):
    h, ws = make_handler(), _FakeWS()
    h.game_state.spin_seq = 11
    _send_event(h, ws, event_id="cam-rt", round_id="r-77")
    h.game_state.save()
    novo = GameState.load()
    ev = novo.pending_direction_event
    assert (ev["event_id"], ev["target_spin_seq"], ev["round_id"]) == ("cam-rt", 12, "r-77")


# ------------------------------------------------------- retry / contradição

def test_retry_do_mesmo_evento_nao_renova_ttl_nem_remira(make_handler):
    """Reenviar o MESMO `event_id` não pode renovar o prazo nem mudar o alvo —
    seria uma renovação infinita à custa do produtor."""
    h, ws = make_handler(), _FakeWS()
    h.game_state.spin_seq = 2
    _send_event(h, ws, event_id="cam-1")
    ev1 = dict(h.game_state.pending_direction_event)
    h.game_state.spin_seq = 40  # o mundo andou entre os dois envios
    _send_event(h, ws, event_id="cam-1")
    ev2 = h.game_state.pending_direction_event
    assert ev2["received_at_mono"] == ev1["received_at_mono"]
    assert ev2["target_spin_seq"] == ev1["target_spin_seq"] == 3
    assert ev2["meta"]["retries"] == 1


def test_contradicao_do_produtor_e_sticky(make_handler):
    """Mesmo `event_id` reapresentado com direção diferente = produtor se
    contradizendo. A marca não pode ser apagada por um terceiro envio 'correto'."""
    h, ws = make_handler(), _FakeWS()
    _send_event(h, ws, event_id="cam-x", direction=ANTI)
    _send_event(h, ws, event_id="cam-x", direction=HORARIO)
    assert h.game_state.pending_direction_event["self_contradict"] is True
    _send_event(h, ws, event_id="cam-x", direction=ANTI)
    assert h.game_state.pending_direction_event["self_contradict"] is True
    kind, _ = classify_direction_event(
        h.game_state.pending_direction_event, session_id="sess-v4",
        spin_seq=h.game_state.pending_direction_event["target_spin_seq"],
        spin_round_id=None, final_direction=ANTI,
        now_mono=h.game_state.pending_direction_event["received_at_mono"], ttl_ms=TTL)
    assert kind == "selfcontradict"


def test_evento_novo_antes_do_giro_supersede_o_anterior(make_handler):
    """Dois ids diferentes antes do mesmo giro: o primeiro NUNCA poderá vincular.
    Ele é terminalizado como `unbound` em vez de sumir (senão fica um `received`
    órfão para sempre na trilha)."""
    from state import phase_metrics
    h, ws = make_handler(), _FakeWS()
    _send_event(h, ws, event_id="cam-a")
    _send_event(h, ws, event_id="cam-b")
    assert h.game_state.pending_direction_event["event_id"] == "cam-b"
    # O contador `vision_unbound_total` NÃO sobe: ele particiona os giros ELEGÍVEIS
    # (denominador de `roleta_vision_coverage_ratio`), e um frame extra do produtor
    # não é um giro — contá-lo derrubaria a cobertura artificialmente. O volume de
    # ingressos já aparece em `vision_event_total`.
    snap = phase_metrics.snapshot()
    assert snap["vision_unbound_total"] == 0
    assert snap["vision_event_total"] == 2


# ------------------------------------------------------------------ sessão

def test_nova_sessao_invalida_evento_pendente(make_handler):
    h, ws = make_handler(), _FakeWS()
    _send_event(h, ws, event_id="cam-sess")
    assert h.game_state.pending_direction_event is not None
    asyncio.run(h.process_message(ws, json.dumps({"type": "nova_sessao"}), "c1"))
    assert h.game_state.pending_direction_event is None


def test_slave_nao_ingressa_evento(make_handler, monkeypatch):
    """Role-gate do SPR-V1 continua valendo para o contrato novo."""
    from server import message_handler as mh_mod
    h, ws = make_handler(), _FakeWS()
    monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: "slave")
    _send_event(h, ws, event_id="cam-slave")
    assert h.game_state.pending_direction_event is None
