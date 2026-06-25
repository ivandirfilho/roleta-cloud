"""DIR6 (sentido-fase): idempotência por trace_id + resync_advised no bloco sentido."""

from server.message_handler import MessageHandler


def _fresh_handler():
    # MessageHandler usa estado de instância para o dedup; basta um objeto cru.
    h = MessageHandler.__new__(MessageHandler)
    return h


def test_is_duplicate_trace_detects_repeat():
    h = _fresh_handler()
    assert h._is_duplicate_trace("abc-1") is False  # primeira vez
    assert h._is_duplicate_trace("abc-2") is False
    assert h._is_duplicate_trace("abc-1") is True   # reenvio do mesmo trace_id
    assert h._is_duplicate_trace("abc-2") is True


def test_trace_window_evicts_old():
    h = _fresh_handler()
    for i in range(70):  # janela é 64 → os primeiros saem
        h._is_duplicate_trace(f"t-{i}")
    # t-0 já foi descartado pela janela → não é mais "duplicado"
    assert h._is_duplicate_trace("t-0") is False
    # um recente continua detectado
    assert h._is_duplicate_trace("t-69") is True


def test_sentido_block_has_resync_advised():
    from state.game import GameState
    gs = GameState()
    gs.process_spin(10, "horario")
    gs.last_phase_uncertain = True
    out = gs.engine_overlay_fields()
    assert out["sentido"]["resync_advised"] is True
    gs.last_phase_uncertain = False
    assert gs.engine_overlay_fields()["sentido"]["resync_advised"] is False
