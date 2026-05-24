"""M-1 Gap Detector: detecta decisões SQLite sem evento correspondente em PG outbox.

Run as:
    docker exec roleta-cloud python -m tools.gap_detector
Or scheduled (cron/systemd) every 60s.

Output (stdout JSON):
    {
        "ts": "2026-05-24T20:30:00",
        "decisions_max": 3769,
        "outbox_max_decision_id": 3769,
        "gap_count": 0,
        "missing_decision_ids": []
    }

Exit code:
    0 → no gaps
    1 → gaps found (suitable for alerting)
    2 → infrastructure error

Bug history: ver sprints_evolucao_pos_24_05.md §XII.3 / §XVII.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2


SQLITE_PATH = os.environ.get("ROLETA_SQLITE_PATH", "/app/data/decisions.db")
PG_DSN = os.environ.get(
    "ROLETA_PG_DSN",
    "host=roleta-pg user=roleta password={pw} dbname=roleta".format(
        pw=os.environ.get("POSTGRES_PASSWORD", "")
    ),
)
LOOKBACK_MIN = int(os.environ.get("GAP_LOOKBACK_MIN", "60"))


def main() -> int:
    if not Path(SQLITE_PATH).exists():
        print(json.dumps({"error": f"sqlite missing: {SQLITE_PATH}"}), file=sys.stderr)
        return 2

    sq = sqlite3.connect(SQLITE_PATH)
    try:
        cur = sq.execute(
            "SELECT id FROM decisions WHERE timestamp >= "
            "strftime('%Y-%m-%dT%H:%M:%S', 'now', ?) ORDER BY id",
            (f"-{LOOKBACK_MIN} minutes",),
        )
        decision_ids = {row[0] for row in cur.fetchall()}
    finally:
        sq.close()

    try:
        pg = psycopg2.connect(PG_DSN)
    except Exception as exc:
        print(json.dumps({"error": f"pg connect: {exc}"}), file=sys.stderr)
        return 2
    try:
        with pg.cursor() as pc:
            pc.execute(
                "SELECT DISTINCT split_part(aggregate_id, ':', 2)::bigint "
                "FROM shared.outbox WHERE aggregate = 'spin' "
                "AND created_at >= now() - make_interval(mins => %s)",
                (LOOKBACK_MIN,),
            )
            outbox_ids = {row[0] for row in pc.fetchall()}
    finally:
        pg.close()

    missing = sorted(decision_ids - outbox_ids)
    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lookback_min": LOOKBACK_MIN,
        "decisions_count": len(decision_ids),
        "outbox_count": len(outbox_ids),
        "gap_count": len(missing),
        "missing_decision_ids": missing[:50],
    }
    print(json.dumps(result))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
