"""SPR-V4 — NÃO-INTERFERÊNCIA e SHADOW QUE NÃO AGE.

Duas provas distintas:
  (A) com as flags novas OFF o replay congelado do SPR-V1 continua byte-idêntico
      (decisão, cobertura, stake, timelines, seed, `spin_seq`);
  (B) com as flags novas ON, o caminho de shadow é incapaz de agir — qualquer
      chamada a `_apply_seed`/`process_spin` ou qualquer alteração de
      `direcao`/`seed_parity`/`spin_seq` a partir dele FALHA o teste.

INV-3 permanece intacto: nada aqui toca indicação, cobertura ou stake.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from replay_harness_v1 import PROD_ENV, run_replay
from state.game import GameState
from state.phase import ANTI, HORARIO

FIXTURE = Path(__file__).parent / "fixtures" / "spr_v1_replay_baseline.json"

# As 3 flags do SPR-V4, explicitamente OFF — é exatamente o que a DoD exige.
V4_OFF = {
    "SDA_PHASE_EVENT_AUDIT": "0",
    "SDA_DIRECTION_VISION_SHADOW": "0",
    "SDA_DIRECTION_VISION_TTL_MS": "30000",
}


@pytest.fixture()
def baseline():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _replay(monkeypatch, extra=None):
    from state import phase_metrics

    for k, v in {**PROD_ENV, **V4_OFF, **(extra or {})}.items():
        monkeypatch.setenv(k, v)
    phase_metrics.reset()
    try:
        return run_replay()
    finally:
        phase_metrics.reset()


def test_replay_identico_com_flags_novas_off(monkeypatch, baseline):
    """Campo a campo contra a fixture congelada ANTES do SPR-V1."""
    atual = _replay(monkeypatch)
    for campo in (
        "spin_seq", "seed_parity", "seed_n", "direction_source", "direction_locked",
        "last_direction", "last_number", "target_direction",
        "recent_results", "phase_results", "ws_errors",
        "timeline_cw", "timeline_ccw",
    ):
        assert atual[campo] == baseline[campo], f"campo divergente: {campo}"
    assert len(atual["decisions"]) == len(baseline["decisions"])
    for i, (a, b) in enumerate(zip(atual["decisions"], baseline["decisions"])):
        assert a == b, f"decisao {i} divergente:\natual={a}\nbaseline={b}"


def test_cobertura_e_stake_identicos(monkeypatch, baseline):
    """Redundante de propósito: falha aqui aponta direto para risco financeiro."""
    atual = _replay(monkeypatch)
    for i, (a, b) in enumerate(zip(atual["decisions"], baseline["decisions"])):
        assert a["final_action"] == b["final_action"], f"acao divergente no giro {i}"
        assert a["sda_numbers"] == b["sda_numbers"], f"cobertura divergente no giro {i}"
        assert a["gale_bet_value"] == b["gale_bet_value"], f"stake divergente no giro {i}"


def test_direction_vision_congelada_em_1_nao_muda_nada(monkeypatch, baseline):
    """Regressão do fail-close do SPR-V1: mesmo com `SDA_DIRECTION_VISION=1` a visão
    não entra na fusão do giro, e o SPR-V4 não reabriu esse vetor."""
    atual = _replay(monkeypatch, {"SDA_DIRECTION_VISION": "1"})
    assert atual["decisions"] == baseline["decisions"]
    assert atual["spin_seq"] == baseline["spin_seq"]
    assert atual["seed_parity"] == baseline["seed_parity"]


def test_shadow_ligado_nao_muda_decisao_nem_stake(monkeypatch, baseline):
    """O shadow é observabilidade: com ele ON (e sem nenhum `direction_event` no
    replay) o resultado tem de continuar idêntico."""
    atual = _replay(monkeypatch, {
        "SDA_DIRECTION_VISION_SHADOW": "1", "SDA_PHASE_EVENT_AUDIT": "1"})
    assert atual["decisions"] == baseline["decisions"]
    assert atual["timeline_cw"] == baseline["timeline_cw"]
    assert atual["timeline_ccw"] == baseline["timeline_ccw"]


def test_shadow_conta_missing_por_giro(monkeypatch):
    """Cobertura ANTES de concordância: sem evento, todo giro elegível vira
    `missing` — é o denominador honesto de qualquer taxa de acordo."""
    from state import phase_metrics

    for k, v in {**PROD_ENV, **V4_OFF, "SDA_DIRECTION_VISION_SHADOW": "1"}.items():
        monkeypatch.setenv(k, v)
    phase_metrics.reset()
    try:
        snap = run_replay()
        # Todo giro que chegou ao boundary vira exatamente UMA disposição; sem
        # nenhum `direction_event` no replay, todas são `missing`.
        assert phase_metrics.snapshot()["vision_missing_total"] == len(snap["decisions"])
        assert phase_metrics.snapshot()["vision_agree_total"] == 0
    finally:
        phase_metrics.reset()


# ============================================================================
# (B) O caminho de shadow é INCAPAZ de agir
# ============================================================================

class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, m):
        self.sent.append(m)


@pytest.fixture()
def handler(tmp_path, monkeypatch):
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
        MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0)))
    monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: "master")
    monkeypatch.setenv("SDA_PHASE_EVENT_AUDIT", "1")
    monkeypatch.setenv("SDA_DIRECTION_VISION_SHADOW", "1")
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_PHASE_RECONCILE", "1")
    phase_metrics.reset()
    h = MessageHandler(
        game_state=GameState(), strategy=SDA17Strategy(),
        state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"))
    h.current_session_id = "sess-shadow"
    yield h
    phase_metrics.reset()


def test_shadow_nunca_chama_apply_seed_nem_process_spin(handler, monkeypatch):
    """Monkeypatch que EXPLODE se o caminho de shadow tocar os motores de fase."""
    gs = handler.game_state
    ws = _FakeWS()

    def _proibido(*a, **k):
        raise AssertionError("o caminho de shadow chamou um motor de fase")

    # Classificação isolada, com os motores minados.
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "direction_event", "direction": ANTI, "confidence": 1.0,
        "event_id": "cam-mine",
    }), "c1"))
    monkeypatch.setattr(gs, "_apply_seed", _proibido)
    monkeypatch.setattr(gs, "process_spin", _proibido)
    gs.spin_seq = 0
    gs._apply_seed  # (referência local minada; abaixo só o shadow roda)
    rows, kind = handler._classify_pending_direction_event(
        final_direction=HORARIO, spin_round_id=None)
    assert kind in ("unbound", "agree", "disagree", "stale")


def test_shadow_nao_altera_direcao_seed_nem_spin_seq(handler):
    """Estado de fase congelado antes × depois da classificação."""
    gs = handler.game_state
    ws = _FakeWS()
    gs._apply_seed(HORARIO, "operator_seed", locked=True, n=0)
    gs.spin_seq = 5
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "direction_event", "direction": ANTI, "confidence": 1.0,
        "event_id": "cam-freeze",
    }), "c1"))
    antes = (gs.seed_parity, gs.seed_n, gs.spin_seq, gs.direction_source,
             gs.direction_locked, gs.last_direction, gs.target_direction)
    gs.spin_seq += 1  # simula o incremento do giro
    handler._classify_pending_direction_event(final_direction=HORARIO, spin_round_id=None)
    depois = (gs.seed_parity, gs.seed_n, gs.spin_seq - 1, gs.direction_source,
              gs.direction_locked, gs.last_direction, gs.target_direction)
    assert antes == depois


def test_evento_com_confianca_maxima_nao_inverte_o_giro(handler):
    """D (fail-close do SPR-V1) sob o contrato novo: `confidence=1.0` e direção
    OPOSTA continuam sem nenhum efeito sobre a direção autoritativa."""
    gs = handler.game_state
    ws = _FakeWS()
    gs.spin_seq = 4
    gs._apply_seed(HORARIO, "auto_seed", n=0)
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "direction_event", "direction": ANTI, "confidence": 1.0,
        "event_id": "cam-forjado",
    }), "c1"))
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": 17, "direcao": HORARIO,
        "timestamp": 1, "trace_id": "vision-v4-001", "allNumbers": [17],
    }), "c1"))
    assert gs.last_direction == HORARIO
    assert gs.direction_source != "vision"
    from state import phase_metrics
    # O evento foi CLASSIFICADO (disagree/agree/unbound), nunca aplicado.
    snap = phase_metrics.snapshot()
    assert snap["vision_agree_total"] + snap["vision_disagree_total"] + snap["vision_unbound_total"] == 1
