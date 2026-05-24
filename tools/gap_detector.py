"""M-1 Gap Detector: detecta decisoes SQLite sem evento correspondente em PG outbox.

v2 (H-2/H-3 fix, sprints_evolucao_pos_24_05.md §XIX):
  - Lookback simetrico baseado em decision.id range (nao mistura
    timestamp vs created_at, imune a backfill).
  - Opcao --prom-textfile para integracao com node-exporter (gauge
    decisions_outbox_gap{lookback="60m"} N).

Run as:
    docker exec roleta-cloud python /app/tools/gap_detector.py
    docker exec roleta-cloud python /app/tools/gap_detector.py \
        --prom-textfile /var/lib/node_exporter/roleta_gap.prom

Output JSON (stdout). Exit code: 0=ok, 1=gap, 2=infra.

Bug history: ver sprints_evolucao_pos_24_05.md §XII.3 / §XVII / §XIX.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import psycopg2


SQLITE_PATH_DEFAULT = "/app/data/decisions.db"
PG_DSN_DEFAULT = "host=roleta-pg user=roleta password={pw} dbname=roleta".format(
    pw=os.environ.get("POSTGRES_PASSWORD", "")
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="M-1 gap detector v2")
    p.add_argument("--lookback-min", type=int, default=int(os.environ.get("GAP_LOOKBACK_MIN", "60")))
    p.add_argument("--sqlite", default=os.environ.get("ROLETA_SQLITE_PATH", SQLITE_PATH_DEFAULT))
    p.add_argument("--pg-dsn", default=os.environ.get("ROLETA_PG_DSN", PG_DSN_DEFAULT))
    p.add_argument("--prom-textfile", default=None, help="caminho .prom para node-exporter")
    return p.parse_args()


def write_prom_textfile(path: str, gap_count: int, lookback_min: int,
                        decisions_count: int, outbox_count: int) -> None:
    """Atomic write via temp+rename (node-exporter textfile collector exige)."""
    content = (
        "# HELP decisions_outbox_gap Total decisoes SQLite sem outbox event correspondente\n"
        "# TYPE decisions_outbox_gap gauge\n"
        f'decisions_outbox_gap{{lookback="{lookback_min}m"}} {gap_count}\n'
        "# HELP decisions_outbox_decisions_total Decisoes na janela\n"
        "# TYPE decisions_outbox_decisions_total gauge\n"
        f'decisions_outbox_decisions_total{{lookback="{lookback_min}m"}} {decisions_count}\n'
        "# HELP decisions_outbox_events_total Outbox events na janela\n"
        "# TYPE decisions_outbox_events_total gauge\n"
        f'decisions_outbox_events_total{{lookback="{lookback_min}m"}} {outbox_count}\n'
        "# HELP decisions_outbox_last_run_ts Timestamp UNIX do ultimo check\n"
        "# TYPE decisions_outbox_last_run_ts gauge\n"
        f"decisions_outbox_last_run_ts {int(datetime.now(timezone.utc).timestamp())}\n"
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".gap_", suffix=".prom")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
        raise


def main() -> int:
    args = parse_args()

    if not Path(args.sqlite).exists():
        print(json.dumps({"error": f"sqlite missing: {args.sqlite}"}), file=sys.stderr)
        return 2

    # H-2 fix: lookback baseado em id range, nao em timestamps mistos.
    # 1) acha o min decision.id que cai na janela (por timestamp event)
    # 2) compara conjuntos de IDs em decisions vs outbox aggregate_id
    #    PARA O MESMO RANGE DE IDS (imune a backfill que insere event "agora"
    #    com aggregate_id apontando para id antigo).
    sq = sqlite3.connect(args.sqlite)
    try:
        cur = sq.execute(
            "SELECT MIN(id), MAX(id) FROM decisions WHERE timestamp >= "
            "strftime('%Y-%m-%dT%H:%M:%S','now',?)",
            (f"-{args.lookback_min} minutes",),
        )
        row = cur.fetchone()
        min_id, max_id = row[0], row[1]
        if min_id is None:
            result = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "lookback_min": args.lookback_min,
                "decisions_count": 0,
                "outbox_count": 0,
                "gap_count": 0,
                "missing_decision_ids": [],
                "note": "no decisions in window",
            }
            print(json.dumps(result))
            if args.prom_textfile:
                write_prom_textfile(args.prom_textfile, 0, args.lookback_min, 0, 0)
            return 0
        cur = sq.execute(
            "SELECT id FROM decisions WHERE id BETWEEN ? AND ?",
            (min_id, max_id),
        )
        decision_ids = {row[0] for row in cur.fetchall()}
    finally:
        sq.close()

    try:
        pg = psycopg2.connect(args.pg_dsn)
    except Exception as exc:
        print(json.dumps({"error": f"pg connect: {exc}"}), file=sys.stderr)
        return 2
    try:
        with pg.cursor() as pc:
            pc.execute(
                "SELECT DISTINCT split_part(aggregate_id,':',2)::bigint "
                "FROM shared.outbox WHERE aggregate='spin' "
                "AND split_part(aggregate_id,':',2) ~ '^[0-9]+$' "
                "AND split_part(aggregate_id,':',2)::bigint BETWEEN %s AND %s",
                (min_id, max_id),
            )
            outbox_ids = {row[0] for row in pc.fetchall()}
    finally:
        pg.close()

    missing = sorted(decision_ids - outbox_ids)
    result = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lookback_min": args.lookback_min,
        "id_range": [min_id, max_id],
        "decisions_count": len(decision_ids),
        "outbox_count": len(outbox_ids),
        "gap_count": len(missing),
        "missing_decision_ids": missing[:50],
    }
    print(json.dumps(result))

    if args.prom_textfile:
        try:
            write_prom_textfile(
                args.prom_textfile, len(missing), args.lookback_min,
                len(decision_ids), len(outbox_ids),
            )
        except Exception as exc:
            print(json.dumps({"prom_textfile_error": str(exc)}), file=sys.stderr)

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
