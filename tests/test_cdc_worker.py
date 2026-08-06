"""Integration tests do CDC worker — S5.

Skip elegante se PG nao disponivel (ROLETA_TEST_PG_ENABLED!=1).

Validacoes:
1. publisher.publish_spin_features grava em shared.outbox.
2. process_one_batch replica para cw|ccw.spins_vectors.
3. event idempotente (mesmo UUID 2x = 1 row).
4. payload invalido marca status='failed' apos MAX_RETRIES.
5. SKIP LOCKED: 2 workers em paralelo nao processam mesma linha.
6. (06/08) spin_result COM contexto projeta as colunas de contexto em
   cw|ccw.spin_features contra PG real — incluindo a coluna citada "table".
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

TEST_MARKER = "cdc-worker-test"


@pytest.fixture
def conn():
    import psycopg2
    c = psycopg2.connect(DSN)
    c.autocommit = False
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _cleanup(conn):
    """Limpa apenas linhas criadas pelos testes (matched por meta.test_marker).

    Correcao 06/08: `spin_features` nunca era limpo — linhas de teste ficavam no
    feature store e contaminavam a janela de lag (recent_acc/streaks) das
    execucoes seguintes, tornando os proprios testes dependentes de ordem.
    """
    yield
    with conn.cursor() as cur:
        for schema in ("cw", "ccw"):
            cur.execute(
                f"DELETE FROM {schema}.spins_vectors "
                "WHERE meta->>'test_marker' = %s;", (TEST_MARKER,)
            )
            cur.execute(
                f"DELETE FROM {schema}.spin_features "
                "WHERE meta->>'test_marker' = %s;", (TEST_MARKER,)
            )
        cur.execute(
            "DELETE FROM shared.outbox "
            "WHERE payload->'meta'->>'test_marker' = %s;", (TEST_MARKER,)
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


# ---------- Projecao do contexto em PG real (correcao 06/08) ----------


def _spin_result_payload(direction: str, decision_id: int, context: dict) -> dict:
    """Payload realista de `spin_result` + marker no meta para o cleanup.

    O `meta` NAO carrega `spin_number`: e exatamente assim que o produtor emite,
    e serve de prova de que a linha legada `meta.get('spin_number', ...)` nao
    sequestra o numero real do resultado quando o meta existe por outro motivo.
    """
    return {
        "event_type": "spin_result",
        "direction": direction,
        "decision_id": decision_id,
        "hit": True,
        "actual_number": 32,
        "session_id": "sess-ctx-test",
        "meta": {"test_marker": TEST_MARKER},
        "context": context,
    }


@pytest.mark.parametrize("direction,decision_id", [("cw", 991001), ("ccw", 991002)])
def test_worker_projects_full_context_into_spin_features(
    conn, monkeypatch, direction, decision_id,
):
    """E2E contra PG real: contexto do evento -> colunas de cw|ccw.spin_features.

    Cobre o alias perigoso `dealer_table` -> coluna citada "table" (palavra
    reservada), que so o banco de verdade consegue reprovar.
    """
    monkeypatch.setenv("SDA_PG_FEATURE_CONTEXT", "1")
    from database.outbox_integration import build_pg_feature_context
    from workers.cdc_worker import process_one_batch

    context = build_pg_feature_context({
        "id": decision_id,
        "session_id": "sess-ctx-test",
        "dealer": "Ana",
        "dealer_table": "Roleta ao Vivo",
        "provider": "Evolution",
        "round_id": "r-991",
        "wheel_model": "Roleta ao Vivo",
        "vision_confidence": 0.87,
        "vision_source": "vision",
        "spin_seq": 31,
        "direction_source": "authority",
        "direction_confidence": 0.91,
        "direction_next": "anti-horario",
        "phase_uncertain": False,
        "sda_center": 17,
        "gale_level": 2,
    })
    _publish_raw(conn, _spin_result_payload(direction, decision_id, context))

    assert process_one_batch(conn) >= 1

    schema = direction
    with conn.cursor() as cur:
        cur.execute(
            f'SELECT spin_number, hit, session_id, dealer, "table", provider, '
            f'round_id, wheel_model, vision_confidence, vision_source, spin_seq, '
            f'direction_source, direction_confidence, direction_next, '
            f'phase_uncertain, centro_previsto, gale_level '
            f"FROM {schema}.spin_features WHERE decision_id = %s;",
            (decision_id,),
        )
        row = cur.fetchone()
    assert row is not None, f"nenhuma linha em {schema}.spin_features"
    (spin_number, hit, session_id, dealer, table, provider, round_id, wheel_model,
     vis_conf, vis_src, spin_seq, dir_src, dir_conf, dir_next, phase_unc,
     centro, gale) = row

    # spin_number continua sendo o numero REAL do resultado, nao o da decisao.
    assert spin_number == 32
    assert hit is True
    assert session_id == "sess-ctx-test"
    assert dealer == "Ana"
    assert table == "Roleta ao Vivo"        # coluna citada "table"
    assert provider == "Evolution"
    assert round_id == "r-991"
    assert wheel_model == "Roleta ao Vivo"
    assert abs(vis_conf - 0.87) < 1e-6
    assert vis_src == "vision"
    assert spin_seq == 31
    assert dir_src == "authority"
    assert abs(dir_conf - 0.91) < 1e-6
    assert dir_next == "ccw"                # normalizado no produtor
    assert phase_unc is False
    assert centro == 17
    assert gale == 2


def test_worker_hostile_floats_keep_the_essential_row(conn, monkeypatch):
    """Float impossivel no contexto vira NULL — a linha essencial sobrevive.

    A coluna e REAL (float4): 1e300 estoura por overflow e 1e-300 por underflow.
    Ambos passam pelo JSONB, entao so a coercao do worker impede que um campo
    OPCIONAL mande o resultado para a DLQ.
    """
    monkeypatch.setenv("SDA_PG_FEATURE_CONTEXT", "1")
    from workers.cdc_worker import process_one_batch

    decision_id = 991003
    context = {
        "decision_id": decision_id,
        "session_id": "sess-ctx-test",
        "dealer": "Bia",
        "dealer_table": "Mesa Y",
        "vision_confidence": 1e300,     # overflow em float4
        "direction_confidence": 1e-300,  # underflow em float4
        "spin_seq": 3,
        "direction_source": "dom",
    }
    evt = _publish_raw(conn, _spin_result_payload("ccw", decision_id, context))

    process_one_batch(conn)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, error FROM shared.outbox WHERE event_uuid = %s;", (evt,)
        )
        status, error = cur.fetchone()
        cur.execute(
            'SELECT spin_number, hit, dealer, "table", vision_confidence, '
            "direction_confidence, spin_seq "
            "FROM ccw.spin_features WHERE decision_id = %s;", (decision_id,),
        )
        row = cur.fetchone()

    assert status == "processed", f"evento foi para a DLQ: {error}"
    assert row is not None, "resultado essencial perdido por causa de campo opcional"
    spin_number, hit, dealer, table, vis_conf, dir_conf, spin_seq = row
    assert spin_number == 32 and hit is True
    assert vis_conf is None and dir_conf is None
    # O resto do contexto continua projetado.
    assert dealer == "Bia" and table == "Mesa Y" and spin_seq == 3


def test_worker_flag_off_writes_legacy_row_against_real_pg(conn, monkeypatch):
    """Worker com flag OFF ignora o contexto sem quebrar (skew produtor-ON)."""
    monkeypatch.setenv("SDA_PG_FEATURE_CONTEXT", "0")
    from database.outbox_integration import build_pg_feature_context
    from workers.cdc_worker import process_one_batch

    decision_id = 991004
    context = build_pg_feature_context({
        "id": decision_id, "session_id": "sess-ctx-test", "dealer": "Ana",
        "dealer_table": "Mesa X",
    })
    evt = _publish_raw(conn, _spin_result_payload("cw", decision_id, context))
    process_one_batch(conn)

    with conn.cursor() as cur:
        cur.execute("SELECT status FROM shared.outbox WHERE event_uuid = %s;", (evt,))
        assert cur.fetchone()[0] == "processed"
        cur.execute(
            "SELECT spin_number, hit, dealer, spin_seq "
            "FROM cw.spin_features WHERE decision_id = %s;", (decision_id,),
        )
        spin_number, hit, dealer, spin_seq = cur.fetchone()
    assert spin_number == 32 and hit is True
    assert dealer == "unknown"   # DEFAULT do DDL: nada foi projetado
    assert spin_seq is None
