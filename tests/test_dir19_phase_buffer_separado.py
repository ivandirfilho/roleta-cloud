"""DIR19 (sentido-fase): buffer dedicado para shift, janela 20 (fix #R).

Antes: phase_advance usava recent_results (maxlen=10) -> shift limitado a k<=10.

Depois: novo _phase_results (maxlen=20) SEPARADO. recent_results (zona fria C3,
SDA17) permanece intacto -> 8 testes existentes nao quebram.

phase_advance(max_window=20) ja preparado em state/phase.py.
"""

import tempfile
from pathlib import Path
from state.game import GameState
from state.phase import HORARIO, ANTI, phase_advance


def test_buffer_separado_inicial():
    """GameState ja nasce com _phase_results separado de recent_results."""
    gs = GameState()
    assert hasattr(gs, "_phase_results")
    assert gs._phase_results.maxlen == 20
    assert gs.recent_results.maxlen == 10
    # Separacao real:
    assert gs._phase_results is not gs.recent_results


def test_process_spin_alimenta_buffers_em_paralelo():
    """Ambos buffers crescem com cada giro, sem interferencia."""
    gs = GameState()
    for n in range(15):
        gs.process_spin(n, HORARIO if n % 2 == 0 else ANTI)
    assert len(gs.recent_results) == 10        # SDA17 zona fria preservada
    assert len(gs._phase_results) == 15        # buffer fase tem 15 (cabe ate 20)
    # Mais recente em [0] em ambos:
    assert gs.recent_results[0] == 14
    assert gs._phase_results[0] == 14


def test_register_history_alimenta_ambos():
    """Historico alimenta os dois buffers (sem direcao em _phase_results, so numero)."""
    gs = GameState()
    for n in [3, 7, 21, 5]:
        gs.register_history_number(n)
    assert list(gs.recent_results) == [5, 21, 7, 3]
    assert list(gs._phase_results) == [5, 21, 7, 3]


def test_phase_advance_aceita_janela_maior():
    """Com prev de 15 elementos, phase_advance recupera gap k=14 (limitado a max_window=20)."""
    prev = list(range(15))  # 0,1,2,...,14 (mais antigo = 14, mais recente = 0)
    new = [99, 98, 97, 96, 95, 94, 93, 92, 91, 90, 89, 88, 87, 86, 85, 0, 1, 2, 3, 4]
    # new[15..] = [0,1,2,3,4] casa com prev[0..4] = [0,1,2,3,4]
    gap, inter, uncertain = phase_advance(prev, new)
    assert uncertain is False
    assert gap == 14  # 15 novos - 1 normal = 14 perdidos


def test_roundtrip_phase_results_em_save_load():
    """_phase_results sobrevive a restart."""
    gs = GameState()
    for n in range(5):
        gs.process_spin(n, HORARIO)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "state.json"
        gs.save(p)
        gs2 = GameState.load(p)
    assert list(gs2._phase_results) == [4, 3, 2, 1, 0]
    assert gs2._phase_results.maxlen == 20


def test_reset_session_zera_phase_results():
    """reset_session zera _phase_results (novo dealer = nova historia de fase)."""
    gs = GameState()
    for n in range(8):
        gs.process_spin(n, HORARIO)
    assert len(gs._phase_results) == 8
    gs.reset_session()
    assert len(gs._phase_results) == 0
    assert gs._phase_results.maxlen == 20


def test_recent_results_NAO_alterado_pela_DIR19():
    """INV: SDA17 zona fria C3 segue maxlen=10. NUNCA mexer."""
    gs = GameState()
    assert gs.recent_results.maxlen == 10
    for n in range(25):
        gs.process_spin(n, HORARIO)
    assert len(gs.recent_results) == 10        # capou no 10
    assert list(gs.recent_results)[0] == 24    # mais recente


def test_fallback_phase_advance_se_phase_results_ausente():
    """Se load_state legado nao tem _phase_results, fallback usa recent_results."""
    # Simular GameState antigo (sem _phase_results)
    gs = GameState()
    delattr(gs, "_phase_results")
    # phase_advance ainda deve funcionar usando recent_results
    # (o fallback esta em message_handler.py:_prev_nums = ... or recent_results)
    assert not hasattr(gs, "_phase_results")
    # Simular o fallback do handler:
    _prev_nums = list(getattr(gs, "_phase_results", None) or gs.recent_results)
    assert _prev_nums == list(gs.recent_results)
