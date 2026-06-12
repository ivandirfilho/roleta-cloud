"""P3.1 backfill — copia decision_dna SQLite → shared.decision_dna (PG).

One-shot, idempotente (anti-duplo por decision_id+feature_name). Roda
dentro do container roleta-cloud (tem SQLite, psycopg2 e ROLETA_PG_DSN).

Uso: docker exec roleta-cloud python /tmp/backfill_dna_pg.py
"""
import json
import os
import sqlite3

import psycopg2
from psycopg2.extras import Json

SQLITE = "/app/data/decisions.db"
DSN = os.environ["ROLETA_PG_DSN"]

src = sqlite3.connect(f"file:{SQLITE}?mode=ro", uri=True)
src.row_factory = sqlite3.Row
rows = src.execute("""
    SELECT decision_id, spin_number, direction, ts, feature_name, feature_value,
           estimated_lift_pp, realized_lift_pp, confidence_n, final_action,
           hit, wheel_dist
    FROM decision_dna ORDER BY id
""").fetchall()
print(f"SQLite decision_dna: {len(rows)} rows")

pg = psycopg2.connect(DSN)
pg.autocommit = False
ins = skip = 0
with pg.cursor() as cur:
    for r in rows:
        try:
            fv = json.loads(r["feature_value"] or "{}")
        except (ValueError, TypeError):
            fv = {"raw": r["feature_value"]}
        direction = {"horario": "cw", "anti-horario": "ccw"}.get(
            r["direction"] or "", r["direction"]
        )
        cur.execute(
            """
            INSERT INTO shared.decision_dna
                (decision_id, spin_number, direction, ts, feature_name,
                 feature_value, estimated_lift_pp, realized_lift_pp,
                 confidence_n, final_action, hit, wheel_dist)
            SELECT %s, %s, %s, COALESCE(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s, %s, %s
            WHERE NOT EXISTS (
                SELECT 1 FROM shared.decision_dna
                WHERE decision_id = %s AND feature_name = %s
            );
            """,
            (
                r["decision_id"], r["spin_number"], direction, r["ts"],
                r["feature_name"], Json(fv), r["estimated_lift_pp"],
                r["realized_lift_pp"], r["confidence_n"], r["final_action"],
                bool(r["hit"]) if r["hit"] is not None else None, r["wheel_dist"],
                r["decision_id"], r["feature_name"],
            ),
        )
        if cur.rowcount:
            ins += 1
        else:
            skip += 1
pg.commit()
with pg.cursor() as cur:
    cur.execute("SELECT count(*) FROM shared.decision_dna")
    total = cur.fetchone()[0]
print(f"backfill: inseridas={ins} puladas(dup)={skip} | PG total={total}")
pg.close()
src.close()
