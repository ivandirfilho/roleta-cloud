"""
Testes MEL-ISO-004 — Circuit Breaker SQLite (Confiabilidade 5.3).

Cobre transicoes CLOSED -> OPEN -> HALF_OPEN -> CLOSED|OPEN.
"""
import sqlite3
import time
from unittest.mock import patch

import pytest

from database.sqlite_repo import (
    CircuitBreakerOpen,
    SQLiteDecisionRepository,
    _SQLiteCircuitBreaker,
)


class TestCircuitBreakerStandalone:
    def test_starts_closed(self):
        cb = _SQLiteCircuitBreaker()
        assert cb.state == "CLOSED"
        cb.before_call()  # nao deve raise

    def test_opens_after_threshold(self):
        cb = _SQLiteCircuitBreaker(failure_threshold=3, window_seconds=10)
        for _ in range(3):
            cb.before_call()
            cb.record_failure(sqlite3.OperationalError("boom"))
        assert cb.state == "OPEN"
        with pytest.raises(CircuitBreakerOpen):
            cb.before_call()

    def test_success_resets_failures(self):
        cb = _SQLiteCircuitBreaker(failure_threshold=3, window_seconds=10)
        cb.record_failure(sqlite3.OperationalError("e1"))
        cb.record_failure(sqlite3.OperationalError("e2"))
        cb.record_success()
        assert cb.state == "CLOSED"
        # Agora precisa de 3 novas para abrir
        cb.record_failure(sqlite3.OperationalError("e3"))
        cb.record_failure(sqlite3.OperationalError("e4"))
        assert cb.state == "CLOSED"

    def test_window_slides(self):
        cb = _SQLiteCircuitBreaker(failure_threshold=3, window_seconds=0.05)
        cb.record_failure(sqlite3.OperationalError("old"))
        cb.record_failure(sqlite3.OperationalError("old"))
        time.sleep(0.1)
        cb.record_failure(sqlite3.OperationalError("new"))
        # falhas antigas saem da janela
        assert cb.state == "CLOSED"

    def test_half_open_after_cooldown(self):
        cb = _SQLiteCircuitBreaker(
            failure_threshold=2, window_seconds=10, cooldown_seconds=0.05
        )
        cb.record_failure(sqlite3.OperationalError("x"))
        cb.record_failure(sqlite3.OperationalError("x"))
        assert cb.state == "OPEN"
        time.sleep(0.06)
        cb.before_call()  # transiciona para HALF_OPEN
        assert cb.state == "HALF_OPEN"
        cb.record_success()
        assert cb.state == "CLOSED"

    def test_half_open_failure_reopens(self):
        cb = _SQLiteCircuitBreaker(
            failure_threshold=2, window_seconds=10, cooldown_seconds=0.05
        )
        cb.record_failure(sqlite3.OperationalError("x"))
        cb.record_failure(sqlite3.OperationalError("x"))
        time.sleep(0.06)
        cb.before_call()
        assert cb.state == "HALF_OPEN"
        cb.record_failure(sqlite3.OperationalError("ainda-quebrado"))
        assert cb.state == "OPEN"
        with pytest.raises(CircuitBreakerOpen):
            cb.before_call()


class TestRepositoryIntegration:
    def test_repository_uses_breaker(self, tmp_path):
        db = tmp_path / "decisions.db"
        cb = _SQLiteCircuitBreaker(failure_threshold=2, window_seconds=10)
        repo = SQLiteDecisionRepository(db_path=str(db), circuit_breaker=cb)
        # Operacao normal funciona
        conn = repo._get_connection()
        conn.close()
        assert cb.state == "CLOSED"

    def test_breaker_opens_on_repeated_sqlite_errors(self, tmp_path):
        db = tmp_path / "decisions.db"
        cb = _SQLiteCircuitBreaker(failure_threshold=2, window_seconds=10)
        repo = SQLiteDecisionRepository(db_path=str(db), circuit_breaker=cb)
        # Forca falhas de connect
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("disk full")):
            for _ in range(2):
                with pytest.raises(sqlite3.OperationalError):
                    repo._get_connection()
        assert cb.state == "OPEN"
        with pytest.raises(CircuitBreakerOpen):
            repo._get_connection()

    def test_breaker_recovers_after_cooldown(self, tmp_path):
        db = tmp_path / "decisions.db"
        cb = _SQLiteCircuitBreaker(
            failure_threshold=2, window_seconds=10, cooldown_seconds=0.05
        )
        repo = SQLiteDecisionRepository(db_path=str(db), circuit_breaker=cb)
        with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("x")):
            for _ in range(2):
                with pytest.raises(sqlite3.OperationalError):
                    repo._get_connection()
        assert cb.state == "OPEN"
        time.sleep(0.06)
        # Conexao real funciona -> HALF_OPEN -> CLOSED
        conn = repo._get_connection()
        conn.close()
        assert cb.state == "CLOSED"
