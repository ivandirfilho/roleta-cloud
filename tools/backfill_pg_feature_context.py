"""Backfill do contexto de features no PG (correção 06/08) — SÓ UPDATE.

Contexto do problema
--------------------
`cw/ccw.spin_features` chegou a produção com `dealer='unknown'` em 100% das
linhas e `spin_seq`/`direction_*`/`centro_previsto`/`gale_level` NULL em 100%,
mesmo com as colunas existindo desde as migrations 0007/0009/0010/0012: o
produtor nunca emitia o contexto e o worker nunca o projetava. Corrigido o
caminho ao vivo (flag `SDA_PG_FEATURE_CONTEXT`), as linhas ANTIGAS continuam
vazias — este utilitário as completa a partir do SQLite, que é a fonte
autoritativa de escrita.

Invioláveis deste script
------------------------
1. **Nunca INSERE.** Só `UPDATE` de linhas que já existem. Linha de feature
   ausente é ausência de evidência: fabricar desfecho seria inventar dado.
2. **Nunca sobrescreve.** O SET é por coluna (`COALESCE(col, %s)`; no `dealer`,
   `COALESCE(NULLIF(dealer,'unknown'), %s)`), então valor existente sobrevive e
   rodar duas vezes é no-op — idempotente por construção. O `WHERE` é
   **disjuntivo**: basta UMA coluna vazia para a linha valer uma visita. Com
   `AND` o reparo seria tudo-ou-nada e uma linha meio preenchida (caso real: o
   OCR corrige o dealer DEPOIS do publish) nunca mais seria alcançada.
3. **Nunca toca resultado.** `hit`, `spin_number`, `session_id` e as lag
   features (`recent_acc_*`, `streak_*`, `last_20_hits`) estão fora da
   allowlist e não podem ser alcançados.
4. **`--dry-run` é o default.** Gravar exige `--apply` explícito.
5. **Escopo congelado.** `max(decisions.id)` é lido UMA vez no início; linhas
   criadas durante a execução ficam para a próxima rodada, e o relatório diz
   quantas ficaram (`above_ceiling`, contagem read-only feita ao fim da
   varredura). `above_ceiling > 0` significa: rode de novo.
6. **Mesma normalização do runtime.** Os valores saem de
   `database.outbox_integration.build_pg_feature_context` — o mesmo helper que
   alimenta o caminho ao vivo. Sem isso, backfill e produção divergiriam.

Escopo de origem: `final_action='APOSTAR' AND result_actual IS NOT NULL`. É um
SUPERconjunto seguro das linhas que existem no PG (só decisões com predição
resolvida geram evento `spin_result`); o que não tiver linha de destino
simplesmente casa 0 rows e aparece na reconciliação como `target_absent`.

Uso:
    python tools/backfill_pg_feature_context.py --db data/decisions.db          # dry-run
    python tools/backfill_pg_feature_context.py --db ... --apply                # grava
    python tools/backfill_pg_feature_context.py --db ... --include-center-gale  # + centro/gale
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.outbox_integration import (  # noqa: E402
    _normalize_direction, build_pg_feature_context,
)

DEFAULT_DB = "/app/data/decisions.db"

# Allowlist ÚNICA de destinos: chave do contexto -> (identificador SQL, predicado).
# O predicado é o que garante "só preenche o que está vazio". `dealer` tem regra
# própria porque a coluna nasceu com DEFAULT 'unknown' (migration 0007) — ali o
# valor default É a ausência.
_NULL = "{col} IS NULL"
CONTEXT_TARGETS: dict[str, tuple[str, str]] = {
    "dealer": ("dealer", "(dealer IS NULL OR dealer = 'unknown')"),
    "dealer_table": ('"table"', _NULL.format(col='"table"')),
    "provider": ("provider", _NULL.format(col="provider")),
    "round_id": ("round_id", _NULL.format(col="round_id")),
    "wheel_model": ("wheel_model", _NULL.format(col="wheel_model")),
    "vision_confidence": ("vision_confidence", _NULL.format(col="vision_confidence")),
    "vision_source": ("vision_source", _NULL.format(col="vision_source")),
    "spin_seq": ("spin_seq", _NULL.format(col="spin_seq")),
    "direction_source": ("direction_source", _NULL.format(col="direction_source")),
    "direction_confidence": ("direction_confidence", _NULL.format(col="direction_confidence")),
    "direction_next": ("direction_next", _NULL.format(col="direction_next")),
    "phase_uncertain": ("phase_uncertain", _NULL.format(col="phase_uncertain")),
}
# Opt-in explícito: centro_previsto/gale_level são séries temporais e preenchê-las
# retroativamente cria uma descontinuidade (antes NULL, depois valor). Só com
# --include-center-gale.
CENTER_GALE_TARGETS: dict[str, tuple[str, str]] = {
    "centro_previsto": ("centro_previsto", _NULL.format(col="centro_previsto")),
    "applied_gale_level": ("gale_level", _NULL.format(col="gale_level")),
}

# Colunas que este script JAMAIS pode tocar (verificado em teste).
FORBIDDEN_COLUMNS = frozenset({
    "hit", "spin_number", "session_id", "decision_id", "id", "ts", "meta",
    "recent_acc_10", "recent_acc_50", "streak_miss", "streak_hit", "last_20_hits",
})


@dataclass(frozen=True)
class UpdatePlan:
    """Um UPDATE planejado para UMA linha de destino.

    O SET é **por coluna** (`COALESCE`), não por linha: cada coluna só recebe
    valor se estiver vazia, independentemente das outras. Sem isso, um único
    campo já preenchido bloquearia o reparo de todos os demais na mesma linha —
    cenário real, porque `update_last_vision()` corrige dealer/mesa DEPOIS do
    publish: a linha nasce com `spin_seq` preenchido e `dealer` vazio, e um
    `WHERE` conjuntivo nunca mais a alcançaria (o `ON CONFLICT DO NOTHING`
    também barra replay). O `WHERE` é disjuntivo pelo mesmo motivo: basta UMA
    coluna vazia para a linha valer uma visita.
    """
    schema: str
    decision_id: int
    columns: tuple[str, ...]
    values: tuple[Any, ...]

    @property
    def sql(self) -> str:
        sets = ", ".join(_SET_EXPR_BY_COLUMN[c] for c in self.columns)
        preds = " OR ".join(f"({p})" for p in self.predicates)
        return (
            f"UPDATE {self.schema}.spin_features SET {sets} "
            f"WHERE decision_id = %s AND ({preds})"
        )

    @property
    def predicates(self) -> tuple[str, ...]:
        return tuple(_PREDICATE_BY_COLUMN[c] for c in self.columns)

    @property
    def params(self) -> tuple[Any, ...]:
        return tuple(self.values) + (self.decision_id,)


_PREDICATE_BY_COLUMN: dict[str, str] = {
    col: pred for col, pred in
    list(CONTEXT_TARGETS.values()) + list(CENTER_GALE_TARGETS.values())
}
# Expressão de SET por coluna: preserva o valor existente e só preenche vazio.
# `dealer` precisa de NULLIF porque o DEFAULT 'unknown' do DDL (0007) É a
# ausência — sem isso, 'unknown' seria tratado como valor legítimo e nunca
# corrigido.
_SET_EXPR_BY_COLUMN: dict[str, str] = {
    col: (
        "dealer = COALESCE(NULLIF(dealer, 'unknown'), %s)" if col == "dealer"
        else f"{col} = COALESCE({col}, %s)"
    )
    for col in _PREDICATE_BY_COLUMN
}


@dataclass
class Stats:
    frozen_max_decision_id: Optional[int] = None
    scanned: int = 0
    above_ceiling: int = 0
    skipped_unknown_direction: int = 0
    skipped_no_context: int = 0
    planned: int = 0
    by_schema: dict = field(default_factory=dict)
    by_field: dict = field(default_factory=dict)
    samples: list = field(default_factory=list)
    applied_rows: int = 0
    target_absent: int = 0
    already_filled: int = 0

    def as_dict(self) -> dict:
        return {
            "frozen_max_decision_id": self.frozen_max_decision_id,
            "scanned": self.scanned,
            "above_ceiling": self.above_ceiling,
            "skipped_unknown_direction": self.skipped_unknown_direction,
            "skipped_no_context": self.skipped_no_context,
            "planned": self.planned,
            "by_schema": dict(self.by_schema),
            "by_field": dict(self.by_field),
            "samples": list(self.samples),
            "applied_rows": self.applied_rows,
            "target_absent": self.target_absent,
            "already_filled": self.already_filled,
        }


def freeze_max_decision_id(conn: sqlite3.Connection) -> Optional[int]:
    """Congela o topo do escopo ANTES de planejar (a origem segue crescendo)."""
    row = conn.execute("SELECT MAX(id) FROM decisions").fetchone()
    return int(row[0]) if row and row[0] is not None else None


def plan_updates(
    conn: sqlite3.Connection,
    *,
    include_center_gale: bool = False,
    limit: Optional[int] = None,
    frozen_max_id: Optional[int] = None,
    stats: Optional[Stats] = None,
) -> list[UpdatePlan]:
    """Lê o SQLite e devolve os UPDATEs candidatos. NÃO grava em lugar nenhum.

    `frozen_max_id` permite reexecutar com o MESMO teto de uma rodada anterior
    (reprodutibilidade); omitido, congela `max(decisions.id)` agora.
    """
    stats = stats if stats is not None else Stats()
    conn.row_factory = sqlite3.Row
    max_id = frozen_max_id if frozen_max_id is not None else freeze_max_decision_id(conn)
    stats.frozen_max_decision_id = max_id
    if max_id is None:
        return []
    targets = dict(CONTEXT_TARGETS)
    if include_center_gale:
        targets.update(CENTER_GALE_TARGETS)

    sql = (
        "SELECT * FROM decisions "
        "WHERE id <= ? AND final_action = 'APOSTAR' AND result_actual IS NOT NULL "
        "ORDER BY id"
    )
    params: list[Any] = [max_id]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))

    plans: list[UpdatePlan] = []
    for row in conn.execute(sql, params):
        stats.scanned += 1
        schema = _normalize_direction(row["spin_direction"] or "")
        if schema not in ("cw", "ccw"):
            # Sem sentido normalizado não há schema de destino: pular é a única
            # opção honesta (adivinhar cw/ccw contaminaria a série do sentido).
            stats.skipped_unknown_direction += 1
            continue
        context = build_pg_feature_context(row)
        if context is None:
            stats.skipped_no_context += 1
            continue
        columns: list[str] = []
        values: list[Any] = []
        for key, (column, _pred) in targets.items():
            value = context.get(key)
            if value is None:
                continue
            columns.append(column)
            values.append(value)
            stats.by_field[key] = stats.by_field.get(key, 0) + 1
        if not columns:
            stats.skipped_no_context += 1
            continue
        plan = UpdatePlan(schema, int(row["id"]), tuple(columns), tuple(values))
        plans.append(plan)
        stats.planned += 1
        stats.by_schema[schema] = stats.by_schema.get(schema, 0) + 1
        if len(stats.samples) < 8:
            stats.samples.append({
                "decision_id": plan.decision_id,
                "schema": schema,
                "sets": dict(zip(plan.columns, plan.values)),
            })
    # Cumpre a promessa do teto congelado: quantas linhas ELEGÍVEIS nasceram
    # acima dele durante a varredura. Leitura pura; `> 0` = rode de novo.
    above = conn.execute(
        "SELECT count(*) FROM decisions "
        "WHERE id > ? AND final_action = 'APOSTAR' AND result_actual IS NOT NULL",
        (max_id,),
    ).fetchone()
    stats.above_ceiling = int(above[0]) if above and above[0] is not None else 0
    return plans


def _assert_allowlisted(plans: Iterable[UpdatePlan]) -> None:
    """Cinto de segurança em runtime: nada fora da allowlist chega ao banco."""
    allowed = {c for c, _ in CONTEXT_TARGETS.values()} | {
        c for c, _ in CENTER_GALE_TARGETS.values()}
    for plan in plans:
        for column in plan.columns:
            if column not in allowed:
                raise ValueError(f"coluna fora da allowlist: {column!r}")
            if column.strip('"') in FORBIDDEN_COLUMNS:
                raise ValueError(f"coluna proibida: {column!r}")


def apply_plans(pg_conn, plans: list[UpdatePlan], *, batch_size: int = 200,
                stats: Optional[Stats] = None) -> Stats:
    """Executa os UPDATEs em transações por lote. Só é chamado com --apply."""
    stats = stats if stats is not None else Stats()
    _assert_allowlisted(plans)
    for start in range(0, len(plans), batch_size):
        batch = plans[start:start + batch_size]
        cur = pg_conn.cursor()
        try:
            for plan in batch:
                cur.execute(plan.sql, plan.params)
                touched = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                if touched:
                    stats.applied_rows += touched
                    continue
                # rowcount 0 tem DUAS causas muito diferentes; confundi-las
                # esconderia exatamente o que o relatório precisa denunciar.
                cur.execute(
                    f"SELECT 1 FROM {plan.schema}.spin_features "
                    "WHERE decision_id = %s LIMIT 1",
                    (plan.decision_id,),
                )
                if cur.fetchone() is None:
                    stats.target_absent += 1   # linha ainda não existe no PG
                else:
                    stats.already_filled += 1  # nada a preencher (idempotência)
        finally:
            cur.close()
        pg_conn.commit()
    return stats


def reconcile(pg_conn, schemas: Iterable[str] = ("cw", "ccw")) -> dict:
    """Fill-rate por coluna DEPOIS da execução (prova, não promessa)."""
    out: dict[str, dict] = {}
    cur = pg_conn.cursor()
    try:
        for schema in schemas:
            counts: dict[str, Any] = {}
            cur.execute(f"SELECT count(*) FROM {schema}.spin_features")
            row = cur.fetchone()
            counts["rows"] = row[0] if row else 0
            for _key, (column, predicate) in {
                **CONTEXT_TARGETS, **CENTER_GALE_TARGETS,
            }.items():
                cur.execute(
                    f"SELECT count(*) FROM {schema}.spin_features WHERE {predicate}"
                )
                row = cur.fetchone()
                counts[f"empty_{column.strip(chr(34))}"] = row[0] if row else 0
            out[schema] = counts
    finally:
        cur.close()
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite de origem")
    ap.add_argument("--dsn", default=None,
                    help="DSN do PG (default: env ROLETA_PG_DSN)")
    ap.add_argument("--apply", action="store_true",
                    help="grava de fato (sem isto, dry-run)")
    ap.add_argument("--include-center-gale", action="store_true",
                    help="tambem preenche centro_previsto/gale_level (cria "
                         "descontinuidade na serie temporal — opt-in)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--batch", type=int, default=200)
    ap.add_argument("--json", action="store_true", help="saida em JSON")
    args = ap.parse_args(argv)

    if not Path(args.db).exists():
        print(f"[bf-ctx] DB nao encontrado: {args.db}", file=sys.stderr)
        return 2

    stats = Stats()
    conn = sqlite3.connect(args.db)
    try:
        plans = plan_updates(
            conn, include_center_gale=args.include_center_gale,
            limit=args.limit, stats=stats,
        )
    finally:
        conn.close()
    _assert_allowlisted(plans)

    reconciliation: dict = {}
    if args.apply:
        import os

        dsn = args.dsn or os.environ.get("ROLETA_PG_DSN")
        if not dsn:
            print("[bf-ctx] --apply exige --dsn ou ROLETA_PG_DSN", file=sys.stderr)
            return 2
        import psycopg2  # import tardio: dry-run nao precisa do driver

        pg = psycopg2.connect(dsn)
        try:
            pg.autocommit = False
            apply_plans(pg, plans, batch_size=args.batch, stats=stats)
            reconciliation = reconcile(pg)
        finally:
            pg.close()

    payload = stats.as_dict()
    payload["mode"] = "apply" if args.apply else "dry-run"
    payload["include_center_gale"] = args.include_center_gale
    if reconciliation:
        payload["reconciliation"] = reconciliation
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"[bf-ctx] modo            : {payload['mode']}")
    print(f"[bf-ctx] max decision_id : {stats.frozen_max_decision_id} (congelado)")
    print(f"[bf-ctx] acima do teto   : {stats.above_ceiling} (>0 = rode de novo)")
    print(f"[bf-ctx] scanned         : {stats.scanned}")
    print(f"[bf-ctx] planned         : {stats.planned}")
    print(f"[bf-ctx] sem sentido     : {stats.skipped_unknown_direction}")
    print(f"[bf-ctx] sem contexto    : {stats.skipped_no_context}")
    print(f"[bf-ctx] por schema      : {stats.by_schema}")
    print("[bf-ctx] por campo       :")
    for key, count in sorted(stats.by_field.items(), key=lambda kv: -kv[1]):
        print(f"  {count:<7} {key}")
    print("[bf-ctx] amostras        :")
    for sample in stats.samples:
        print(f"  {sample}")
    if args.apply:
        print(f"[bf-ctx] linhas alteradas: {stats.applied_rows}")
        print(f"[bf-ctx] alvo ausente    : {stats.target_absent} (linha ainda nao existe no PG)")
        print(f"[bf-ctx] ja preenchido   : {stats.already_filled} (nada a fazer)")
        print(f"[bf-ctx] reconciliacao   : {reconciliation}")
    else:
        print("[bf-ctx] dry-run — nada gravado (use --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
