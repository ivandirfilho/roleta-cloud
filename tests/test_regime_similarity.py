"""S-STRAT-12 — testes unitários do RegimeSimilarityReader.

Sem dependência de PG real (validação de input + comportamento sem DSN).
"""
from __future__ import annotations

import pytest

from database.regime_similarity import RegimeSimilarityReader


def test_reader_rejects_invalid_direction():
    r = RegimeSimilarityReader(dsn=None)
    with pytest.raises(ValueError, match="direction"):
        r.find_similar("xy", [1.0] * 6)
    with pytest.raises(ValueError, match="direction"):
        r.regime_score("xy", [1.0] * 6)


def test_reader_rejects_wrong_vector_dim():
    r = RegimeSimilarityReader(dsn=None)
    with pytest.raises(ValueError, match="must be list"):
        r.find_similar("cw", [1.0, 2.0, 3.0])  # 3 floats em vez de 6
    with pytest.raises(ValueError):
        r.find_similar("cw", "not_a_list")  # type: ignore[arg-type]


def test_reader_rejects_non_numeric_vector():
    r = RegimeSimilarityReader(dsn=None)
    with pytest.raises(ValueError, match="non-numeric"):
        r.find_similar("cw", [1.0, 2.0, "x", 4.0, 5.0, 6.0])  # type: ignore[list-item]


def test_reader_rejects_bad_limit():
    r = RegimeSimilarityReader(dsn=None)
    with pytest.raises(ValueError, match="limit"):
        r.find_similar("cw", [1.0] * 6, limit=0)
    with pytest.raises(ValueError, match="limit"):
        r.find_similar("cw", [1.0] * 6, limit=101)
    with pytest.raises(ValueError, match="limit"):
        r.regime_score("cw", [1.0] * 6, limit=201)


def test_reader_returns_empty_when_no_dsn():
    r = RegimeSimilarityReader(dsn=None)
    assert r.find_similar("cw", [1.0] * 6) == []
    score = r.regime_score("ccw", [0.0] * 6)
    assert score == {"n": 0, "avg_distance": None, "hit_rate": None, "direction": "ccw"}


def test_reader_close_is_idempotent():
    r = RegimeSimilarityReader(dsn=None)
    r.close()
    r.close()  # não deve raise
