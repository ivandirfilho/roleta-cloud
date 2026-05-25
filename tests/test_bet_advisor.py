"""Testes para o Triple Rate Advisor (Kill Switch)."""

import pytest
from state.bet_advisor import TripleRateAdvisor, BetAdvice


@pytest.fixture
def advisor():
    return TripleRateAdvisor()


class TestTripleRateAdvisor:
    """Testa o Kill Switch Advisor v2."""

    def test_empty_performance_should_bet(self, advisor):
        """Sem dados → apostar (dados insuficientes)."""
        advice = advisor.analyze([], sda_score=3)
        assert advice.should_bet is True
        assert advice.confidence == "media"

    def test_single_result_should_bet(self, advisor):
        """Um resultado → apostar (dados insuficientes)."""
        advice = advisor.analyze([True], sda_score=3)
        assert advice.should_bet is True

    def test_all_hits_should_bet(self, advisor):
        """100% acerto → apostar com alta confiança."""
        perf = [True] * 6
        advice = advisor.analyze(perf, sda_score=5)
        assert advice.should_bet is True
        assert advice.confidence == "alta"

    def test_kill_switch_activates(self, advisor):
        """v3 (S-STRAT-3): c4 < 30% + sda_score < 4 → KILL."""
        perf = [False, False, False, False]
        advice = advisor.analyze(perf, sda_score=2)
        assert advice.should_bet is False
        assert advice.confidence == "baixa"
        assert "KILL v3" in advice.reason

    def test_kill_switch_not_active_with_good_sda(self, advisor):
        """v3: c4=0% mas sda_score>=4 → apostar (sinal forte vence)."""
        perf = [False, False, False, False]
        advice = advisor.analyze(perf, sda_score=4)
        assert advice.should_bet is True

    def test_kill_switch_not_active_with_hits(self, advisor):
        """v3: 2/4 = 50% > 30% → apostar mesmo com sda baixo."""
        perf = [True, True, False, False]
        advice = advisor.analyze(perf, sda_score=1)
        assert advice.should_bet is True

    def test_kill_switch_v3_low_acc_low_score(self, advisor):
        """v3 novo: 1/4 = 25% < 30% + sda<4 → kill (cobre caso que v2 deixava passar)."""
        perf = [True, False, False, False]
        advice = advisor.analyze(perf, sda_score=3)
        assert advice.should_bet is False
        assert "KILL v3" in advice.reason

    def test_growing_trend_alta(self, advisor):
        """Tendência crescente → confiança alta."""
        perf = [True, True, True, False, False, True, False, False, False, False, False, False]
        advice = advisor.analyze(perf, sda_score=4)
        assert advice.should_bet is True

    def test_to_dict(self, advisor):
        """BetAdvice.to_dict() retorna formato correto."""
        advice = advisor.analyze([True, False, True], sda_score=4)
        d = advice.to_dict()
        assert "should_bet" in d
        assert "confidence" in d
        assert "rates" in d
        assert "c4" in d["rates"]

    def test_get_stats(self, advisor):
        """get_stats retorna estatísticas completas."""
        perf = [True, False, True, True]
        stats = advisor.get_stats(perf)
        assert "advice" in stats
        assert "stats" in stats
        assert stats["stats"]["total_results"] == 4
        assert stats["stats"]["total_hits"] == 3

    def test_calculate_rate_partial_window(self, advisor):
        """Taxa com janela parcial usa dados disponíveis."""
        rate = advisor._calculate_rate([True, True], 4)
        assert rate == 1.0  # 2/2

    def test_calculate_rate_full_window(self, advisor):
        """Taxa com janela completa usa apenas a janela."""
        rate = advisor._calculate_rate([True, False, True, False, True], 4)
        assert rate == 0.5  # 2/4 (primeiros 4)
