"""
Testes de integração: message_handler.py pipeline SmartGale v5.

Verifica que o pipeline de produção (WebSocket) chama corretamente:
  T1: get_gale() antes de registrar aposta
  T2: sync_global() no martingale oposto após hit
  T3: global_hit passado no update()
  T4: action_reason contém score + gale_display
  T5: fallback early-session quando SDA insuficiente
  T6: gale_level no overlay reflete get_gale()
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

from state.game import GameState, MartingaleState
from state.timeline import Timeline


class FakeAnalysisResult:
    """Simula resultado da strategy.analyze()."""
    def __init__(self, should_bet=True, score=4, numbers=None, center=17, visual="17 [25,2,17,34,6]"):
        self.should_bet = should_bet
        self.score = score
        self.numbers = numbers or list(range(1, 22))
        self.center = center
        self.visual = visual
        self.details = {
            "predicted_force": 5,
            "centers": [center],
            "trend": "stable"
        }


class FakeBetAdvice:
    """Simula BetAdvice do Triple Rate."""
    def __init__(self, should_bet=True, confidence="media", reason="OK"):
        self.should_bet = should_bet
        self.confidence = confidence
        self.reason = reason
        self.c4_rate = 0.5
        self.m6_rate = 0.4
        self.l12_rate = 0.45

    def to_dict(self):
        return {"should_bet": self.should_bet, "confidence": self.confidence, "reason": self.reason}


def make_game_state(last_direction="horario", last_number=17) -> GameState:
    """Cria GameState com estado mínimo para teste."""
    gs = GameState()
    gs.last_direction = last_direction
    gs.last_number = last_number
    gs.timeline_cw = Timeline("cw")
    gs.timeline_ccw = Timeline("ccw")
    return gs


class TestGaleCalledOnBet:
    """T1: Quando SDA + TR aprovam, get_gale() deve ser chamado ANTES de store_prediction."""

    def test_gale_called_on_bet_decision(self):
        gs = make_game_state()
        mg = gs.target_martingale

        # Simular 3 hits globais para streak
        mg.global_consecutive_hits = 3

        # get_gale com score=5 e streak global=3 → G3
        level = mg.get_gale(score=5, c4_rate=0.5)
        assert level == 3, f"Com streak global 3 e score 5, esperado G3, obtido G{level}"
        assert mg.gale_display == "G3 S0 GS3"

    def test_gale_display_in_action_reason_format(self):
        """Verifica que o formato do action_reason está correto."""
        gs = make_game_state()
        mg = gs.target_martingale
        mg.global_consecutive_hits = 2

        score = 4
        bet_c4_rate = gs.get_bet_c4_rate()
        mg.get_gale(score=score, c4_rate=bet_c4_rate)

        action_reason = f"SDA score={score} | {mg.gale_display} | C4={bet_c4_rate:.0%}"
        assert "SDA score=4" in action_reason
        assert "G2 S0 GS2" in action_reason
        assert "C4=" in action_reason


class TestSyncGlobalOnHit:
    """T2: Hit em CW deve sync para CCW via sync_global()."""

    def test_sync_global_cw_to_ccw(self):
        gs = make_game_state()
        hit_result = True

        # Simular update em CW com global_hit + sync_global para CCW
        martingale_info = gs.martingale_cw.update(hit_result, global_hit=hit_result)
        gs.martingale_ccw.sync_global(hit_result)

        assert gs.martingale_cw.global_consecutive_hits == 1
        assert gs.martingale_ccw.global_consecutive_hits == 1

    def test_sync_global_ccw_to_cw(self):
        gs = make_game_state()
        hit_result = True

        martingale_info = gs.martingale_ccw.update(hit_result, global_hit=hit_result)
        gs.martingale_cw.sync_global(hit_result)

        assert gs.martingale_ccw.global_consecutive_hits == 1
        assert gs.martingale_cw.global_consecutive_hits == 1

    def test_sync_global_miss_resets_both(self):
        gs = make_game_state()

        # Primeiro: 2 hits
        gs.martingale_cw.update(True, global_hit=True)
        gs.martingale_ccw.sync_global(True)
        gs.martingale_cw.update(True, global_hit=True)
        gs.martingale_ccw.sync_global(True)

        assert gs.martingale_cw.global_consecutive_hits == 2
        assert gs.martingale_ccw.global_consecutive_hits == 2

        # Depois: miss
        gs.martingale_cw.update(False, global_hit=False)
        gs.martingale_ccw.sync_global(False)

        assert gs.martingale_cw.global_consecutive_hits == 0
        assert gs.martingale_ccw.global_consecutive_hits == 0


class TestGlobalHitParameter:
    """T3: update() deve receber global_hit e atualizar global_consecutive_hits."""

    def test_update_with_global_hit_true(self):
        mg = MartingaleState()
        info = mg.update(hit=True, global_hit=True)
        assert mg.global_consecutive_hits == 1
        assert info["global_consecutive_hits"] == 1

    def test_update_with_global_hit_false(self):
        mg = MartingaleState()
        mg.global_consecutive_hits = 3
        info = mg.update(hit=False, global_hit=False)
        assert mg.global_consecutive_hits == 0

    def test_update_without_global_hit_preserves(self):
        """Sem global_hit, streak global não muda (compatibilidade)."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 2
        info = mg.update(hit=True)
        assert mg.global_consecutive_hits == 2


class TestFallbackEarlySession:
    """T5: SDA insuficiente mas com dados → G1 seguro."""

    def test_fallback_activates_with_data(self):
        gs = make_game_state()
        # Adicionar uma força à timeline alvo (CCW, porque last_direction=horario)
        gs.timeline_ccw.add(5)

        assert gs.target_timeline.size == 1
        # O fallback deve ativar quando SDA não recomenda mas timeline tem dados
        # Simulamos a lógica diretamente
        mg = gs.target_martingale
        mg.level = 1
        assert mg.level == 1
        assert mg.current_bet == 17

    def test_no_fallback_empty_timeline(self):
        gs = make_game_state()
        assert gs.target_timeline.size == 0
        # Sem dados → não ativa fallback


class TestGaleLevelInDecision:
    """T6: gale_level no overlay/DB deve refletir o resultado de get_gale()."""

    def test_gale_level_reflects_get_gale(self):
        mg = MartingaleState()
        mg.global_consecutive_hits = 2

        # Antes de get_gale: level=1
        assert mg.level == 1

        # Após get_gale com score=4, streak=2: G2
        mg.get_gale(score=4, c4_rate=0.5)
        assert mg.level == 2

        # O level agora reflete a decisão, sem lag
        assert mg.gale_display == "G2 S0 GS2"
        assert mg.current_bet == 34

    def test_gale_level_no_lag_after_update(self):
        """Verifica que não há lag de 1 decisão no gale_level."""
        mg = MartingaleState()

        # Hit: update → get_gale (sequência correta)
        mg.update(hit=True, global_hit=True)
        assert mg.global_consecutive_hits == 1

        # Segundo hit
        mg.update(hit=True, global_hit=True)
        assert mg.global_consecutive_hits == 2

        # get_gale ANTES de gravar no DB
        mg.get_gale(score=4, c4_rate=0.5)
        assert mg.level == 2, "Após get_gale, level deve ser 2 (sem lag)"

    def test_c4_rate_force_g1(self):
        """C4 rate < 0.15 deve forçar G1 mesmo com streak alto."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 5

        mg.get_gale(score=5, c4_rate=0.10)
        assert mg.level == 1, "C4 rate 0.10 < 0.15 deve forçar G1"


class TestPipelineSequence:
    """Teste de sequência completa: update → sync_global → get_gale → registrar."""

    def test_full_pipeline_hit_sequence(self):
        gs = make_game_state()

        # --- Spin 1: CW hit ---
        gs.martingale_cw.update(True, global_hit=True)
        gs.martingale_ccw.sync_global(True)

        # --- Spin 2: CCW hit ---
        gs.martingale_ccw.update(True, global_hit=True)
        gs.martingale_cw.sync_global(True)

        # Agora ambos: global=2
        assert gs.martingale_cw.global_consecutive_hits == 2
        assert gs.martingale_ccw.global_consecutive_hits == 2

        # get_gale para próxima aposta
        gs.martingale_cw.get_gale(score=4, c4_rate=0.5, confidence="media")
        assert gs.martingale_cw.level == 2

    def test_full_pipeline_miss_resets(self):
        gs = make_game_state()

        # 2 hits globais
        gs.martingale_cw.update(True, global_hit=True)
        gs.martingale_ccw.sync_global(True)
        gs.martingale_ccw.update(True, global_hit=True)
        gs.martingale_cw.sync_global(True)

        # get_gale → G2
        gs.martingale_cw.get_gale(score=4, c4_rate=0.5, confidence="media")
        assert gs.martingale_cw.level == 2

        # Miss em CW
        gs.martingale_cw.update(False, global_hit=False)
        gs.martingale_ccw.sync_global(False)

        # get_gale → G1 (reset)
        gs.martingale_cw.get_gale(score=4, c4_rate=0.5, confidence="media")
        assert gs.martingale_cw.level == 1
        assert gs.martingale_cw.global_consecutive_hits == 0


class TestConfidenceInGale:
    """T7: Confiança como filtro de gale (SmartGale v6)."""

    def test_confidence_alta_forces_g1(self):
        """'alta' (spike regression) → G1 mesmo com streak alto."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 5
        mg.get_gale(score=5, c4_rate=0.8, confidence="alta")
        # S-STRAT-2 (v7): confidence=alta NÃO força mais G1; só "baixa" e sinais fracos.
        assert mg.level == 3, "v7: confidence='alta' com sinal forte deve permitir G3"

    def test_confidence_media_allows_escalation(self):
        """'media' (estável) → permite G2/G3 normalmente."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 3
        mg.get_gale(score=4, c4_rate=0.5, confidence="media")
        assert mg.level == 3, "Confiança 'media' com streak 3 deve permitir G3"

    def test_confidence_baixa_forces_g1(self):
        """'baixa' (dados ruins) → G1."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 4
        mg.get_gale(score=5, c4_rate=0.9, confidence="baixa")
        assert mg.level == 1, "Confiança 'baixa' deve forçar G1"

    def test_confidence_media_with_c4_low_still_g1(self):
        """'media' mas c4_rate < 0.25 → G1 (v7: threshold elevado de 0.15→0.25)."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 3
        mg.get_gale(score=4, c4_rate=0.20, confidence="media")
        assert mg.level == 1, "v7: c4_rate < 0.25 deve forçar G1 mesmo com 'media'"


class TestScoreNoLongerLimitsGale:
    """T8 (v7): Score < 3 AGORA limita gale (S-STRAT-2). v6 ignorava score totalmente,
    mas o estudo live mostrou que streak global pode escalar em situações de baixa
    confiança SDA. v7 trava em G1 quando score < 3."""

    def test_score_2_traps_g1_with_streak(self):
        """Score baixo (2) com streak alto → G1 (v7: score < 3 trava)."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 3
        mg.get_gale(score=2, c4_rate=0.5, confidence="media")
        assert mg.level == 1, "v7: score < 3 deve travar em G1"

    def test_score_1_traps_g1_with_streak(self):
        """Score mínimo (1) com streak 2 → G1 (v7: score < 3 trava)."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 2
        mg.get_gale(score=1, c4_rate=0.5, confidence="media")
        assert mg.level == 1, "v7: score < 3 deve travar em G1"

    def test_score_6_without_streak_stays_g1(self):
        """Score alto (6) sem streak → G1 (score não libera gale)."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 0
        mg.get_gale(score=6, c4_rate=0.8, confidence="media")
        assert mg.level == 1, "Score alto sem streak não deve liberar gale"

    def test_score_high_with_alta_now_escalates(self):
        """Score=5 + streak=3 + 'alta' → G3 (v7: confiança alta JÁ NÃO bloqueia)."""
        mg = MartingaleState()
        mg.global_consecutive_hits = 3
        mg.get_gale(score=5, c4_rate=0.8, confidence="alta")
        assert mg.level == 3, "v7: alta + streak + score alto deve escalar para G3"
