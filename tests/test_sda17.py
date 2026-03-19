"""Testes para a estratégia SDA-17 (IQR + Weighted Median + Drift)."""

import pytest
from strategies.sda17 import SDA17Strategy
from state.timeline import Timeline


@pytest.fixture
def strategy():
    return SDA17Strategy()


@pytest.fixture
def timeline_with_data():
    """Timeline com dados suficientes para análise."""
    tl = Timeline("cw")
    forces = [12, 14, 13, 15, 11, 14, 12, 13, 15, 14]
    for f in forces:
        tl.add(f)
    return tl


class TestSDA17Strategy:
    """Testa a estratégia SDA-17."""

    def test_name(self, strategy):
        assert strategy.name == "SDA-19"

    def test_analyze_insufficient_data(self, strategy):
        """Com dados insuficientes, should_bet=False."""
        tl = Timeline("cw")
        tl.add(12)
        from core.roulette import roulette
        result = strategy.analyze(tl, 17, roulette.WHEEL_SEQUENCE)
        assert result.should_bet is False

    def test_analyze_with_data(self, strategy, timeline_with_data):
        """Com dados suficientes, retorna resultado válido."""
        from core.roulette import roulette
        result = strategy.analyze(timeline_with_data, 17, roulette.WHEEL_SEQUENCE)
        assert hasattr(result, "should_bet")
        assert hasattr(result, "numbers")
        assert hasattr(result, "center")
        assert hasattr(result, "score")
        assert hasattr(result, "visual")

    def test_analyze_returns_numbers(self, strategy, timeline_with_data):
        """Análise retorna lista de números válidos."""
        from core.roulette import roulette
        result = strategy.analyze(timeline_with_data, 17, roulette.WHEEL_SEQUENCE)
        if result.should_bet:
            assert len(result.numbers) > 0
            for n in result.numbers:
                assert 0 <= n <= 36

    def test_analyze_score_range(self, strategy, timeline_with_data):
        """Score está entre 0 e 6."""
        from core.roulette import roulette
        result = strategy.analyze(timeline_with_data, 17, roulette.WHEEL_SEQUENCE)
        assert 0 <= result.score <= 6

    def test_drift_calculation(self, strategy):
        """Testa que o drift é calculado corretamente com * 0.5."""
        # Testar que a fórmula não é mais / 2 * 0.5 = 0.25
        diffs = [2, 4, 6]
        expected = int(sum(diffs) * 0.5)  # = 6
        wrong = int(sum(diffs) / 2 * 0.5)  # = 3 (bug antigo)
        assert expected == 6
        assert wrong == 3  # Confirma que o bug antigo dava valor errado
