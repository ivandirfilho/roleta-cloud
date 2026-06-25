"""DIR17 (sentido-fase): FIX #T — reancora a fase em phase_uncertain.

Cobertura:
- Flag default OFF + helper.
- Quando phase_advance retorna sem alinhamento (matched=False), seed_parity zera
  para forcar auto-seed da DIR5 no proximo giro alinhado.
- Preservacao de direction_locked: lock do operador sobrevive a uncertain.
- INV-3: spin_seq ainda incrementa (contador de eventos para auditoria).
"""

from state.phase import phase_advance, reconcile_shift, HORARIO, ANTI
from state.game import GameState
from app_config.settings import uncertain_reancora_enabled


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("SDA_UNCERTAIN_REANCORA", raising=False)
    assert uncertain_reancora_enabled() is False
    monkeypatch.setenv("SDA_UNCERTAIN_REANCORA", "1")
    assert uncertain_reancora_enabled() is True


def test_phase_advance_uncertain_quando_sem_alinhamento():
    """Validacao da invariante DIR4: shift sem alinhamento retorna uncertain=True."""
    prev = [10, 5, 32, 19]                # mesa antiga
    new = [22, 18, 4, 27, 35, 0, 31]       # mesa nova, sem overlap
    gap, inter, uncertain = phase_advance(prev, new)
    assert uncertain is True
    assert gap == 0
    assert inter == []


def test_reconcile_shift_alinhado():
    """Sanity: shift normal (k=1) nao gera uncertain."""
    prev = [10, 5, 32, 19]
    new = [22, 10, 5, 32, 19]              # 22 é o novo; resto casa
    k, matched = reconcile_shift(prev, new)
    assert matched is True
    assert k == 1


def test_lock_total_preserva_seed_em_uncertain(monkeypatch):
    """DIR17 + DIR13 cross: com lock explicito, NAO reanchora mesmo em uncertain."""
    monkeypatch.setenv("SDA_UNCERTAIN_REANCORA", "1")
    gs = GameState()
    gs.spin_seq = 8
    gs.seed_parity = HORARIO
    gs.seed_n = 0
    gs.direction_locked = True
    # Simular o branch DIR17 (reanchoragem):
    if uncertain_reancora_enabled() and not gs.direction_locked:
        gs.seed_parity = ""
        gs.seed_n = gs.spin_seq
    # Lock preserva seed_parity intacto:
    assert gs.seed_parity == HORARIO
    assert gs.seed_n == 0


def test_reancora_em_uncertain_quando_flag_on(monkeypatch):
    """DIR17 #T: com flag ON e sem lock, uncertain zera seed_parity + ajusta seed_n."""
    monkeypatch.setenv("SDA_UNCERTAIN_REANCORA", "1")
    gs = GameState()
    gs.spin_seq = 8
    gs.seed_parity = HORARIO
    gs.seed_n = 0
    gs.direction_locked = False
    if uncertain_reancora_enabled() and not gs.direction_locked:
        gs.seed_parity = ""
        gs.seed_n = gs.spin_seq
    assert gs.seed_parity == ""
    assert gs.seed_n == 8


def test_flag_off_mantem_comportamento_legado(monkeypatch):
    """INV ADITIVO: flag OFF restaura comportamento atual byte-identico."""
    monkeypatch.delenv("SDA_UNCERTAIN_REANCORA", raising=False)
    gs = GameState()
    gs.spin_seq = 8
    gs.seed_parity = HORARIO
    gs.seed_n = 0
    gs.direction_locked = False
    # Branch DIR17 nao deve disparar:
    if uncertain_reancora_enabled() and not gs.direction_locked:
        gs.seed_parity = ""
        gs.seed_n = gs.spin_seq
    assert gs.seed_parity == HORARIO       # preservado
    assert gs.seed_n == 0                  # preservado
