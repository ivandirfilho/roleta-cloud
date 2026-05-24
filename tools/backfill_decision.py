"""J-* Backfill tool: re-injeta evento outbox para decision perdida.

Uso:
    docker exec roleta-cloud python /app/tools/backfill_decision.py --decision-id 3698
    docker exec roleta-cloud python /app/tools/backfill_decision.py --decision-id 3698 --dry-run

Preserva semantica de tempo (meta.original_decision_ts) e flag meta.backfill=true
para que consumidores ML possam ignorar replays.

Idempotente: WHERE NOT EXISTS em (ccw:<id>, cw:<id>).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras

SQLITE_PATH_DEFAULT = "/app/data/decisions.db"
PG_DSN_DEFAULT = "host=roleta-pg user=roleta password={pw} dbname=roleta".format(
    pw=os.environ.get("POSTGRES_PASSWORD", "")
)

DIRECTION_MAP = {
    "horario": "cw", "anti-horario": "ccw",
    "cw": "cw", "ccw": "ccw",
    "clockwise": "cw", "counter-clockwise": "ccw",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--decision-id", type=int, required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--sqlite", default=os.environ.get("ROLETA_SQLITE_PATH", SQLITE_PATH_DEFAULT))
    p.add_argument("--pg-dsn", default=os.environ.get("ROLETA_PG_DSN", PG_DSN_DEFAULT))
    return p.parse_args()


def main() -> int:
    args = parse_args()
    sq = sqlite3.connect(args.sqlite)
    sq.row_factory = sqlite3.Row
    try:
        row = sq.execute(
            "SELECT id, timestamp, session_id, spin_number, spin_direction, "
            "spin_force, tr_c4_rate, tr_m6_rate, tr_l12_rate, "
            "sda_score, sda_predicted_force, gale_level, final_action "
            "FROM decisions WHERE id=?",
            (args.decision_id,),
        ).fetchone()
    finally:
        sq.close()

    if row is None:
        print(json.dumps({"error": f"decision {args.decision_id} not found"}), file=sys.stderr)
        return 2

    direction = DIRECTION_MAP.get((row["spin_direction"] or "").strip().lower())
    if direction is None:
        print(json.dumps({"error": f"unknown direction {row['spin_direction']!r}"}), file=sys.stderr)
        return 2

    raw_features = [
        float(row["spin_force"] or 0),
        float(row["tr_c4_rate"] or 0.0),
        float(row["tr_m6_rate"] or 0.0),
        float(row["tr_l12_rate"] or 0.0),
        float(row["sda_score"] or 0),
        float(row["sda_predicted_force"] or 0),
    ]
    payload = {
        "event_type": "spin_features",
        "decision_id": row["id"],
        "direction": direction,
        "raw_features": raw_features,
        "meta": {
            "session_id": row["session_id"],
            "final_action": row["final_action"],
            "gale_level": row["gale_level"],
            "backfill": True,
            "original_decision_ts": row["timestamp"],
        },
    }
    aggregate_id = f"{direction}:{row['id']}"

    if args.dry_run:
        print(json.dumps({"dry_run": True, "aggregate_id": aggregate_id, "payload": payload}, indent=2))
        return 0

    pg = psycopg2.connect(args.pg_dsn)
    try:
        with pg, pg.cursor() as pc:
            pc.execute(
                "INSERT INTO shared.outbox (event_uuid, aggregate, aggregate_id, payload) "
                "SELECT gen_random_uuid(), 'spin', %s, %s::jsonb "
                "WHERE NOT EXISTS (SELECT 1 FROM shared.outbox "
                "WHERE aggregate_id IN (%s, %s)) "
                "RETURNING id",
                (aggregate_id, json.dumps(payload),
                 f"ccw:{row['id']}", f"cw:{row['id']}"),
            )
            inserted = pc.fetchone()
    finally:
        pg.close()

    if inserted is None:
        print(json.dumps({"skipped": "already exists", "aggregate_id": aggregate_id}))
        return 0
    print(json.dumps({"inserted_outbox_id": inserted[0], "aggregate_id": aggregate_id, "backfill": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
