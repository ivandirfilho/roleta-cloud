"""Testes para o estado do jogo (GameState, MartingaleState / Smart Gale v4)."""

import pytest
import tempfile
import json
from pathlib import Path
from collections import deque

from state.game import GameState, MartingaleState


class TestSmartGaleV4:
    """Testa o Smart Gale v4 (Hybrid Score-Streak)."""

    def test_initial_state(self):
        mg = MartingaleState()
        assert mg.level == 1
        assert mg.consecutive_hits == 0
        assert mg.total_bets == 0
        assert mg.current_bet == 21

    def test_hit_increments_streak(self):
        mg = MartingaleState()
        info = mg.update(True)
        assert mg.consecutive_hits == 1
        assert info["hit"] is True
        assert mg.total_bets == 1

    def test_miss_resets_streak(self):
        mg = MartingaleState()
        mg.update(True)
        mg.update(True)
        assert mg.consecutive_hits == 2
        info = mg.update(False)
        assert mg.consecutive_hits == 0
        assert mg.level == 1
        assert info["hit"] is False

    def test_miss_resets_to_g1(self):
        mg = MartingaleState()
        mg.level = 3
        mg.consecutive_hits = 3
        mg.update(False)
        assert mg.level == 1
        assert mg.consecutive_hits == 0

    def test_get_gale_score_ceiling(self):
        mg = MartingaleState()
        mg.global_consecutive_hits = 5  # wants to raise via global streak
        assert mg.get_gale(score=1) == 1  # ceiling 1 for low score
        assert mg.get_gale(score=3) == 2  # ceiling 2 for mid score
        assert mg.get_gale(score=5) == 3  # ceiling 3 for high score

    def test_get_gale_c4_rate_override(self):
        mg = MartingaleState()
        mg.global_consecutive_hits = 5
        assert mg.get_gale(score=6, c4_rate=0.10) == 1  # c4_rate < 15% forces ceiling 1

    def test_get_gale_streak_raises(self):
        mg = MartingaleState()
        mg.level = 1
        mg.global_consecutive_hits = 3  # global streak >= 3 → G3
        result = mg.get_gale(score=5, c4_rate=0.5)
        assert result == 3  # raised to 3 via global streak

    def test_bet_values(self):
        mg = MartingaleState()
        mg.level = 1
        assert mg.current_bet == 21
        mg.level = 2
        assert mg.current_bet == 42
        mg.level = 3
        assert mg.current_bet == 63

    def test_multiplier_display(self):
        mg = MartingaleState()
        assert mg.multiplier == "1x"
        mg.level = 2
        assert mg.multiplier == "2x"
        mg.level = 3
        assert mg.multiplier == "3x"

    def test_gale_display(self):
        mg = MartingaleState()
        assert mg.gale_display == "G1 S0 GS0"
        mg.update(True, global_hit=True)
        assert mg.gale_display == "G1 S1 GS1"

    def test_to_dict_from_dict(self):
        mg = MartingaleState()
        mg.update(True)
        mg.update(True)
        d = mg.to_dict()
        mg2 = MartingaleState.from_dict(d)
        assert mg2.level == mg.level
        assert mg2.consecutive_hits == mg.consecutive_hits
        assert mg2.total_bets == mg.total_bets

    def test_from_dict_migration(self):
        """Legacy data with window_count/total_stops migrates gracefully."""
        old_data = {"level": 2, "window_count": 3, "total_stops": 1}
        mg = MartingaleState.from_dict(old_data)
        assert mg.level == 2
        assert mg.total_bets == 8  # 3 + 1*5

    def test_transition_message_on_streak(self):
        mg = MartingaleState()
        mg.update(True, global_hit=True)
        info = mg.update(True, global_hit=True)
        assert info.get("transition") is not None
        assert "STREAK" in info["transition"]

    def test_transition_message_on_reset(self):
        mg = MartingaleState()
        mg.level = 2
        mg.consecutive_hits = 2
        info = mg.update(False)
        assert "RESET" in info["transition"]

    def test_always_returns_valid_gale(self):
        """get_gale always returns 1, 2, or 3."""
        mg = MartingaleState()
        for score in range(0, 8):
            for c4 in [0.0, 0.1, 0.24, 0.25, 0.5, 1.0]:
                for streak in range(0, 5):
                    mg.consecutive_hits = streak
                    result = mg.get_gale(score=score, c4_rate=c4)
                    assert result in (1, 2, 3), f"Invalid gale {result} for score={score}, c4={c4}, streak={streak}"


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
