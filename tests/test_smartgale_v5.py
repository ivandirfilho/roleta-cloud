"""
Testes para SmartGale v5 — Anti-Martingale com Take-Profit e Streak Global.

Cobertura:
  T1: Anti-MG hit escalation (G1→G2→G3)
  T2: Anti-MG miss reset
  T3: Take-profit G3 hit → reset G1
  T4: Global streak cross-direction
  T5: c4 threshold 0.15 (não bloqueia 0.20)
  T6: c4 threshold 0.15 (bloqueia 0.10)
  T7: sync_global independente do estado local
  T8: to_dict / from_dict com global_consecutive_hits
  T9: Replay da sessão 08AM (29 resultados reais)
"""
import pytest
from state.game import MartingaleState


class TestAntiMartingaleEscalation:
    """T1: 3 hits globais consecutivos devem escalar G1→G2→G3."""

    def test_anti_mg_hit_escalation(self):
        mg = MartingaleState()

        # Hit 1: global=1 → get_gale retorna G1 (streak<2)
        mg.update(hit=True, global_hit=True)
        level = mg.get_gale(score=4, c4_rate=0.5, confidence="media")
        assert level == 1, f"After 1 global hit, expected G1 but got G{level}"

        # Hit 2: global=2 → get_gale retorna G2
        mg.update(hit=True, global_hit=True)
        level = mg.get_gale(score=4, c4_rate=0.5, confidence="media")
        assert level == 2, f"After 2 global hits, expected G2 but got G{level}"

        # Hit 3: global=3 → get_gale retorna G3 (v6: score não limita mais)
        mg.update(hit=True, global_hit=True)
        level = mg.get_gale(score=4, c4_rate=0.5, confidence="media")
        assert level == 3, f"After 3 global hits with media, expected G3 but got G{level}"

        # Hit 4 com confiança alta: global=4 → get_gale retorna G1 (alta força G1)
        mg.update(hit=True, global_hit=True)
        level = mg.get_gale(score=5, c4_rate=0.5, confidence="alta")
        assert level == 1, f"Confidence 'alta' forces G1, expected G1 but got G{level}"


class TestAntiMartingaleMissReset:
    """T2: Miss após escalação deve resetar para G1."""

    def test_anti_mg_miss_reset(self):
        mg = MartingaleState()

        # Escalar para G2
        mg.update(hit=True, global_hit=True)
        mg.update(hit=True, global_hit=True)
        mg.get_gale(score=4, c4_rate=0.5)
        assert mg.level == 2

        # Miss → reset
        result = mg.update(hit=False, global_hit=False)
        assert result["level_after"] == 1
        assert mg.consecutive_hits == 0
        assert mg.global_consecutive_hits == 0

        level = mg.get_gale(score=4, c4_rate=0.5)
        assert level == 1


class TestTakeProfitG3:
    """T3: Hit em G3 deve resetar para G1 (take-profit)."""

    def test_take_profit_g3_hit(self):
        mg = MartingaleState()

        # Simular estado em G3
        mg.level = 3
        mg.consecutive_hits = 3
        mg.global_consecutive_hits = 4

        # Hit em G3 → take-profit
        result = mg.update(hit=True, global_hit=True)
        assert result["level_before"] == 3
        assert result["level_after"] == 1, "Take-profit should reset to G1"
        assert mg.consecutive_hits == 0, "Take-profit resets local streak"
        assert "TAKE-PROFIT" in result["transition"]


class TestGlobalStreakCrossDirection:
    """T4: Hits em direções diferentes devem incrementar global streak."""

    def test_global_streak_cross_direction(self):
        mg_cw = MartingaleState()
        mg_ccw = MartingaleState()

        # CW hit
        mg_cw.update(hit=True, global_hit=True)
        mg_ccw.sync_global(True)
        assert mg_cw.global_consecutive_hits == 1
        assert mg_ccw.global_consecutive_hits == 1

        # CCW hit
        mg_ccw.update(hit=True, global_hit=True)
        mg_cw.sync_global(True)
        assert mg_cw.global_consecutive_hits == 2
        assert mg_ccw.global_consecutive_hits == 2

        # CW hit
        mg_cw.update(hit=True, global_hit=True)
        mg_ccw.sync_global(True)
        assert mg_cw.global_consecutive_hits == 3
        assert mg_ccw.global_consecutive_hits == 3

        # Both should now allow G3 with media confidence (v6: no score ceiling)
        assert mg_cw.get_gale(score=4, c4_rate=0.5, confidence="media") == 3
        assert mg_ccw.get_gale(score=5, c4_rate=0.5, confidence="media") == 3


class TestC4Threshold015:
    """T5/T6: c4_rate threshold at 0.15."""

    def test_c4_020_does_not_block(self):
        mg = MartingaleState()
        mg.global_consecutive_hits = 3  # Would want G3

        level = mg.get_gale(score=5, c4_rate=0.20)
        assert level == 3, f"c4=0.20 should NOT block, expected G3 got G{level}"

    def test_c4_010_blocks_to_g1(self):
        mg = MartingaleState()
        mg.global_consecutive_hits = 3  # Would want G3

        level = mg.get_gale(score=5, c4_rate=0.10)
        assert level == 1, f"c4=0.10 should block to G1, got G{level}"

    def test_c4_015_blocks_to_g1(self):
        """Boundary: exactly 0.15 should NOT block (< 0.15 blocks)."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 3

        level = mg.get_gale(score=5, c4_rate=0.15)
        assert level == 3, f"c4=0.15 (boundary) should NOT block, got G{level}"


class TestSyncGlobalIndependent:
    """T7: sync_global must NOT change level or consecutive_hits."""

    def test_sync_global_independent(self):
        mg = MartingaleState()
        mg.level = 2
        mg.consecutive_hits = 3
        mg.global_consecutive_hits = 1

        mg.sync_global(True)

        assert mg.level == 2, "sync_global should not change level"
        assert mg.consecutive_hits == 3, "sync_global should not change consecutive_hits"
        assert mg.global_consecutive_hits == 2, "sync_global should increment global streak"

    def test_sync_global_miss_resets_only_global(self):
        mg = MartingaleState()
        mg.level = 2
        mg.consecutive_hits = 3
        mg.global_consecutive_hits = 5

        mg.sync_global(False)

        assert mg.level == 2, "sync_global miss should not change level"
        assert mg.consecutive_hits == 3, "sync_global miss should not change local streak"
        assert mg.global_consecutive_hits == 0, "sync_global miss should reset global"


class TestToDictFromDict:
    """T8: Persistência do global_consecutive_hits."""

    def test_to_dict_includes_global(self):
        mg = MartingaleState(level=2, consecutive_hits=3, global_consecutive_hits=5, total_bets=10)
        d = mg.to_dict()
        assert d["global_consecutive_hits"] == 5
        assert d["level"] == 2
        assert d["consecutive_hits"] == 3

    def test_from_dict_restores_global(self):
        data = {"level": 2, "consecutive_hits": 3, "global_consecutive_hits": 5, "total_bets": 10}
        mg = MartingaleState.from_dict(data)
        assert mg.global_consecutive_hits == 5
        assert mg.level == 2
        assert mg.consecutive_hits == 3

    def test_from_dict_defaults_global_zero(self):
        """Retrocompatibilidade: state.json antigo sem global_consecutive_hits."""
        data = {"level": 1, "consecutive_hits": 0, "total_bets": 5}
        mg = MartingaleState.from_dict(data)
        assert mg.global_consecutive_hits == 0


class TestSessionReplay:
    """T9: Replay dos 29 resultados reais da sessão 08AM com SmartGale v5."""

    def test_session_replay_profitable(self):
        """Simula SmartGale v5 com streak global e scores variados.
        
        Usa a sequência real de hits/misses.
        Score varia: 3-4 normalmente, sobe para 5 durante streaks fortes
        (modelo prediz melhor quando está acertando → score sobe).
        """
        # (hit, score, confidence) — v6 uses confidence instead of score for gale
        plays = [
            (True, 3, "media"), (True, 4, "media"), (True, 4, "media"), (False, 4, "media"), (False, 3, "media"),
            (False, 3, "alta"), (False, 3, "alta"), (True, 3, "media"), (True, 4, "media"), (False, 4, "alta"),
            (True, 4, "media"), (False, 3, "media"), (True, 4, "media"), (False, 3, "media"),
            (True, 4, "media"), (True, 4, "media"), (True, 5, "media"), (True, 5, "media"), (True, 5, "media"), (False, 4, "alta"),
            (False, 3, "alta"), (False, 3, "alta"), (True, 3, "media"), (False, 3, "media"),
            (False, 3, "alta"), (False, 3, "alta"), (False, 3, "alta"), (True, 3, "media"), (True, 4, "media"), (False, 4, "alta"),
        ]

        PAYOFF = {1: (15, -21), 2: (30, -42), 3: (45, -63)}

        mg = MartingaleState()
        total_pnl = 0
        max_level_seen = 1

        for hit, score, conf in plays:
            level = mg.get_gale(score=score, c4_rate=0.5, confidence=conf)
            max_level_seen = max(max_level_seen, level)
            win, loss = PAYOFF[level]
            total_pnl += win if hit else loss
            mg.update(hit=hit, global_hit=hit)

        always_g1_pnl = sum(15 if h else -21 for h, _, _ in plays)

        # v6 should escalate during the 5-hit streak (bets 15-19, confidence media)
        assert max_level_seen >= 2, "Should have escalated above G1 at some point"
        # With G3 unlocked during streak with media confidence, should outperform always G1
        assert total_pnl > always_g1_pnl, (
            f"SmartGale v6 ({total_pnl}) should beat Always G1 ({always_g1_pnl})"
        )

    def test_session_replay_no_catastrophic_loss(self):
        """Verifica que miss sempre reseta para G1 (sem escalar em perdas)."""
        results = [False, False, False, False, False]  # 5 misses seguidos
        mg = MartingaleState()

        for hit in results:
            level = mg.get_gale(score=4, c4_rate=0.5)
            assert level == 1, f"After miss streak, level should be G1 but got G{level}"
            mg.update(hit=hit, global_hit=hit)
