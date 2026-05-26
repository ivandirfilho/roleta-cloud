"""NEW-12 (26/05/2026) — calibration_fill_stats provider.

Lição aprendida do bug B-09: deploys pos-W-02 deixaram `calibration_error`
populando 0/N sem alarme. Este teste blinda o provider Prometheus
`calibration_fill_stats` que alimenta o alerta `RoletaCalibrationFillRateLow`.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from database.sqlite_repo import SQLiteDecisionRepository
from database.models import Decision, Session


@pytest.fixture
def repo(tmp_path: Path) -> SQLiteDecisionRepository:
    db_path = tmp_path / "decisions.db"
    r = SQLiteDecisionRepository(db_path=str(db_path))
    r.create_session(Session(id="s1"))
    return r


def _seed(repo: SQLiteDecisionRepository, *, total: int, with_ce: int) -> None:
    """Cria `total` decisions APOSTAR com result_actual, sendo `with_ce`
    com calibration_error populado."""
    for i in range(total):
        d = Decision(
            session_id="s1",
            spin_direction="cw",
            sda_should_bet=True,
            sda_score=4,
            sda_center=0,
            sda_centers=[0, 1, 2],
            sda_numbers=[0, 1, 2],
            final_action="APOSTAR",
            tr_confidence="alta",
            tr_reason="test",
        )
        did = repo.save_decision(d)
        ce = i if i < with_ce else None
        repo.update_result(did, hit=True, actual_number=0, calibration_error=ce)


def test_fill_stats_empty_db_returns_zeros(repo: SQLiteDecisionRepository) -> None:
    stats = repo.calibration_fill_stats(window_minutes=60)
    assert stats == {"total": 0, "filled": 0}


def test_fill_stats_counts_only_apostar_with_result(repo: SQLiteDecisionRepository) -> None:
    _seed(repo, total=10, with_ce=7)
    stats = repo.calibration_fill_stats(window_minutes=60)
    assert stats["total"] == 10
    assert stats["filled"] == 7


def test_fill_stats_returns_dict_shape(repo: SQLiteDecisionRepository) -> None:
    """Provider deve sempre retornar dict com keys 'total' e 'filled'."""
    stats = repo.calibration_fill_stats()
    assert isinstance(stats, dict)
    assert "total" in stats and "filled" in stats
    assert isinstance(stats["total"], int)
    assert isinstance(stats["filled"], int)


def test_fill_stats_window_param_respected(repo: SQLiteDecisionRepository) -> None:
    """Janela de 1 minuto deve excluir decisoes mais antigas que isso."""
    _seed(repo, total=3, with_ce=3)
    # Bate forçando timestamp para >2min atrás via SQL direto
    conn = repo._get_connection()
    try:
        conn.execute(
            "UPDATE decisions SET timestamp = datetime('now', '-5 minutes')"
        )
        conn.commit()
    finally:
        conn.close()
    stats = repo.calibration_fill_stats(window_minutes=1)
    assert stats == {"total": 0, "filled": 0}
