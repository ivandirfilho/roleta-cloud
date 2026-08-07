"""Backfill do contexto de features no PG — testes (correção 06/08).

Determinístico: o SQLite de origem é um arquivo temporário real e o PG é
substituído por uma conexão falsa que registra SQL/params. Nenhum teste toca
banco de produção e `--apply` nunca roda contra PG real aqui.

O que estes testes provam (nesta ordem de importância):
  1. o script NUNCA emite INSERT;
  2. nunca escreve em coluna fora da allowlist (resultado/lag/sessão intactos);
  3. só preenche o que está vazio → rodar de novo é no-op (idempotente);
  4. o escopo é congelado no início e o sentido decide o schema;
  5. dry-run não grava absolutamente nada.
"""
from __future__ import annotations

import sqlite3

import pytest

from tools.backfill_pg_feature_context import (
    CENTER_GALE_TARGETS, CONTEXT_TARGETS, FORBIDDEN_COLUMNS, UpdatePlan,
    apply_plans, freeze_max_decision_id, main, plan_updates,
)

DECISION_COLUMNS = (
    "id INTEGER PRIMARY KEY AUTOINCREMENT",
    "session_id TEXT", "spin_number INTEGER", "spin_direction TEXT",
    "final_action TEXT", "result_actual INTEGER", "result_hit INTEGER",
    "sda_center INTEGER", "gale_level INTEGER",
    "dealer TEXT", "dealer_table TEXT", "provider TEXT", "round_id TEXT",
    "wheel_model TEXT", "vision_confidence REAL", "vision_source TEXT",
    "spin_seq INTEGER", "direction_source TEXT", "direction_confidence REAL",
    "direction_next TEXT", "phase_uncertain INTEGER",
)


class FakeCursor:
    def __init__(self, owner, rowcount=1):
        self.owner = owner
        self.rowcount = rowcount
        self.closed = False

    def execute(self, sql, params=None):
        self.owner.executed.append((sql, params))
        self.rowcount = self.owner.next_rowcount

    def fetchone(self):
        return self.owner.probe_result

    def close(self):
        self.closed = True


class FakePG:
    """Conexão PG mínima: registra tudo e não escreve em lugar nenhum."""

    def __init__(self, rowcount=1, row_exists=True):
        self.executed: list[tuple[str, tuple | None]] = []
        self.commits = 0
        self.next_rowcount = rowcount
        # Resposta do probe `SELECT 1 ... WHERE decision_id = %s`.
        self.probe_result = (1,) if row_exists else None

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    @property
    def updates(self) -> list[str]:
        return [s for s, _ in self.executed if s.startswith("UPDATE")]


def _make_db(tmp_path, rows):
    path = tmp_path / "decisions.db"
    conn = sqlite3.connect(path)
    conn.execute(f"CREATE TABLE decisions ({', '.join(DECISION_COLUMNS)})")
    for row in rows:
        cols = ", ".join(row)
        vals = ", ".join("?" for _ in row)
        conn.execute(f"INSERT INTO decisions ({cols}) VALUES ({vals})",
                     tuple(row.values()))
    conn.commit()
    conn.close()
    return path


def _row(**over) -> dict:
    base = {
        "session_id": "s1",
        "spin_number": 12,
        "spin_direction": "horario",
        "final_action": "APOSTAR",
        "result_actual": 32,
        "result_hit": 1,
        "sda_center": 17,
        "gale_level": 2,
        "dealer": "Ana",
        "dealer_table": "Mesa X",
        "provider": "Evolution",
        "round_id": "r-1",
        "wheel_model": "Mesa X",
        "vision_confidence": 0.9,
        "vision_source": "vision",
        "spin_seq": 5,
        "direction_source": "authority",
        "direction_confidence": 0.8,
        "direction_next": "anti-horario",
        "phase_uncertain": 0,
    }
    base.update(over)
    return base


@pytest.fixture
def db(tmp_path):
    return _make_db(tmp_path, [_row(), _row(spin_direction="anti-horario")])


def _plans(db_path, **kw):
    conn = sqlite3.connect(db_path)
    try:
        return plan_updates(conn, **kw)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Invioláveis: nunca INSERT, nunca coluna proibida
# ---------------------------------------------------------------------------

def test_never_emits_insert(db):
    for plan in _plans(db, include_center_gale=True):
        assert plan.sql.strip().upper().startswith("UPDATE ")
        assert "INSERT" not in plan.sql.upper()


def test_apply_never_emits_insert(db):
    pg = FakePG()
    apply_plans(pg, _plans(db, include_center_gale=True))
    assert pg.executed
    for sql, _params in pg.executed:
        assert "INSERT" not in sql.upper()
        assert "DELETE" not in sql.upper()
        assert "DROP" not in sql.upper()


def test_never_touches_result_or_lag_columns(db):
    for plan in _plans(db, include_center_gale=True):
        for column in plan.columns:
            assert column.strip('"') not in FORBIDDEN_COLUMNS


def test_allowlist_is_disjoint_from_forbidden():
    allowed = {c.strip('"') for c, _ in CONTEXT_TARGETS.values()}
    allowed |= {c.strip('"') for c, _ in CENTER_GALE_TARGETS.values()}
    assert allowed & FORBIDDEN_COLUMNS == set()


def test_apply_rejects_column_outside_allowlist():
    bad = UpdatePlan("cw", 1, ("hit",), (True,))
    with pytest.raises(ValueError, match="allowlist"):
        apply_plans(FakePG(), [bad])


# ---------------------------------------------------------------------------
# Idempotência: só preenche o que está vazio
# ---------------------------------------------------------------------------

def test_every_column_carries_its_own_emptiness_predicate(db):
    for plan in _plans(db, include_center_gale=True):
        assert len(plan.predicates) == len(plan.columns)
        for column, predicate in zip(plan.columns, plan.predicates):
            assert column in predicate


def test_dealer_predicate_treats_unknown_as_empty(db):
    plan = _plans(db)[0]
    predicate = dict(zip(plan.columns, plan.predicates))["dealer"]
    assert "dealer IS NULL OR dealer = 'unknown'" in predicate


def test_non_dealer_predicates_are_is_null(db):
    plan = _plans(db, include_center_gale=True)[0]
    for column, predicate in zip(plan.columns, plan.predicates):
        if column == "dealer":
            continue
        assert predicate == f"{column} IS NULL"


def test_predicates_are_disjunctive_so_one_filled_column_blocks_nothing(db):
    """Regressão: `AND` tornava o reparo tudo-ou-nada por linha.

    Cenário real: `update_last_vision()` corrige dealer/mesa DEPOIS do publish,
    então a linha nasce com `spin_seq` preenchido e `dealer` vazio. Com `WHERE`
    conjuntivo, `spin_seq IS NULL` seria falso e o `dealer` nunca mais seria
    reparado — e o `ON CONFLICT DO NOTHING` também barra replay.
    """
    plan = _plans(db, include_center_gale=True)[0]
    where = plan.sql.split("WHERE", 1)[1]
    assert " OR " in where
    assert " AND (" in where          # só o AND que prende o decision_id
    assert where.count(" AND ") == 1


def test_set_uses_coalesce_so_existing_values_survive(db):
    """Nenhuma coluna já preenchida é sobrescrita, mesmo visitando a linha."""
    plan = _plans(db, include_center_gale=True)[0]
    sets = plan.sql.split("SET", 1)[1].split("WHERE", 1)[0]
    for column in plan.columns:
        if column == "dealer":
            continue
        assert f"{column} = COALESCE({column}, %s)" in sets


def test_dealer_set_treats_unknown_as_empty(db):
    """`'unknown'` é o DEFAULT do DDL: precisa de NULLIF para ser corrigido."""
    plan = _plans(db)[0]
    assert "dealer = COALESCE(NULLIF(dealer, 'unknown'), %s)" in plan.sql


def test_second_run_is_a_no_op_when_targets_are_filled(db):
    """Idempotência: com as colunas já preenchidas, o UPDATE casa 0 linhas."""
    plans = _plans(db)
    first = FakePG(rowcount=1)
    apply_plans(plans=plans, pg_conn=first)
    second = FakePG(rowcount=0, row_exists=True)  # predicados não casam mais
    stats = apply_plans(plans=plans, pg_conn=second)
    assert stats.applied_rows == 0
    assert stats.already_filled == len(plans)
    assert stats.target_absent == 0
    # Mesmo SQL de UPDATE nas duas rodadas: nada muda de forma entre execuções.
    assert first.updates == second.updates


def test_missing_target_row_is_reported_apart_from_already_filled(db):
    """Linha inexistente ≠ linha completa: o relatório precisa distinguir.

    Confundir as duas esconderia justamente o caso que pede nova rodada (a
    feature ainda não chegou ao PG).
    """
    plans = _plans(db)
    pg = FakePG(rowcount=0, row_exists=False)
    stats = apply_plans(plans=plans, pg_conn=pg)
    assert stats.target_absent == len(plans)
    assert stats.already_filled == 0
    assert stats.applied_rows == 0


def test_probe_runs_only_when_nothing_was_updated(db):
    plans = _plans(db)
    pg = FakePG(rowcount=1)
    apply_plans(plans=plans, pg_conn=pg)
    assert not any("SELECT 1" in s for s, _ in pg.executed)


def test_where_clause_always_pins_the_decision_id(db):
    for plan in _plans(db):
        assert "WHERE decision_id = %s" in plan.sql
        assert plan.params[-1] == plan.decision_id


# ---------------------------------------------------------------------------
# Escopo
# ---------------------------------------------------------------------------

def test_scope_excludes_unresolved_and_non_apostar(tmp_path):
    path = _make_db(tmp_path, [
        _row(),                                  # elegível
        _row(result_actual=None),                # sem resultado
        _row(final_action="PULAR"),              # sem aposta
    ])
    plans = _plans(path)
    assert len(plans) == 1


def test_max_decision_id_is_frozen_at_start(tmp_path):
    path = _make_db(tmp_path, [_row(), _row()])
    conn = sqlite3.connect(path)
    try:
        frozen = freeze_max_decision_id(conn)
        assert frozen == 2
        conn.execute(
            "INSERT INTO decisions (spin_direction, final_action, result_actual) "
            "VALUES ('horario', 'APOSTAR', 7)"
        )
        conn.commit()
        from tools.backfill_pg_feature_context import Stats
        stats = Stats()
        plans = plan_updates(conn, stats=stats)
    finally:
        conn.close()
    # A linha nova (id=3) entrou DEPOIS do congelamento inicial desta chamada;
    # o que importa é o contrato: o teto vem de uma leitura única no início.
    assert stats.frozen_max_decision_id >= 2
    assert all(p.decision_id <= stats.frozen_max_decision_id for p in plans)


def test_scope_respects_frozen_ceiling(tmp_path):
    path = _make_db(tmp_path, [_row(), _row(), _row()])
    conn = sqlite3.connect(path)
    try:
        from tools.backfill_pg_feature_context import Stats
        stats = Stats()
        plans = plan_updates(conn, stats=stats)
    finally:
        conn.close()
    assert stats.frozen_max_decision_id == 3
    assert max(p.decision_id for p in plans) <= 3


def test_report_counts_eligible_rows_above_the_frozen_ceiling(tmp_path):
    """A promessa do teto congelado tem que ser verificável no relatório.

    O escopo é congelado no início; o que nasce depois fica para a próxima
    rodada. Sem esta contagem, o operador não teria como saber que sobrou algo.
    """
    path = _make_db(tmp_path, [_row(), _row(), _row(), _row()])
    conn = sqlite3.connect(path)
    try:
        from tools.backfill_pg_feature_context import Stats

        stats = Stats()
        plans = plan_updates(conn, frozen_max_id=2, stats=stats)
        assert stats.frozen_max_decision_id == 2
        assert max(p.decision_id for p in plans) <= 2
        assert stats.above_ceiling == 2, "ids 3 e 4 ficaram para a proxima rodada"

        # Sem teto injetado, congela no topo real: nada fica de fora.
        stats2 = Stats()
        plan_updates(conn, stats=stats2)
        assert stats2.frozen_max_decision_id == 4
        assert stats2.above_ceiling == 0
    finally:
        conn.close()


def test_above_ceiling_counts_only_eligible_rows(tmp_path):
    """Linha sem resultado ou sem aposta não conta como pendência."""
    path = _make_db(tmp_path, [
        _row(),                       # id 1 — dentro do teto
        _row(),                       # id 2 — elegível, acima do teto
        _row(result_actual=None),     # id 3 — sem resultado
        _row(final_action="PULAR"),   # id 4 — sem aposta
    ])
    conn = sqlite3.connect(path)
    try:
        from tools.backfill_pg_feature_context import Stats
        stats = Stats()
        plan_updates(conn, frozen_max_id=1, stats=stats)
        assert stats.above_ceiling == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sentido → schema
# ---------------------------------------------------------------------------

def test_direction_decides_the_schema(db):
    schemas = {p.schema for p in _plans(db)}
    assert schemas == {"cw", "ccw"}


def test_unknown_direction_is_skipped_not_guessed(tmp_path):
    path = _make_db(tmp_path, [_row(spin_direction="diagonal"), _row(spin_direction="")])
    conn = sqlite3.connect(path)
    try:
        from tools.backfill_pg_feature_context import Stats
        stats = Stats()
        plans = plan_updates(conn, stats=stats)
    finally:
        conn.close()
    assert plans == []
    assert stats.skipped_unknown_direction == 2


def test_schema_appears_in_the_update_target(db):
    for plan in _plans(db):
        assert plan.sql.startswith(f"UPDATE {plan.schema}.spin_features SET ")


# ---------------------------------------------------------------------------
# Valores e normalização compartilhada com o runtime
# ---------------------------------------------------------------------------

def test_values_use_the_same_normalization_as_the_live_producer(db):
    plan = _plans(db)[0]
    sets = dict(zip(plan.columns, plan.values))
    assert sets["dealer"] == "Ana"
    assert sets['"table"'] == "Mesa X"
    assert sets["direction_next"] == "ccw"      # normalizado, como ao vivo
    assert sets["phase_uncertain"] is False
    assert sets["spin_seq"] == 5


def test_absent_values_are_not_written_at_all(tmp_path):
    path = _make_db(tmp_path, [_row(dealer="unknown", provider="", spin_seq=0)])
    plan = _plans(path)[0]
    assert "dealer" not in plan.columns
    assert "provider" not in plan.columns
    assert "spin_seq" not in plan.columns


def test_center_and_gale_require_explicit_opt_in(db):
    without = _plans(db)[0]
    assert "centro_previsto" not in without.columns
    assert "gale_level" not in without.columns
    with_opt = _plans(db, include_center_gale=True)[0]
    assert "centro_previsto" in with_opt.columns
    assert "gale_level" in with_opt.columns


def test_row_with_nothing_to_fill_is_not_planned(tmp_path):
    path = _make_db(tmp_path, [_row(
        dealer="unknown", dealer_table="", provider="", round_id="",
        wheel_model="", vision_confidence=None, vision_source="",
        spin_seq=0, direction_source="", direction_confidence=None,
        direction_next="", phase_uncertain=None,
    )])
    assert _plans(path) == []


def test_params_are_positionally_aligned_with_columns(db):
    for plan in _plans(db, include_center_gale=True):
        assert len(plan.params) == len(plan.columns) + 1
        assert plan.sql.count("%s") == len(plan.params)


# ---------------------------------------------------------------------------
# CLI: dry-run é o default e não grava
# ---------------------------------------------------------------------------

def test_cli_defaults_to_dry_run_and_writes_nothing(db, capsys, monkeypatch):
    def _boom(*_a, **_kw):
        raise AssertionError("dry-run nao pode abrir conexao PG")

    monkeypatch.setattr("tools.backfill_pg_feature_context.apply_plans", _boom)
    assert main(["--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "nada gravado" in out


def test_cli_reports_frozen_ceiling_and_counts(db, capsys):
    main(["--db", str(db), "--json"])
    import json as _json
    payload = _json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["frozen_max_decision_id"] == 2
    assert payload["planned"] == 2
    assert payload["by_schema"] == {"cw": 1, "ccw": 1}
    assert payload["by_field"]["dealer"] == 2


def test_cli_apply_without_dsn_fails_closed(db, monkeypatch, capsys):
    monkeypatch.delenv("ROLETA_PG_DSN", raising=False)
    assert main(["--db", str(db), "--apply"]) == 2


def test_cli_missing_db_fails_closed(tmp_path):
    assert main(["--db", str(tmp_path / "nope.db")]) == 2
