"""DIR7 (sentido-fase): fusão de fontes de direção — estrutura STAND-BY p/ o vídeo.

O futuro serviço de vídeo publica um sinal de direção; a fusão por prioridade
(operator > vision > toggle) o acopla sem nenhuma outra mudança. Default OFF = inerte.
"""

import asyncio

from state.phase import fuse_direction, HORARIO, ANTI
from state.game import GameState
from server.message_handler import MessageHandler


def test_toggle_only_when_no_vision():
    d, src = fuse_direction(
        [{"source": "deterministic_toggle", "direction": HORARIO, "confidence": 1.0}], HORARIO
    )
    assert (d, src) == (HORARIO, "deterministic_toggle")


def test_vision_overrides_toggle_when_confident():
    d, src = fuse_direction(
        [
            {"source": "deterministic_toggle", "direction": HORARIO, "confidence": 1.0},
            {"source": "vision", "direction": ANTI, "confidence": 0.9},
        ],
        HORARIO, min_vision_conf=0.7,
    )
    assert (d, src) == (ANTI, "vision")


def test_vision_below_threshold_discarded():
    d, src = fuse_direction(
        [
            {"source": "deterministic_toggle", "direction": HORARIO, "confidence": 1.0},
            {"source": "vision", "direction": ANTI, "confidence": 0.5},
        ],
        HORARIO, min_vision_conf=0.7,
    )
    assert (d, src) == (HORARIO, "deterministic_toggle")


def test_operator_beats_vision():
    d, src = fuse_direction(
        [
            {"source": "vision", "direction": ANTI, "confidence": 0.99},
            {"source": "operator_seed", "direction": HORARIO, "confidence": 1.0},
        ],
        ANTI,
    )
    assert (d, src) == (HORARIO, "operator_seed")


def test_empty_signals_fallback_default():
    assert fuse_direction([], ANTI) == (ANTI, "deterministic_toggle")


def test_invalid_signal_ignored():
    d, src = fuse_direction([{"source": "vision", "direction": "lixo", "confidence": 0.9}], HORARIO)
    assert (d, src) == (HORARIO, "deterministic_toggle")


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, m):
        self.sent.append(m)


def test_direction_event_handler_stores_signal_standby():
    h = MessageHandler.__new__(MessageHandler)
    h.game_state = GameState()
    ws = _FakeWS()
    asyncio.run(h.handle_direction_event(ws, {"direction": "anti-horario", "confidence": 0.8}))
    ev = h.game_state.last_direction_event
    assert ev["source"] == "vision"
    assert ev["direction"] == "anti-horario"
    assert ev["confidence"] == 0.8
    assert len(ws.sent) == 1
