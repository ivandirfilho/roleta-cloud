"""Testes para o estado do jogo (GameState, MartingaleState)."""

import pytest
import tempfile
import json
from pathlib import Path
from collections import deque

from state.game import GameState, MartingaleState


class TestMartingaleState:
    """Testa o sistema de Martingale inteligente."""

    def test_initial_state(self):
        mg = MartingaleState()
        assert mg.level == 1
        assert mg.window_count == 0
        assert mg.window_hits == 0

    def test_hit_increments(self):
        mg = MartingaleState()
        info = mg.update(True)
        assert mg.window_count == 1
        assert mg.window_hits == 1
        assert info["hit"] is True

    def test_miss_increments(self):
        mg = MartingaleState()
        info = mg.update(False)
        assert mg.window_count == 1
        assert mg.window_hits == 0
        assert info["hit"] is False

    def test_window_completes_after_5(self):
        mg = MartingaleState()
        for i in range(4):
            mg.update(False)
        info = mg.update(False)  # 5th play
        assert info.get("transition") is not None or mg.window_count == 0

    def test_to_dict_from_dict(self):
        mg = MartingaleState()
        mg.update(True)
        mg.update(False)
        d = mg.to_dict()
        mg2 = MartingaleState.from_dict(d)
        assert mg2.level == mg.level
        assert mg2.window_count == mg.window_count
        assert mg2.window_hits == mg.window_hits


class TestGameState:
    """Testa o estado do jogo."""

    def test_initial_state(self):
        gs = GameState()
        assert gs.last_number == 0
        assert gs.last_direction == ""
        assert len(gs.performance_sda17_cw) == 0

    def test_process_spin(self):
        gs = GameState()
        gs.process_spin(17, "horario")
        assert gs.last_number == 17
        assert gs.last_direction == "horario"

    def test_target_direction(self):
        gs = GameState()
        gs.process_spin(17, "horario")
        assert gs.target_direction == "anti-horario"
        gs.process_spin(5, "anti-horario")
        assert gs.target_direction == "horario"

    def test_performance_deque_maxlen(self):
        """Performance lists usam deque com maxlen=12."""
        gs = GameState()
        assert isinstance(gs.performance_sda17_cw, deque)
        assert gs.performance_sda17_cw.maxlen == 12

    def test_check_prediction_updates_performance(self):
        gs = GameState()
        gs.process_spin(17, "horario")
        gs.store_prediction([17, 32, 15], "anti-horario", 17, sda_centers=[17, 32, 15])
        hit = gs.check_prediction(17)
        assert hit is True
        assert len(gs.performance_sda17_ccw) == 1

    def test_check_prediction_miss(self):
        gs = GameState()
        gs.process_spin(17, "horario")
        gs.store_prediction([32, 15, 19], "anti-horario", 32, sda_centers=[32])
        hit = gs.check_prediction(5)
        assert hit is False

    def test_performance_capped_at_12(self):
        """Deque com maxlen=12 nunca excede."""
        gs = GameState()
        for i in range(20):
            gs.process_spin(i % 37, "horario")
            gs.store_prediction([i % 37], "anti-horario", i % 37, sda_centers=[i % 37])
            gs.check_prediction(i % 37)
        assert len(gs.performance_sda17_ccw) == 12

    def test_save_load_roundtrip(self):
        """Salvar e carregar preserva estado."""
        gs = GameState()
        gs.process_spin(17, "horario")
        gs.store_prediction([17, 32], "anti-horario", 17, sda_centers=[17, 32])
        gs.check_prediction(17)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = Path(f.name)

        try:
            gs.save(tmp_path)
            gs2 = GameState.load(tmp_path)
            assert gs2.last_number == 17
            assert gs2.last_direction == "horario"
            assert isinstance(gs2.performance_sda17_ccw, deque)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_reset_session(self):
        gs = GameState()
        gs.process_spin(17, "horario")
        gs.store_prediction([17], "anti-horario", 17, sda_centers=[17])
        gs.check_prediction(17)
        gs.reset_session()
        assert gs.last_number == 0
        assert len(gs.performance_sda17_cw) == 0
        assert isinstance(gs.performance_sda17_cw, deque)

    def test_get_performance_stats(self):
        gs = GameState()
        stats = gs.get_performance_stats()
        assert "sda17" in stats
        assert "bet" in stats
        assert "cw" in stats["sda17"]

    def test_store_prediction_with_centers(self):
        """SDA-21: store_prediction armazena lista de centros."""
        gs = GameState()
        gs.process_spin(17, "horario")
        gs.store_prediction([17, 32, 15, 19, 4], "anti-horario", 17, sda_centers=[17, 32, 15])
        assert gs.pending_prediction["center"] == 17
        assert gs.pending_prediction["centers"] == [17, 32, 15]

    def test_store_prediction_defaults_centers(self):
        """Sem sda_centers, deve usar [center] como fallback."""
        gs = GameState()
        gs.process_spin(17, "horario")
        gs.store_prediction([17, 32], "anti-horario", 17)
        assert gs.pending_prediction["centers"] == [17]
