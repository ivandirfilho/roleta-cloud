"""SPR-V1 / DIR23 — FURO C+D: AUTORIDADE da âncora de fase.

Quatro buracos fechados aqui:

C1. `set_seed` sem o campo `locked` DESTRAVAVA a âncora do operador em silêncio
    (`bool(data.get("locked", False))`). Agora `locked` omitido PRESERVA o lock.
C2. Re-ancoragem de histórico saltava `spin_seq` para `count` e deixava `seed_n`
    velho — a paridade `(spin_seq - seed_n)` mudava e a fase autoritativa INVERTIA
    sem nada visível mudar. Agora a âncora do operador é REPROJETADA para o novo `n`.
C3. `set_seed`/`direction_event`/`nova_sessao` podiam vir de QUALQUER conexão
    (inclusive slave). Agora exigem role MASTER.
D.  `direction_event` (não autenticado) podia SOBREPOR a projeção determinística via
    fusão de vídeo. Fail-close: nenhum sinal 'vision' entra na fusão do giro enquanto
    não houver produtor autenticado (SPR-V7).

Mais o bloco `phase_authority` no overlay, pré-requisito do SPR-V2.
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from state.game import GameState
from state.phase import HORARIO, ANTI, project_phase


# ------------------------------------------------------------- _apply_seed (unit)

def test_apply_seed_define_ancora():
    gs = GameState()
    gs.spin_seq = 7
    assert gs._apply_seed(HORARIO, "operator_seed", locked=True) is True
    assert (gs.seed_parity, gs.seed_n) == (HORARIO, 7)
    assert gs.direction_source == "operator_seed"
    assert gs.direction_locked is True


def test_apply_seed_locked_none_preserva_lock():
    """C1: o coração do furo — omitir `locked` NÃO pode destravar."""
    gs = GameState()
    gs._apply_seed(HORARIO, "operator_seed", locked=True)
    gs._apply_seed(ANTI, "operator_seed", locked=None)
    assert gs.direction_locked is True
    assert gs.seed_parity == ANTI


def test_apply_seed_locked_false_destrava_explicitamente():
    gs = GameState()
    gs._apply_seed(HORARIO, "operator_seed", locked=True)
    gs._apply_seed(HORARIO, "operator_seed", locked=False)
    assert gs.direction_locked is False


def test_apply_seed_source_vazia_preserva_origem():
    gs = GameState()
    gs._apply_seed(HORARIO, "operator_seed")
    gs._apply_seed(ANTI, "")
    assert gs.direction_source == "operator_seed"


def test_apply_seed_direcao_vazia_limpa_ancora():
    """DIR17/DIR16 dependem disto: seed vazio força auto-seed no próximo alinhamento."""
    gs = GameState()
    gs.spin_seq = 5
    gs._apply_seed(HORARIO, "auto_seed")
    assert gs._apply_seed("", "", locked=None) is True
    assert gs.seed_parity == ""
    assert gs.seed_n == 5


def test_apply_seed_direcao_invalida_nao_grava_lixo():
    gs = GameState()
    gs._apply_seed("diagonal", "auto_seed")
    assert gs.seed_parity == ""


def test_apply_seed_vision_recusada_sob_lock():
    """D: a visão não usurpa uma âncora confirmada pelo operador."""
    gs = GameState()
    gs._apply_seed(HORARIO, "operator_seed", locked=True)
    assert gs._apply_seed(ANTI, "vision") is False
    assert gs.seed_parity == HORARIO
    assert gs.direction_source == "operator_seed"


def test_apply_seed_n_explicito():
    gs = GameState()
    gs.spin_seq = 30
    gs._apply_seed(HORARIO, "operator_seed", n=12)
    assert gs.seed_n == 12


def test_apply_seed_round_trip(tmp_path):
    """Campos escritos pelo caminho único sobrevivem ao restart."""
    gs = GameState()
    gs.spin_seq = 9
    gs._apply_seed(ANTI, "operator_seed", locked=True)
    p = tmp_path / "s.json"
    gs.save(p)
    gs2 = GameState.load(p)
    assert (gs2.seed_parity, gs2.seed_n) == (ANTI, 9)
    assert gs2.direction_source == "operator_seed"
    assert gs2.direction_locked is True


def test_reset_session_limpa_ancora_nao_travada(monkeypatch):
    monkeypatch.setenv("SDA_RESET_REANCORA", "1")
    gs = GameState()
    gs._apply_seed(HORARIO, "auto_seed", locked=False)
    gs.reset_session()
    assert gs.seed_parity == ""


# ------------------------------------------------------- phase_authority (overlay)

def test_phase_authority_presente_no_overlay():
    gs = GameState()
    gs.spin_seq = 6
    gs._apply_seed(HORARIO, "operator_seed", n=0)
    pa = gs.engine_overlay_fields()["phase_authority"]
    assert pa["spin_seq"] == 6
    assert pa["seed_parity"] == 0            # 0 = horario
    assert pa["seed_n"] == 0
    # spin_seq=6 é o índice do PRÓXIMO giro: (6-0) par ⇒ mesma paridade do seed.
    assert pa["direction"] == "cw"
    assert project_phase(HORARIO, 0, 6) == HORARIO


def test_phase_authority_alterna_com_spin_seq():
    gs = GameState()
    gs._apply_seed(HORARIO, "operator_seed", n=0)
    gs.spin_seq = 7
    assert gs.engine_overlay_fields()["phase_authority"]["direction"] == "ccw"


def test_phase_authority_null_sem_ancora():
    """Sem âncora válida não há autoridade a espelhar — publica null (não adivinha)."""
    gs = GameState()
    gs.seed_parity = ""
    pa = gs.engine_overlay_fields()["phase_authority"]
    assert pa["direction"] is None
    assert pa["seed_parity"] is None
    assert pa["seed_n"] is None


def test_phase_authority_enabled_reflete_flags(monkeypatch):
    gs = GameState()
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "0")
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "0")
    assert gs.engine_overlay_fields()["phase_authority"]["enabled"] is False
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "1")
    assert gs.engine_overlay_fields()["phase_authority"]["enabled"] is True


def test_phase_authority_e_serializavel():
    """Viaja em state_sync/sugestao/trace: precisa ser JSON puro."""
    gs = GameState()
    gs._apply_seed(ANTI, "operator_seed", n=0)
    json.dumps(gs.engine_overlay_fields()["phase_authority"])


# ------------------------------------------------------------- handler (E2E)

class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)

    def erros(self):
        return [json.loads(m) for m in self.sent if json.loads(m).get("type") == "error"]


@pytest.fixture()
def make_handler(tmp_path, monkeypatch):
    import database
    from app_config.settings import settings
    from strategies.sda17 import SDA17Strategy
    from server import message_handler as mh_mod
    from server.message_handler import MessageHandler

    database.init_database(str(tmp_path / "d.db"))
    monkeypatch.setattr(settings, "state_file", tmp_path / "state.json")
    monkeypatch.setattr(mh_mod.db_service, "save_decision", lambda d: 1)
    monkeypatch.setattr(
        mh_mod.connection_manager, "broadcast",
        MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0)),
    )

    def _factory(role="master"):
        monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: role)
        return MessageHandler(
            game_state=GameState(), strategy=SDA17Strategy(),
            state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"),
        )

    return _factory


@pytest.mark.parametrize("msg", [
    {"type": "set_seed", "direction": HORARIO},
    {"type": "direction_event", "direction": HORARIO, "confidence": 0.99},
    {"type": "nova_sessao"},
])
def test_role_gate_bloqueia_slave(make_handler, msg):
    """C3: escrever autoridade de fase é privilégio do MASTER."""
    h = make_handler(role="slave")
    ws = _FakeWS()
    asyncio.run(h.process_message(ws, json.dumps(msg), "c1"))
    erros = ws.erros()
    assert erros and erros[0]["code"] == "NOT_MASTER"
    assert h.game_state.seed_parity == ""
    assert getattr(h.game_state, "last_direction_event", None) is None


def test_master_ainda_pode_set_seed(make_handler):
    h = make_handler(role="master")
    ws = _FakeWS()
    asyncio.run(h.process_message(
        ws, json.dumps({"type": "set_seed", "direction": HORARIO, "locked": True}), "c1"))
    assert h.game_state.seed_parity == HORARIO
    assert h.game_state.direction_locked is True


def test_set_seed_sem_locked_preserva_lock(make_handler):
    """C1 end-to-end: o segundo `set_seed` (sem `locked`) não pode destravar."""
    h = make_handler(role="master")
    ws = _FakeWS()
    asyncio.run(h.process_message(
        ws, json.dumps({"type": "set_seed", "direction": HORARIO, "locked": True}), "c1"))
    asyncio.run(h.process_message(
        ws, json.dumps({"type": "set_seed", "direction": ANTI}), "c1"))
    assert h.game_state.direction_locked is True
    assert h.game_state.seed_parity == ANTI


def test_correcao_historico_preserva_fase_do_operador(make_handler, monkeypatch):
    """C2: a fase projetada para o PRÓXIMO giro tem de ser a mesma antes e depois da
    re-ancoragem quando a âncora é do operador."""
    monkeypatch.setenv("SDA_RESET_REANCORA", "1")
    h = make_handler(role="master")
    gs = h.game_state
    gs.spin_seq = 11
    gs._apply_seed(HORARIO, "operator_seed", locked=True, n=0)
    antes = project_phase(gs.seed_parity, gs.seed_n, gs.spin_seq)
    ws = _FakeWS()
    asyncio.run(h.process_message(ws, json.dumps({
        "type": "correcao_historico",
        "resultados": [{"numero": n, "direcao": HORARIO} for n in range(4)],
    }), "c1"))
    depois = project_phase(gs.seed_parity, gs.seed_n, gs.spin_seq)
    assert gs.spin_seq == 4
    assert depois == antes, "re-ancoragem inverteu a fase do operador em silencio"
    assert gs.direction_locked is True


def test_correcao_historico_sem_operador_mantem_legado(make_handler, monkeypatch):
    """Sem âncora do operador o DIR16 legado continua: zera o seed para auto-seed."""
    monkeypatch.setenv("SDA_RESET_REANCORA", "1")
    h = make_handler(role="master")
    gs = h.game_state
    gs.spin_seq = 11
    gs._apply_seed(HORARIO, "auto_seed", locked=False, n=0)
    ws = _FakeWS()
    asyncio.run(h.process_message(ws, json.dumps({
        "type": "correcao_historico",
        "resultados": [{"numero": n, "direcao": HORARIO} for n in range(3)],
    }), "c1"))
    assert gs.spin_seq == 3
    assert gs.seed_parity == ""


def test_vision_nao_sobrepoe_projecao_no_giro(make_handler, monkeypatch):
    """D (fail-close): mesmo com SDA_DIRECTION_VISION=1 e confidence máxima, um
    `direction_event` NÃO altera a direção autoritativa do giro."""
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_DIRECTION_VISION", "1")
    monkeypatch.setenv("SDA_DIRECTION_VISION_MIN_CONF", "0.1")
    monkeypatch.setenv("SDA_PHASE_RECONCILE", "1")
    h = make_handler(role="master")
    gs = h.game_state
    gs.spin_seq = 4
    gs._apply_seed(HORARIO, "auto_seed", n=0)
    ws = _FakeWS()
    asyncio.run(h.process_message(ws, json.dumps({
        "type": "direction_event", "direction": ANTI, "confidence": 1.0,
    }), "c1"))
    assert gs.last_direction_event is not None      # continua ARMAZENADO (SPR-V7)
    asyncio.run(h.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": 17, "direcao": HORARIO,
        "timestamp": 1, "trace_id": "vision-001", "allNumbers": [17],
    }), "c1"))
    # project_phase(horario, 0, 4) == horario ⇒ a visão (ANTI) não teve efeito.
    assert gs.last_direction == HORARIO
    assert gs.direction_source != "vision"


def test_direction_source_vision_obsoleta_e_normalizada(make_handler, monkeypatch):
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_PHASE_RECONCILE", "1")
    h = make_handler(role="master")
    gs = h.game_state
    gs.spin_seq = 4
    gs._apply_seed(HORARIO, "auto_seed", n=0)
    gs.direction_source = "vision"
    ws = _FakeWS()
    asyncio.run(h.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": 17, "direcao": HORARIO,
        "timestamp": 1, "trace_id": "vision-002", "allNumbers": [17],
    }), "c1"))
    assert gs.direction_source == "deterministic_toggle"
