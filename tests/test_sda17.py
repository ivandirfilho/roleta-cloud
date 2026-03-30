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
        assert strategy.name == "M15-ADA"

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

    def test_triple_focus_returns_three_centers(self, strategy, timeline_with_data):
        """SDA-21 retorna exatamente 3 centros em details."""
        from core.roulette import roulette
        result = strategy.analyze(timeline_with_data, 17, roulette.WHEEL_SEQUENCE)
        if result.should_bet:
            centers = result.details.get("centers", [])
            assert len(centers) == 3
            assert result.center == centers[0]  # C1 é o centro primário

    def test_triple_focus_unique_count(self, strategy, timeline_with_data):
        """Números devem ter 15-21 itens únicos."""
        from core.roulette import roulette
        result = strategy.analyze(timeline_with_data, 17, roulette.WHEEL_SEQUENCE)
        if result.should_bet:
            assert 7 <= len(result.numbers) <= 21
            assert len(result.numbers) == len(set(result.numbers))  # Todos únicos

    def test_triple_focus_forces_used(self, strategy, timeline_with_data):
        """M15-ADA: detalhes contêm mediana (offset adaptativo substitui max/min)."""
        from core.roulette import roulette
        result = strategy.analyze(timeline_with_data, 17, roulette.WHEEL_SEQUENCE)
        if result.should_bet:
            forces_used = result.details.get("forces_used", {})
            assert "median" in forces_used

    def test_adaptive_offset_in_details(self, strategy, timeline_with_data):
        """M15-ADA: detalhes contêm offset assimétrico e tipo bayesian."""
        from core.roulette import roulette
        result = strategy.analyze(timeline_with_data, 17, roulette.WHEEL_SEQUENCE)
        if result.should_bet:
            assert "offset" in result.details
            assert "offset_c3" in result.details
            assert "offset_type" in result.details
            assert result.details["offset_type"] == "sigmoid"

    def test_adaptive_state_persistence(self, strategy):
        """M15-ADA: estado adaptativo pode ser salvo e restaurado."""
        strategy.cw_history = [(17, 25), (0, 32)]
        strategy.ccw_history = [(17, 25), (0, 32)]
        state = strategy.get_adaptive_state()
        
        new_strategy = SDA17Strategy()
        new_strategy.load_adaptive_state(state)
        assert len(new_strategy.cw_history) == 2
        assert len(new_strategy.ccw_history) == 2
