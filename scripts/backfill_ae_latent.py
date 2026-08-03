"""Backfill de ae_latent em cw|ccw.spins_vectors (H5 03/08).

Aplica o SpinEncoder POR SENTIDO (models/spin_autoencoder_{cw,ccw}.joblib)
em todas as rows com raw_features preenchido e ae_latent NULL, gravando o
vetor 4d comprimido. Idempotente: re-execução só processa o que falta.

Uso:
    ROLETA_PG_DSN=... python scripts/backfill_ae_latent.py
    ROLETA_PG_DSN=... python scripts/backfill_ae_latent.py --batch 500 --directions cw

Sai com código 2 se nenhum modelo foi encontrado.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill_ae_latent")

ALLOWED = ("cw", "ccw")


def _parse_vec(vec) -> list[float] | None:
    if vec is None:
        return None
    if isinstance(vec, str):
        s = vec.strip().lstrip("[").rstrip("]")
        try:
            vec = [float(x) for x in s.split(",") if x.strip()]
        except ValueError:
            return None
    return [float(x) for x in vec] if len(vec) == 6 else None


def backfill_schema(conn, schema: str, encoder, batch: int) -> int:
    """Backfill de um schema. Retorna total de rows atualizadas."""
    total = 0
    while True:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, raw_features::text
                FROM {schema}.spins_vectors
                WHERE raw_features IS NOT NULL AND ae_latent IS NULL
                ORDER BY id
                LIMIT %s;
                """,
                (batch,),
            )
            rows = cur.fetchall()
            if not rows:
                break
            updates: list[tuple[str, int]] = []
            for row_id, raw in rows:
                feats = _parse_vec(raw)
                if feats is None:
                    continue
                latent = encoder.encode(feats)
                if latent is None:
                    continue
                updates.append((
                    "[" + ",".join(f"{v:.8f}" for v in latent) + "]",
                    row_id,
                ))
            if not updates:
                # rows restantes são imparseáveis — evita loop infinito
                log.warning("[%s] %d rows não-encodáveis; parando.", schema, len(rows))
                break
            cur.executemany(
                f"UPDATE {schema}.spins_vectors SET ae_latent = %s::vector WHERE id = %s;",
                updates,
            )
        conn.commit()
        total += len(updates)
        log.info("[%s] +%d (total=%d)", schema, len(updates), total)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--models-dir", type=Path, default=Path("models"))
    ap.add_argument(
        "--directions", nargs="+", choices=ALLOWED, default=list(ALLOWED),
    )
    args = ap.parse_args()

    dsn = os.environ.get("ROLETA_PG_DSN")
    if not dsn:
        log.error("ROLETA_PG_DSN nao setado")
        sys.exit(1)

    import psycopg2  # type: ignore

    from models.spin_encoder import SpinEncoder

    encoders = {}
    for schema in args.directions:
        path = args.models_dir / f"spin_autoencoder_{schema}.joblib"
        enc = SpinEncoder.load(path)
        if enc is None:
            log.warning("[%s] modelo ausente em %s — pulando.", schema, path)
            continue
        encoders[schema] = enc
    if not encoders:
        log.error("nenhum modelo carregado. Rode scripts/train_autoencoder.py antes.")
        sys.exit(2)

    conn = psycopg2.connect(dsn)
    try:
        grand = 0
        for schema, enc in encoders.items():
            grand += backfill_schema(conn, schema, enc, args.batch)
        log.info("backfill concluído: %d rows.", grand)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
