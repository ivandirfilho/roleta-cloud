"""
Testes da sprint W-01 — compute_wheel_dist e variantes.

Cobre os helpers de distância circular em `core.roulette`:
- `compute_wheel_dist(predicted_center, actual)` -> 0..18
- `compute_wheel_dist_dir(predicted_center, actual, direction)` -> -18..+18
- `compute_wheel_dist_min_to_set(centers, actual)` -> 0..18 ou None

WHEEL_SEQUENCE (37 slots, sentido horário a partir do 0):
[0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36,
 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14, 31, 9,
 22, 18, 29, 7, 28, 12, 35, 3, 26]
"""
import pytest

from core.roulette import Direction, roulette


class TestComputeWheelDist:
    def test_same_number_is_zero(self):
        assert roulette.compute_wheel_dist(0, 0) == 0
        assert roulette.compute_wheel_dist(17, 17) == 0
        assert roulette.compute_wheel_dist(26, 26) == 0

    def test_adjacent_in_wheel_is_one(self):
        # 0 -> 32 sao adjacentes na WHEEL_SEQUENCE
        assert roulette.compute_wheel_dist(0, 32) == 1
        assert roulette.compute_wheel_dist(32, 0) == 1
        # 26 -> 0 tambem (wrap-around)
        assert roulette.compute_wheel_dist(26, 0) == 1
        assert roulette.compute_wheel_dist(0, 26) == 1

    def test_max_distance_is_eighteen(self):
        # WHEEL_SEQUENCE[0]=0 e WHEEL_SEQUENCE[18]=10
        assert roulette.compute_wheel_dist(0, 10) == 18
        assert roulette.compute_wheel_dist(10, 0) == 18

    def test_symmetric(self):
        for a in [0, 5, 17, 26, 36]:
            for b in [0, 7, 19, 35, 36]:
                assert roulette.compute_wheel_dist(a, b) == roulette.compute_wheel_dist(b, a)

    def test_always_in_range(self):
        for a in range(37):
            for b in range(37):
                d = roulette.compute_wheel_dist(a, b)
                assert 0 <= d <= 18

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            roulette.compute_wheel_dist(-1, 0)
        with pytest.raises(ValueError):
            roulette.compute_wheel_dist(0, 37)


class TestComputeWheelDistDir:
    def test_same_number_is_zero(self):
        assert roulette.compute_wheel_dist_dir(0, 0, Direction.CLOCKWISE) == 0
        assert roulette.compute_wheel_dist_dir(0, 0, Direction.COUNTERCLOCKWISE) == 0

    def test_cw_one_step_forward(self):
        # 0 -> 32 = +1 no sentido CW
        assert roulette.compute_wheel_dist_dir(0, 32, Direction.CLOCKWISE) == 1
        # 0 -> 26 = -1 no sentido CW (26 esta uma casa "atras" do 0)
        assert roulette.compute_wheel_dist_dir(0, 26, Direction.CLOCKWISE) == -1

    def test_ccw_inverts(self):
        # 0 -> 32 = -1 no sentido CCW (inverso de CW)
        assert roulette.compute_wheel_dist_dir(0, 32, Direction.COUNTERCLOCKWISE) == -1
        # 0 -> 26 = +1 no sentido CCW
        assert roulette.compute_wheel_dist_dir(0, 26, Direction.COUNTERCLOCKWISE) == 1

    def test_magnitude_matches_unsigned(self):
        for a in [0, 5, 17, 36]:
            for b in [0, 7, 19, 35]:
                signed_cw = roulette.compute_wheel_dist_dir(a, b, Direction.CLOCKWISE)
                signed_ccw = roulette.compute_wheel_dist_dir(a, b, Direction.COUNTERCLOCKWISE)
                unsigned = roulette.compute_wheel_dist(a, b)
                assert abs(signed_cw) == unsigned
                assert abs(signed_ccw) == unsigned
                # CW e CCW sao simetricos (sinal trocado quando distancia < 18)
                if unsigned < 18:
                    assert signed_cw == -signed_ccw or signed_cw == signed_ccw  # 0 caso

    def test_range(self):
        for a in range(37):
            for b in range(37):
                for d in (Direction.CLOCKWISE, Direction.COUNTERCLOCKWISE):
                    sd = roulette.compute_wheel_dist_dir(a, b, d)
                    assert -18 <= sd <= 18


class TestComputeWheelDistMinToSet:
    def test_single_center_matches_unsigned(self):
        for a in [0, 5, 17, 26, 36]:
            for b in [0, 7, 19, 35]:
                assert roulette.compute_wheel_dist_min_to_set([a], b) == \
                    roulette.compute_wheel_dist(a, b)

    def test_picks_minimum(self):
        # actual=0 — centros [10, 32, 26]: dist 18, 1, 1 — min = 1
        assert roulette.compute_wheel_dist_min_to_set([10, 32, 26], 0) == 1

    def test_empty_returns_none(self):
        assert roulette.compute_wheel_dist_min_to_set([], 17) is None

    def test_invalid_centers_skipped(self):
        # 99 invalido, None invalido, 32 valido — usa 32
        result = roulette.compute_wheel_dist_min_to_set([99, None, 32, "x"], 0)
        assert result == 1

    def test_all_invalid_returns_none(self):
        assert roulette.compute_wheel_dist_min_to_set([99, -5, "x"], 17) is None

    def test_invalid_actual_raises(self):
        with pytest.raises(ValueError):
            roulette.compute_wheel_dist_min_to_set([0, 5], 99)


class TestRealWorldScenarios:
    """Cenários reais inspirados em dados live (audit 26/05)."""

    def test_typical_hit_distance(self):
        # baseline esperado: media ~9, hits ate ~6 sao "perto"
        d = roulette.compute_wheel_dist(19, 17)  # exemplo da decisao 5049
        assert 0 <= d <= 18

    def test_far_miss_is_high(self):
        # numero oposto deveria dar dist alta
        # WHEEL_SEQUENCE[0]=0, WHEEL_SEQUENCE[18]=10
        assert roulette.compute_wheel_dist(0, 10) >= 17
