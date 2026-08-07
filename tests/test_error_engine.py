"""Tests do Error Engine (strategies/error_engine.py) — ADENDO 05/08 noite-2.

Cobre a precedência completa da taxonomia e o contrato defensivo
(entradas None/parciais degradam sem levantar).
"""
from __future__ import annotations

import pytest

from strategies.error_engine import (
    ERROR_CLASSES,
    FROZEN_CLASSES,
    classify_error,
    is_frozen,
)


def test_data_suspect_trumps_everything_even_hit():
    assert classify_error(
        hit=True, data_suspect=True, signed_err=0,
        gap_to_coverage=0, err_hist=[9, 9, 9, 9, 9],
    ) == "DATA_SUSPECT"


def test_hit_before_any_miss_class():
    assert classify_error(
        hit=True, data_suspect=False, signed_err=10,
        gap_to_coverage=0, err_hist=[9, 9, 9, 9, 9],
    ) == "HIT"


@pytest.mark.parametrize("gap", [0, 1, 2])
def test_geometry_miss_gap_le_2(gap):
    assert classify_error(
        hit=False, data_suspect=False, signed_err=3,
        gap_to_coverage=gap, err_hist=[],
    ) == "GEOMETRY_MISS"


def test_gap_3_is_not_geometry():
    out = classify_error(
        hit=False, data_suspect=False, signed_err=3,
        gap_to_coverage=3, err_hist=[],
    )
    assert out == "VARIANCE"


def test_signature_shift_median_ge_4():
    # mediana(4,5,4,6,5) = 5 → shift sistemático
    assert classify_error(
        hit=False, data_suspect=False, signed_err=5,
        gap_to_coverage=4, err_hist=[4, 5, 4, 6, 5],
    ) == "SIGNATURE_SHIFT"


def test_signature_shift_negative_bias():
    assert classify_error(
        hit=False, data_suspect=False, signed_err=-5,
        gap_to_coverage=4, err_hist=[-4, -6, -5, -4, -5],
    ) == "SIGNATURE_SHIFT"


def test_signature_needs_full_window_of_5():
    # 4 amostras (< janela) → não classifica shift; |err|=5 < 8 → VARIANCE
    assert classify_error(
        hit=False, data_suspect=False, signed_err=5,
        gap_to_coverage=4, err_hist=[5, 5, 5, 5],
    ) == "VARIANCE"


def test_force_miss_abs_err_ge_8():
    assert classify_error(
        hit=False, data_suspect=False, signed_err=-9,
        gap_to_coverage=5, err_hist=[1, -2, 0, 3, -1],
    ) == "FORCE_MISS"


def test_geometry_precedes_signature_and_force():
    # gap<=2 vence mesmo com hist enviesado e erro grande
    assert classify_error(
        hit=False, data_suspect=False, signed_err=9,
        gap_to_coverage=1, err_hist=[9, 9, 9, 9, 9],
    ) == "GEOMETRY_MISS"


def test_signature_precedes_force():
    assert classify_error(
        hit=False, data_suspect=False, signed_err=9,
        gap_to_coverage=6, err_hist=[8, 9, 9, 8, 9],
    ) == "SIGNATURE_SHIFT"


def test_variance_when_small_noise():
    assert classify_error(
        hit=False, data_suspect=False, signed_err=3,
        gap_to_coverage=3, err_hist=[1, -3, 2, 0, -1],
    ) == "VARIANCE"


def test_defensive_none_inputs():
    # tudo None além do miss → decidível apenas até VARIANCE, sem levantar
    assert classify_error(
        hit=False, data_suspect=False, signed_err=None,
        gap_to_coverage=None, err_hist=None,
    ) == "VARIANCE"


def test_all_outputs_are_declared_classes():
    cases = [
        dict(hit=True, data_suspect=True, signed_err=0, gap_to_coverage=0),
        dict(hit=True, data_suspect=False, signed_err=0, gap_to_coverage=0),
        dict(hit=False, data_suspect=False, signed_err=2, gap_to_coverage=2),
        dict(hit=False, data_suspect=False, signed_err=5,
             gap_to_coverage=5, err_hist=[5, 5, 5, 5, 5]),
        dict(hit=False, data_suspect=False, signed_err=12, gap_to_coverage=9),
        dict(hit=False, data_suspect=False, signed_err=1, gap_to_coverage=4),
    ]
    for kw in cases:
        kw.setdefault("err_hist", [])
        assert classify_error(**kw) in ERROR_CLASSES


def test_is_frozen_only_data_suspect():
    assert is_frozen("DATA_SUSPECT") is True
    for cls in ERROR_CLASSES:
        if cls not in FROZEN_CLASSES:
            assert is_frozen(cls) is False
