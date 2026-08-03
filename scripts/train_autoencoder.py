"""Script offline de treino do SpinEncoder — POR SENTIDO (S7 + H5 03/08).

CW e CCW são fenômenos físicos distintos (§4.0 evolução_03_08.md): treinar
uma pool única contaminaria o espaço latente com o delta entre sentidos.
Este script treina UM modelo por schema:

    models/spin_autoencoder_cw.joblib
    models/spin_autoencoder_ccw.joblib

Modelo = Pipeline(StandardScaler → PCA(4, whiten)) — normaliza a ENTRADA
(6 dims com escalas distintas) antes do PCA. `.transform` mantém a API do
SpinEncoder.encode.

Uso:
    ROLETA_PG_DSN="postgresql://..." python scripts/train_autoencoder.py
    ROLETA_PG_DSN=... python scripts/train_autoencoder.py --min-rows 100
    ROLETA_PG_DSN=... python scripts/train_autoencoder.py --directions cw

Se um sentido não tiver dados suficientes (default 100 rows), ele é PULADO
(não aborta o outro). Sai com código 2 se NENHUM modelo foi treinado.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Garante que /app (raiz do repo) está no sys.path quando rodado como
# `python scripts/train_autoencoder.py` — senão `models.spin_encoder` falha.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train_autoencoder")

ALLOWED = ("cw", "ccw")


def fetch_features(dsn: str, schema: str):
    """Lê features 6d de UM schema (cw|ccw). Retorna np.ndarray (n, 6)."""
    import numpy as np  # type: ignore
    import psycopg2  # type: ignore

    if schema not in ALLOWED:
        raise ValueError(f"schema invalido: {schema}")
    rows: list[list[float]] = []
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            # Cast vector -> text para evitar depender do adaptador
            # pgvector no psycopg2 (que costuma devolver str).
            cur.execute(
                f"SELECT raw_features::text FROM {schema}.spins_vectors "
                f"WHERE raw_features IS NOT NULL ORDER BY id DESC LIMIT 50000;"
            )
            for (vec,) in cur.fetchall():
                if vec is None:
                    continue
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
    log.info("[%s] coletadas %d rows", schema, len(rows))
    return np.asarray(rows, dtype=float)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-rows", type=int, default=100)
    ap.add_argument("--out-dir", type=Path, default=Path("models"))
    ap.add_argument(
        "--directions", nargs="+", choices=ALLOWED, default=list(ALLOWED),
        help="sentidos a treinar (default: cw ccw)",
    )
    args = ap.parse_args()

    dsn = os.environ.get("ROLETA_PG_DSN")
    if not dsn:
        log.error("ROLETA_PG_DSN nao setado")
        sys.exit(1)

    from models.spin_encoder import save_encoder, train_pipeline

    trained = 0
    for schema in args.directions:
        X = fetch_features(dsn, schema)
        if len(X) < args.min_rows:
            log.warning(
                "[%s] dados insuficientes (%d < %d). Pulando este sentido.",
                schema, len(X), args.min_rows,
            )
            continue
        model = train_pipeline(X, n_components=4)
        out = args.out_dir / f"spin_autoencoder_{schema}.joblib"
        save_encoder(model, out, kind="pca_pipeline")
        evr = model.named_steps["pca"].explained_variance_ratio_
        log.info(
            "[%s] OK -> %s | explained_variance_ratio=%s (soma=%.4f)",
            schema, out, evr.tolist(), float(evr.sum()),
        )
        trained += 1

    if trained == 0:
        log.error("nenhum modelo treinado. Aborta.")
        sys.exit(2)


if __name__ == "__main__":
    main()
