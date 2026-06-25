"""DIR5 (sentido-fase): publicar a fase autoritativa no canal existente.

O bloco `sentido` é injetado em engine_overlay_fields() → aparece no state_sync (1s)
e no trace, sem nenhuma mensagem WebSocket nova. O cliente sobrescreve sua paridade
com next_direction.
"""

from state.game import GameState


def test_engine_overlay_publishes_sentido_block():
    gs = GameState()
    gs.process_spin(10, "horario")   # last_direction=horario → target=anti-horario
    gs.spin_seq = 1
    gs.direction_source = "auto_seed"
    out = gs.engine_overlay_fields()
    assert "sentido" in out
    s = out["sentido"]
    assert s["last_direction"] == "horario"
    assert s["next_direction"] == "anti-horario"  # oposto do último
    assert s["last_seq"] == 1
    assert s["source"] == "auto_seed"
    assert s["locked"] is False


def test_sentido_next_is_target_direction():
    gs = GameState()
    gs.process_spin(5, "anti-horario")  # last=anti → target=horario
    out = gs.engine_overlay_fields()
    assert out["sentido"]["next_direction"] == "horario"
    assert out["sentido"]["next_direction"] == gs.target_direction
