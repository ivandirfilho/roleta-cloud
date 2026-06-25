"""DIR3 (sentido-fase): fundação — projeção pura de fase, round-trip do estado e flag.

O sentido é uma FASE alternada: fase(n) = seed_parity XOR ((n - seed_n) % 2).
"""

import tempfile
from pathlib import Path

from state.phase import project_phase, opposite, normalize, HORARIO, ANTI
from state.game import GameState
from app_config.settings import sentido_autoritativo_enabled


def test_project_phase_alternates():
    assert project_phase(HORARIO, 0, 0) == HORARIO
    assert project_phase(HORARIO, 0, 1) == ANTI
    assert project_phase(HORARIO, 0, 2) == HORARIO
    assert project_phase(HORARIO, 0, 3) == ANTI
    assert project_phase(ANTI, 5, 5) == ANTI
    assert project_phase(ANTI, 5, 6) == HORARIO
    assert project_phase(ANTI, 5, 10) == HORARIO  # delta=5 (ímpar) → oposto


def test_project_phase_fallback_invalid_seed():
    assert project_phase("", 0, 0) == HORARIO
    assert project_phase("lixo", 0, 1) == ANTI


def test_opposite_and_normalize():
    assert opposite(HORARIO) == ANTI
    assert opposite(ANTI) == HORARIO
    assert normalize("cw") == HORARIO
    assert normalize("ccw") == ANTI
    assert normalize("horario") == HORARIO


def test_gamestate_roundtrip_phase_fields():
    gs = GameState()
    gs.spin_seq = 7
    gs.seed_parity = ANTI
    gs.seed_n = 3
    gs.direction_source = "operator_seed"
    gs.direction_locked = True
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "state.json"
        gs.save(p)
        gs2 = GameState.load(p)
    assert gs2.spin_seq == 7
    assert gs2.seed_parity == ANTI
    assert gs2.seed_n == 3
    assert gs2.direction_source == "operator_seed"
    assert gs2.direction_locked is True


def test_reset_session_reancora_fase():
    gs = GameState()
    gs.spin_seq = 12
    gs.seed_parity = HORARIO
    gs.seed_n = 4
    gs.direction_locked = True
    gs.reset_session()
    assert gs.spin_seq == 0
    assert gs.seed_n == 0
    assert gs.direction_source == "reset"
    # paridade-semente e lock preservados (a roleta física segue alternando)
    assert gs.seed_parity == HORARIO
    assert gs.direction_locked is True


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("SDA_SENTIDO_AUTORITATIVO", raising=False)
    assert sentido_autoritativo_enabled() is False
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    assert sentido_autoritativo_enabled() is True
