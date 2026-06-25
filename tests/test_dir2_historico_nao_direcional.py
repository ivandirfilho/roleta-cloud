"""DIR2 (sentido-fase): o histórico inicial/correção deve ser NÃO-DIRECIONAL.

O histórico do DOM (12 últimos) não carrega o sentido real do giro — a extensão o
FABRICA por alternância retroativa. Alimentar timeline_cw/ccw com essa direção
inventada (via process_spin) envenena o motor SDA17. `register_history_number`
popula apenas o contexto (recent_results) e o último número, sem tocar timelines
nem last_direction.
"""

import os

from state.game import GameState
from app_config.settings import historico_nao_direcional_enabled


def test_register_history_number_is_nondirectional():
    gs = GameState()
    cw0 = gs.timeline_cw.to_dict()
    ccw0 = gs.timeline_ccw.to_dict()
    ld0 = gs.last_direction  # "" inicialmente

    gs.register_history_number(7)
    gs.register_history_number(13)

    # contexto (zona fria C3) populado, mais recente primeiro
    assert list(gs.recent_results)[:2] == [13, 7]
    assert gs.last_number == 13
    # timelines INTACTAS e last_direction NÃO fabricado
    assert gs.timeline_cw.to_dict() == cw0
    assert gs.timeline_ccw.to_dict() == ccw0
    assert gs.last_direction == ld0


def test_process_spin_does_feed_timeline_contrast():
    """Contraste: process_spin (fluxo ao vivo) realmente alimenta a timeline —
    é exatamente o que NÃO queremos para o histórico fabricado."""
    gs = GameState()
    gs.process_spin(7, "horario")   # 1º: sem força (sem last_direction anterior)
    gs.process_spin(13, "horario")  # alimenta timeline_cw
    assert gs.last_direction == "horario"
    assert gs.timeline_cw.to_dict() != GameState().timeline_cw.to_dict()


def test_flag_default_off():
    os.environ.pop("SDA_HISTORICO_NAO_DIRECIONAL", None)
    assert historico_nao_direcional_enabled() is False


def test_flag_on(monkeypatch):
    monkeypatch.setenv("SDA_HISTORICO_NAO_DIRECIONAL", "1")
    assert historico_nao_direcional_enabled() is True
    monkeypatch.setenv("SDA_HISTORICO_NAO_DIRECIONAL", "0")
    assert historico_nao_direcional_enabled() is False
