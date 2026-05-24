"""Tests para skeletons S7/S10/S11/S8 (que nao dependem de PG)."""
from __future__ import annotations

import pytest


def test_cold_regions_score_basic():
    from strategies.cold_regions import ColdRegionsStrategy
    s = ColdRegionsStrategy(window_size=10, num_regions=4)
    # regiao 0 muito visitada, regiao 3 nunca
    scores = s.score([0, 0, 0, 0, 1, 1, 2, 0, 0, 0])
    by_id = {sc.region_id: sc for sc in scores}
    assert by_id[0].coldness < by_id[3].coldness
    assert by_id[3].coldness == 1.0
    assert by_id[3].visits_last_n == 0


def test_cold_regions_empty():
    from strategies.cold_regions import ColdRegionsStrategy
    s = ColdRegionsStrategy(num_regions=4)
    scores = s.score([])
    assert all(sc.coldness == 1.0 for sc in scores)


def test_cold_regions_validation():
    from strategies.cold_regions import ColdRegionsStrategy
    with pytest.raises(ValueError):
        ColdRegionsStrategy(window_size=0)
    with pytest.raises(ValueError):
        ColdRegionsStrategy(num_regions=1)


def test_outlier_filter_removes_extremes():
    from strategies.outlier_filter import filter_outliers_tukey
    values = [10, 11, 12, 13, 14, 15, 16, 17, 100]  # 100 = outlier
    r = filter_outliers_tukey(values)
    assert 100 in r.removed
    assert 100 not in r.clean
    assert len(r.clean) == 8


def test_outlier_filter_small_sample():
    from strategies.outlier_filter import filter_outliers_tukey
    # n<4 -> nao filtra
    r = filter_outliers_tukey([1, 100, 2])
    assert r.removed == []
    assert sorted(r.clean) == [1, 2, 100]


def test_outlier_filter_empty():
    from strategies.outlier_filter import filter_outliers_tukey
    r = filter_outliers_tukey([])
    assert r.clean == []
    assert r.removed == []


def test_spin_encoder_load_missing_returns_none():
    from models.spin_encoder import SpinEncoder
    from pathlib import Path
    enc = SpinEncoder.load(Path("nonexistent_xyz.joblib"))
    assert enc is None


def test_spin_encoder_encode_without_model():
    from models.spin_encoder import SpinEncoder
    enc = SpinEncoder(model=None)
    assert enc.encode([1, 2, 3, 4, 5, 6]) is None


def test_age_queries_graph_whitelist():
    from database.age.queries import run_cypher, _validate_graph
    with pytest.raises(ValueError):
        _validate_graph("evil_graph")
    with pytest.raises(ValueError):
        _validate_graph("cw_graph; DROP TABLE")


def test_age_find_recent_path_depth_validation():
    from database.age.queries import find_recent_path

    class FakeConn:
        def cursor(self):
            raise AssertionError("nao deve chegar aqui")

    with pytest.raises(ValueError):
        find_recent_path(FakeConn(), "cw_graph", depth=0)
    with pytest.raises(ValueError):
        find_recent_path(FakeConn(), "cw_graph", depth=999)


def test_shadow_predictor_noop():
    from strategies.shadow_predictor import NoopShadowPredictor
    p = NoopShadowPredictor()
    assert p.predict("cw", [1, 2, 3, 4, 5, 6]) is None


def test_shadow_compare_handles_none():
    from strategies.shadow_predictor import compare_and_log
    # nao deve levantar
    compare_and_log({"predicted_force": 50}, None, decision_id=1)
