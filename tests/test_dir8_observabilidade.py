"""DIR8 (sentido-fase): observabilidade (contadores) + seed do operador (re-ancoragem)."""

import asyncio

from state import phase_metrics
from state.game import GameState
from server.message_handler import MessageHandler


def test_metrics_incr_and_snapshot():
    phase_metrics.reset()
    phase_metrics.incr("gap_recuperado_total", 3)
    phase_metrics.incr("phase_uncertain_total")
    phase_metrics.incr("direction_divergence_total")
    snap = phase_metrics.snapshot()
    assert snap["gap_recuperado_total"] == 3
    assert snap["phase_uncertain_total"] == 1
    assert snap["direction_divergence_total"] == 1
    phase_metrics.incr("inexistente")  # no-op silencioso
    assert "inexistente" not in phase_metrics.snapshot()
    phase_metrics.reset()


def test_sentido_block_includes_stats():
    phase_metrics.reset()
    phase_metrics.incr("gap_recuperado_total", 2)
    gs = GameState()
    gs.process_spin(10, "horario")
    out = gs.engine_overlay_fields()
    assert "stats" in out["sentido"]
    assert out["sentido"]["stats"]["gap_recuperado_total"] == 2
    phase_metrics.reset()


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, m):
        self.sent.append(m)


def test_set_seed_anchors_phase(monkeypatch):
    h = MessageHandler.__new__(MessageHandler)
    h.game_state = GameState()
    monkeypatch.setattr(h.game_state, "save", lambda *a, **k: None)  # não tocar state.json
    h.game_state.spin_seq = 5
    h.state_lock = asyncio.Lock()
    ws = _FakeWS()
    asyncio.run(h.handle_set_seed(ws, {"direction": "anti-horario", "locked": True}))
    assert h.game_state.seed_parity == "anti-horario"
    assert h.game_state.seed_n == 5
    assert h.game_state.direction_source == "operator_seed"
    assert h.game_state.direction_locked is True
    assert len(ws.sent) == 1
