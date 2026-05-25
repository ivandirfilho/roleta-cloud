"""Script offline de treino do SpinEncoder (S7).

Le features 6d de cw.spins_vectors + ccw.spins_vectors, treina PCA(4),
salva em models/spin_autoencoder.joblib.

Uso:
    ROLETA_PG_DSN="postgresql://..." python scripts/train_autoencoder.py
    ROLETA_PG_DSN=... python scripts/train_autoencoder.py --min-rows 100

Se nao houver dados suficientes (default 100 rows), aborta com codigo 2.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_autoencoder")


def fetch_features(dsn: str, min_rows: int):
    import psycopg2  # type: ignore
    import numpy as np  # type: ignore

    rows: list[list[float]] = []
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            for schema in ("cw", "ccw"):
                # Cast vector -> float[] para evitar depender do adaptador
                # pgvector no psycopg2 (que costuma devolver str).
                cur.execute(
                    f"SELECT raw_features::float[] FROM {schema}.spins_vectors "
                    f"WHERE raw_features IS NOT NULL ORDER BY id DESC LIMIT 50000;"
                )
                for (vec,) in cur.fetchall():
                    if vec is None:
                        continue
                    # Tolerar str (fallback) e list.
                    if isinstance(vec, str):
                        s = vec.strip().lstrip("[").rstrip("]")
                        try:
                            vec = [float(x) for x in s.split(",") if x.strip()]
                        except ValueError:
                            continue
                    if len(vec) == 6:
                        rows.append([float(x) for x in vec])
    finally:
        conn.close()
    log.info("coletadas %d rows", len(rows))
    if len(rows) < min_rows:
        log.error("dados insuficientes (%d < %d). Aborta.", len(rows), min_rows)
        sys.exit(2)
    return np.asarray(rows, dtype=float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-rows", type=int, default=100)
    ap.add_argument("--out", type=Path, default=Path("models/spin_autoencoder.joblib"))
    args = ap.parse_args()

    dsn = os.environ.get("ROLETA_PG_DSN")
    if not dsn:
        log.error("ROLETA_PG_DSN nao setado")
        sys.exit(1)

    X = fetch_features(dsn, args.min_rows)
    from models.spin_encoder import train_pca, save_encoder
    model = train_pca(X, n_components=4)
    save_encoder(model, args.out, kind="pca")
    log.info("OK. explained_variance_ratio=%s", model.explained_variance_ratio_.tolist())


if __name__ == "__main__":
    main()
