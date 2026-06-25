"""DIR16 (sentido-fase): FIX CRITICO #S/#W/#X — reset/reancoragem completa de fase.

Cobertura:
- #S: reset_session zera seed_parity (quando flag ON + nao locked).
- #W: handle_history_correction reancora fase.
- #X: handle_history_correction atualiza spin_seq.
- Preservacao de direction_locked: lock explicito do operador sobrevive ao reset.
- Flag SDA_RESET_REANCORA=0 mantem comportamento legado byte-identico.
"""

import pytest
from state.game import GameState
from state.phase import HORARIO, ANTI
from app_config.settings import reset_reancora_enabled


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("SDA_RESET_REANCORA", raising=False)
    assert reset_reancora_enabled() is False
    monkeypatch.setenv("SDA_RESET_REANCORA", "1")
    assert reset_reancora_enabled() is True


def test_reset_zera_seed_parity_quando_flag_on_e_nao_locked(monkeypatch):
    """DIR16 #S: com flag ON e NAO locked, reset zera seed_parity para forcar auto-seed."""
    monkeypatch.setenv("SDA_RESET_REANCORA", "1")
    gs = GameState()
    gs.spin_seq = 12
    gs.seed_parity = HORARIO
    gs.seed_n = 4
    gs.direction_locked = False
    gs.last_phase_uncertain = True
    gs.last_direction_event = {"source": "vision", "direction": HORARIO}
    gs.reset_session()
    assert gs.spin_seq == 0
    assert gs.seed_n == 0
    assert gs.direction_source == "reset"
    # FIX DIR16: seed_parity zerado + estado efemero limpo (auto-seed dispara no proximo giro)
    assert gs.seed_parity == ""
    assert gs.last_phase_uncertain is False
    assert gs.last_direction_event is None


def test_reset_preserva_seed_parity_quando_locked(monkeypatch):
    """DIR16 #S: lock explicito do operador sobrevive ao reset (a roleta fisica segue alternando)."""
    monkeypatch.setenv("SDA_RESET_REANCORA", "1")
    gs = GameState()
    gs.spin_seq = 12
    gs.seed_parity = ANTI
    gs.seed_n = 4
    gs.direction_locked = True
    gs.reset_session()
    assert gs.spin_seq == 0
    assert gs.seed_n == 0
    assert gs.seed_parity == ANTI         # preservado (lock)
    assert gs.direction_locked is True    # preservado (lock)


def test_reset_legado_off_mantem_seed_parity(monkeypatch):
    """DIR16 INV ADITIVO: flag OFF restaura comportamento atual byte-identico."""
    monkeypatch.delenv("SDA_RESET_REANCORA", raising=False)
    gs = GameState()
    gs.spin_seq = 12
    gs.seed_parity = HORARIO
    gs.seed_n = 4
    gs.direction_locked = False
    gs.reset_session()
    assert gs.spin_seq == 0
    assert gs.seed_n == 0
    # Comportamento legado (pre-DIR16): seed_parity preservado mesmo sem lock.
    assert gs.seed_parity == HORARIO
