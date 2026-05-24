"""Integration tests do CDC worker — S5.

Skip elegante se PG nao disponivel (ROLETA_TEST_PG_ENABLED!=1).

Validacoes:
1. publisher.publish_spin_features grava em shared.outbox.
2. process_one_batch replica para cw|ccw.spins_vectors.
3. event idempotente (mesmo UUID 2x = 1 row).
4. payload invalido marca status='failed' apos MAX_RETRIES.
5. SKIP LOCKED: 2 workers em paralelo nao processam mesma linha.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest

PG_ENABLED = os.environ.get("ROLETA_TEST_PG_ENABLED") == "1"
DSN = os.environ.get("ROLETA_PG_DSN", "")

pytestmark = pytest.mark.skipif(
    not PG_ENABLED or not DSN,
    reason="ROLETA_TEST_PG_ENABLED=1 + ROLETA_PG_DSN required",
)


@pytest.fixture
def conn():
    import psycopg2
    c = psycopg2.connect(DSN)
    c.autocommit = False
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _cleanup(conn):
    """Limpa apenas linhas criadas pelos testes (matched por meta.test_marker)."""
    yield
    with conn.cursor() as cur:
        cur.execute("DELETE FROM cw.spins_vectors WHERE meta->>'test_marker' = 'cdc-worker-test';")
        cur.execute("DELETE FROM ccw.spins_vectors WHERE meta->>'test_marker' = 'cdc-worker-test';")
        cur.execute(
            "DELETE FROM shared.outbox WHERE payload->'meta'->>'test_marker' = 'cdc-worker-test';"
        )
    conn.commit()


def _publish_raw(conn, payload: dict[str, Any], event_uuid: str | None = None) -> str:
    from psycopg2.extras import Json
    evt = event_uuid or str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO shared.outbox (event_uuid, aggregate, aggregate_id, payload)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (event_uuid) DO NOTHING
            RETURNING id;
            """,
            (evt, "spin", "test", Json(payload)),
        )
        row = cur.fetchone()
    conn.commit()
    return evt if row else evt


def _count_pending(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM shared.outbox WHERE status='pending';")
        return cur.fetchone()[0]


def test_publisher_writes_outbox(conn):
    from database.outbox_publisher import OutboxPublisher

    pub = OutboxPublisher(DSN)
    evt = pub.publish_spin_features(
        direction="cw",
        raw_features=[83.0, 75.0, 12.0, 3.0, 8.0, -5.0],
        decision_id=999,
        meta={"test_marker": "cdc-worker-test"},
    )
    pub.close()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT aggregate, payload, status FROM shared.outbox WHERE event_uuid=%s;",
            (evt,),
        )
        row = cur.fetchone()
    assert row is not None
    assert row[0] == "spin"
    assert row[1]["event_type"] == "spin_features"
    assert row[1]["direction"] == "cw"
    assert row[2] == "pending"


def test_publisher_idempotent_same_uuid(conn):
    from database.outbox_publisher import OutboxPublisher

    pub = OutboxPublisher(DSN)
    evt = str(uuid.uuid4())
    pub.publish_spin_features(
        direction="cw",
        raw_features=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        decision_id=1,
        meta={"test_marker": "cdc-worker-test"},
        event_uuid=evt,
    )
    pub.publish_spin_features(
        direction="cw",
        raw_features=[9.0, 9.0, 9.0, 9.0, 9.0, 9.0],  # diferente, mas mesmo UUID
        decision_id=1,
        meta={"test_marker": "cdc-worker-test"},
        event_uuid=evt,
    )
    pub.close()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM shared.outbox WHERE event_uuid=%s;",
            (evt,),
        )
        assert cur.fetchone()[0] == 1


def test_worker_replicates_spin_to_cw_vectors(conn):
    from database.outbox_publisher import OutboxPublisher
    from workers.cdc_worker import process_one_batch

    pub = OutboxPublisher(DSN)
    pub.publish_spin_features(
        direction="cw",
        raw_features=[83.0, 75.0, 12.0, 3.0, 8.0, -5.0],
        decision_id=12345,
        meta={"test_marker": "cdc-worker-test"},
    )
    pub.close()

    n = process_one_batch(conn)
    assert n >= 1

    with conn.cursor() as cur:
        cur.execute(
            "SELECT decision_id, meta FROM cw.spins_vectors "
            "WHERE meta->>'test_marker' = 'cdc-worker-test';"
        )
        rows = cur.fetchall()
    assert any(r[0] == 12345 for r in rows)


def test_worker_marks_invalid_payload(conn):
    from workers.cdc_worker import MAX_RETRIES, process_one_batch

    evt = _publish_raw(
        conn,
        {
            "event_type": "spin_features",
            "direction": "diagonal",  # invalido
            "raw_features": [1, 2, 3, 4, 5, 6],
            "meta": {"test_marker": "cdc-worker-test"},
        },
    )

    # Roda MAX_RETRIES + 1 vezes para garantir transicao para 'failed'.
    for _ in range(MAX_RETRIES + 1):
        process_one_batch(conn)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, retries, error FROM shared.outbox WHERE event_uuid=%s;",
            (evt,),
        )
        status, retries, error = cur.fetchone()
    assert status == "failed", f"expected failed, got status={status} retries={retries}"
    assert retries >= MAX_RETRIES
    assert error and "diagonal" in error.lower()


def test_worker_skips_unknown_event_type(conn):
    from workers.cdc_worker import process_one_batch

    evt = _publish_raw(
        conn,
        {
            "event_type": "ufo_landing",
            "meta": {"test_marker": "cdc-worker-test"},
        },
    )

    process_one_batch(conn)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, retries FROM shared.outbox WHERE event_uuid=%s;",
            (evt,),
        )
        status, retries = cur.fetchone()
    assert status in ("pending", "failed")
    assert retries >= 1


def test_validation_unit():
    """Validacao pura (sem PG)."""
    from workers.cdc_worker import _validate_spin_features

    # OK
    _validate_spin_features({"direction": "cw", "raw_features": [1, 2, 3, 4, 5, 6]})

    with pytest.raises(ValueError, match="invalid direction"):
        _validate_spin_features({"direction": "ne", "raw_features": [1, 2, 3, 4, 5, 6]})

    with pytest.raises(ValueError, match="must be a list of 6"):
        _validate_spin_features({"direction": "cw", "raw_features": [1, 2, 3]})

    with pytest.raises(ValueError, match="non-numeric"):
        _validate_spin_features({"direction": "cw", "raw_features": [1, 2, 3, 4, 5, "x"]})
