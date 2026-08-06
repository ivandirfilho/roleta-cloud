"""CDC worker — projeção do contexto da decisão (correção 06/08).

Determinístico e SEM PostgreSQL: `_apply_spin_result` recebe um cursor falso que
grava o SQL e os parâmetros. Isso permite provar, no CI comum, exatamente o que
seria escrito no banco — inclusive a coluna citada `"table"` e a garantia de que
`spin_number` continua sendo o número REAL do resultado.

`tests/test_cdc_worker.py` continua cobrindo o caminho com PG real; aqui o alvo é
o contrato de colunas/valores, que é justamente o que estava sem rede.
"""
from __future__ import annotations

import re

import pytest

from workers import cdc_worker
from workers.cdc_worker import _apply_spin_result, build_context_columns

FLAG = "SDA_PG_FEATURE_CONTEXT"

# SQL legado, congelado: qualquer divergência com a flag OFF é regressão.
LEGACY_INSERT = (
    "INSERT INTO {schema}.spin_features "
    "(decision_id, spin_number, hit, centro_previsto, gale_level, "
    "recent_acc_10, recent_acc_50, streak_miss, streak_hit, "
    "last_20_hits, meta, session_id) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (decision_id) WHERE decision_id IS NOT NULL DO NOTHING;"
)


class FakeCursor:
    """Cursor mínimo: registra execuções e devolve janela de lag vazia."""

    def __init__(self, window_rows=None):
        self.executed: list[tuple[str, tuple | None]] = []
        self._window_rows = window_rows or []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._window_rows

    @property
    def insert(self) -> tuple[str, tuple]:
        for sql, params in self.executed:
            if "INSERT INTO" in sql:
                return sql, params
        raise AssertionError("nenhum INSERT executado")

    @property
    def queries(self) -> list[str]:
        return [sql for sql, _ in self.executed]


def _norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _insert_columns(sql: str) -> list[str]:
    inner = sql.split("spin_features", 1)[1].split("(", 1)[1].split(")", 1)[0]
    return [c.strip() for c in inner.split(",")]


def _insert_map(cursor: FakeCursor) -> dict:
    sql, params = cursor.insert
    return dict(zip(_insert_columns(sql), params))


def _context(**over) -> dict:
    ctx = {
        "decision_id": 501,
        "session_id": "sess-1",
        "dealer": "Ana",
        "dealer_table": "Roleta ao Vivo",
        "provider": "Evolution",
        "round_id": "r-77",
        "wheel_model": "Roleta ao Vivo",
        "vision_confidence": 0.9,
        "vision_source": "vision",
        "spin_seq": 12,
        "direction_source": "authority",
        "direction_confidence": 0.8,
        "direction_next": "ccw",
        "phase_uncertain": False,
        "centro_previsto": 17,
        "applied_gale_level": 2,
    }
    ctx.update(over)
    return ctx


def _payload(direction="cw", **over) -> dict:
    p = {
        "event_type": "spin_result",
        "direction": direction,
        "decision_id": 501,
        "hit": True,
        "actual_number": 32,
        "session_id": "sess-1",
    }
    p.update(over)
    return p


@pytest.fixture(autouse=True)
def _clear_flag(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


# ---------------------------------------------------------------------------
# Flag OFF — caminho legado intocado
# ---------------------------------------------------------------------------

def test_flag_off_emits_exact_legacy_sql_and_params():
    cur = FakeCursor()
    _apply_spin_result(cur, _payload())
    sql, params = cur.insert
    assert _norm(sql) == LEGACY_INSERT.format(schema="cw")
    assert params == (501, 32, True, None, None, None, None, 0, 0, [True],
                      params[10], "sess-1")


def test_flag_off_ignores_context_and_adds_no_query():
    """Produtor ON + worker OFF: payload extra é ignorado com segurança."""
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context()))
    sql, params = cur.insert
    assert _norm(sql) == LEGACY_INSERT.format(schema="cw")
    assert "Ana" not in params
    # Só a window query de lag features + o INSERT. Nada de leitura extra.
    assert len(cur.executed) == 2
    assert not any("spins_vectors" in q for q in cur.queries)


def test_flag_off_never_reads_other_tables():
    cur = FakeCursor()
    _apply_spin_result(cur, _payload())
    assert all("spin_features" in q for q in cur.queries)


# ---------------------------------------------------------------------------
# Flag ON — projeção completa
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("direction,schema", [("cw", "cw"), ("ccw", "ccw")])
def test_flag_on_projects_full_context_both_directions(monkeypatch, direction, schema):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(direction=direction, context=_context()))
    sql, _ = cur.insert
    assert f"INSERT INTO {schema}.spin_features" in sql
    row = _insert_map(cur)
    assert row["dealer"] == "Ana"
    assert row['"table"'] == "Roleta ao Vivo"
    assert row["provider"] == "Evolution"
    assert row["round_id"] == "r-77"
    assert row["wheel_model"] == "Roleta ao Vivo"
    assert row["vision_confidence"] == 0.9
    assert row["vision_source"] == "vision"
    assert row["spin_seq"] == 12
    assert row["direction_source"] == "authority"
    assert row["direction_confidence"] == 0.8
    assert row["direction_next"] == "ccw"
    assert row["phase_uncertain"] is False
    assert row["centro_previsto"] == 17
    assert row["gale_level"] == 2


def test_flag_on_uses_quoted_table_column(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context()))
    sql, _ = cur.insert
    assert '"table"' in _insert_columns(sql)
    # `table` sem aspas seria erro de sintaxe no PG.
    assert ", table," not in _norm(sql)


def test_flag_on_keeps_actual_number_as_spin_number(monkeypatch):
    """Contexto com spin_number NÃO sobrescreve o número real do resultado."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    ctx = _context()
    ctx["spin_number"] = 7  # tentativa de sequestro
    _apply_spin_result(cur, _payload(actual_number=32, context=ctx))
    assert _insert_map(cur)["spin_number"] == 32


def test_flag_on_keeps_on_conflict_clause_unchanged(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context()))
    sql, _ = cur.insert
    assert ("ON CONFLICT (decision_id) WHERE decision_id IS NOT NULL DO NOTHING"
            in _norm(sql))


def test_flag_on_keeps_placeholder_count_in_sync(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context()))
    sql, params = cur.insert
    assert len(_insert_columns(sql)) == len(params)
    assert _norm(sql).count("%s") == len(params)


def test_flag_on_top_level_session_id_wins(monkeypatch):
    """session_id do evento é autoritativo mesmo com contexto divergente."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(
        cur, _payload(session_id="sess-nova",
                      context=_context(session_id="sess-velha")),
    )
    assert _insert_map(cur)["session_id"] == "sess-nova"


def test_session_mismatch_still_projects_context(monkeypatch):
    """Reset de sessão não invalida o dealer observado na decisão."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(
        cur, _payload(session_id="sess-nova",
                      context=_context(session_id="sess-velha")),
    )
    assert _insert_map(cur)["dealer"] == "Ana"


# ---------------------------------------------------------------------------
# Fail-soft: contexto ruim nunca derruba a linha essencial
# ---------------------------------------------------------------------------

def test_context_from_another_decision_is_rejected(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(
        cur, _payload(decision_id=501, context=_context(decision_id=999)),
    )
    sql, params = cur.insert
    assert _norm(sql) == LEGACY_INSERT.format(schema="cw")
    assert "Ana" not in params


@pytest.mark.parametrize("bad", ["nao-e-dict", 42, ["a"], True])
def test_malformed_context_falls_back_to_legacy_row(monkeypatch, bad):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=bad))
    sql, params = cur.insert
    assert _norm(sql) == LEGACY_INSERT.format(schema="cw")
    assert params[0] == 501 and params[1] == 32 and params[2] is True


def test_garbage_values_become_null_without_dlq(monkeypatch):
    """Valor inválido vira NULL; o resultado essencial continua gravado."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    ctx = _context(spin_seq="doze", vision_confidence="alta",
                   phase_uncertain="talvez", dealer={"nested": 1})
    _apply_spin_result(cur, _payload(context=ctx))
    row = _insert_map(cur)
    assert row["spin_seq"] is None
    assert row["vision_confidence"] is None
    assert row["phase_uncertain"] is None
    assert row["dealer"] is None
    assert row["hit"] is True and row["spin_number"] == 32


@pytest.mark.parametrize("value", [
    float("inf"), float("-inf"), 10 ** 400, -(10 ** 400), 1e400,
])
def test_out_of_range_numbers_never_escape_the_coercion(monkeypatch, value):
    """OverflowError é ArithmeticError, não ValueError.

    Um número absurdo vindo do JSONB (o `numeric` do PG não tem teto) faria
    `int()`/`float()` levantar OverflowError, que escaparia até o savepoint e
    mandaria o resultado essencial para a DLQ — exatamente o que a coerção
    total existe para impedir.
    """
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    ctx = _context(spin_seq=value, vision_confidence=value,
                   direction_confidence=value,
                   centro_previsto=value, applied_gale_level=value)
    _apply_spin_result(cur, _payload(context=ctx))
    row = _insert_map(cur)
    assert row["spin_seq"] is None
    assert row["vision_confidence"] is None
    assert row["direction_confidence"] is None
    assert row["centro_previsto"] is None
    assert row["gale_level"] is None
    assert row["hit"] is True and row["spin_number"] == 32


# ---------------------------------------------------------------------------
# Faixa de float aceita pelo PG (medida contra PG 15 real)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("label,value", [
    ("NaN", float("nan")),
    ("+Inf", float("inf")),
    ("-Inf", float("-inf")),
    ("overflow", 1e300),
    ("-overflow", -1e300),
    ("acima do float4 max", 3.5e38),
    ("underflow", 1e-300),
    ("abaixo do denormal", 1e-46),
])
def test_float_outside_postgres_real_range_becomes_null(monkeypatch, label, value):
    """A coluna é REAL (float4): fora da faixa o PRÓPRIO banco recusa o INSERT.

    Medido contra PG 15: REAL aceita ±Inf/NaN mas recusa 1e300 (overflow) e
    1e-300 (underflow) — justamente o que o JSONB deixa passar. Sem esta guarda
    no worker, um evento legado (ou escrito à mão) com float gigante manda o
    resultado essencial para a DLQ.
    """
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context(
        vision_confidence=value, direction_confidence=value)))
    row = _insert_map(cur)
    assert row["vision_confidence"] is None, label
    assert row["direction_confidence"] is None, label
    # ...e a linha essencial continua inteira.
    assert row["hit"] is True
    assert row["spin_number"] == 32
    assert row["dealer"] == "Ana"


@pytest.mark.parametrize("value", [
    0.0, -0.0, 0.87, 1.0, -0.5, 1e-6, 3.4028235e38, -3.4028235e38, 1.4e-45,
])
def test_floats_inside_postgres_real_range_are_preserved(monkeypatch, value):
    """Sem clamp e sem estrago colateral: valor válido chega intacto."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context(vision_confidence=value)))
    assert _insert_map(cur)["vision_confidence"] == value


def test_zero_is_a_value_not_an_absence(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context(vision_confidence=0.0)))
    assert _insert_map(cur)["vision_confidence"] == 0.0
    assert _insert_map(cur)["vision_confidence"] is not None


def test_non_finite_is_rejected_independently_of_the_column_range(monkeypatch):
    """Finitude e faixa guardam coisas DIFERENTES; hoje se sobrepõem, amanhã não.

    A faixa vem da coluna REAL; a finitude vem do JSONB do evento, que recusa
    NaN/Inf seja qual for a largura da coluna. Alargar a faixa (ex.: migrar para
    float8) não pode reabrir a porta para ±Inf.
    """
    monkeypatch.setattr(cdc_worker, "_PG_FLOAT4_MAX", float("inf"))
    monkeypatch.setattr(cdc_worker, "_PG_FLOAT4_MIN", 0.0)
    assert cdc_worker._coerce_float(float("inf")) is None
    assert cdc_worker._coerce_float(float("-inf")) is None
    assert cdc_worker._coerce_float(float("nan")) is None
    assert cdc_worker._coerce_float(1e300) == 1e300


def test_int_outside_postgres_integer_range_becomes_null(monkeypatch):
    """Fora da faixa de int4 o próprio PG recusaria o INSERT (linha perdida)."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context(spin_seq=2 ** 31)))
    assert _insert_map(cur)["spin_seq"] is None
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context(spin_seq=2 ** 31 - 1)))
    assert _insert_map(cur)["spin_seq"] == 2 ** 31 - 1


def test_coercers_are_total_for_hostile_values():
    from workers.cdc_worker import (
        _coerce_bool, _coerce_float, _coerce_int, _coerce_int4, _coerce_text,
    )
    hostile = [float("inf"), float("-inf"), float("nan"), 10 ** 400,
               "x", "", None, {}, [], (), True, False, object()]
    for value in hostile:
        for coerce in (_coerce_text, _coerce_float, _coerce_int,
                       _coerce_int4, _coerce_bool):
            coerce(value)  # não pode levantar


def test_missing_context_with_flag_on_writes_legacy_row(monkeypatch):
    """Worker ON + produtor OFF: no-op seguro (linha legada, sem crash)."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload())
    sql, _ = cur.insert
    assert _norm(sql) == LEGACY_INSERT.format(schema="cw")


def test_partial_context_projects_only_what_exists(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context={"dealer": "Bia"}))
    row = _insert_map(cur)
    assert row["dealer"] == "Bia"
    assert row["provider"] is None and row["spin_seq"] is None


def test_context_without_decision_id_is_accepted(monkeypatch):
    """Sem identidade declarada não há divergência a detectar."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    ctx = _context()
    ctx.pop("decision_id")
    _apply_spin_result(cur, _payload(context=ctx))
    assert _insert_map(cur)["dealer"] == "Ana"


def test_event_without_decision_id_still_projects(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(decision_id=None, context=_context()))
    row = _insert_map(cur)
    assert row["decision_id"] is None
    assert row["dealer"] == "Ana"


# ---------------------------------------------------------------------------
# Precedência meta × contexto e leitura por evento da flag
# ---------------------------------------------------------------------------

def test_meta_centro_and_gale_take_precedence_over_context(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(
        meta={"centro_previsto": 5, "applied_gale_level": 3},
        context=_context(centro_previsto=17, applied_gale_level=2),
    ))
    row = _insert_map(cur)
    assert row["centro_previsto"] == 5
    assert row["gale_level"] == 3


def test_centro_zero_is_preserved_not_treated_as_missing(monkeypatch):
    """A casa 0 existe na roleta: 0 é valor, não ausência."""
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context(centro_previsto=0)))
    assert _insert_map(cur)["centro_previsto"] == 0


def test_flag_is_read_per_event_not_cached(monkeypatch):
    """Sem cache de módulo: o mesmo processo respeita a env corrente."""
    cur_off = FakeCursor()
    _apply_spin_result(cur_off, _payload(context=_context()))
    assert "dealer" not in _insert_columns(cur_off.insert[0])

    monkeypatch.setenv(FLAG, "1")
    cur_on = FakeCursor()
    _apply_spin_result(cur_on, _payload(context=_context()))
    assert "dealer" in _insert_columns(cur_on.insert[0])

    monkeypatch.setenv(FLAG, "0")
    cur_off2 = FakeCursor()
    _apply_spin_result(cur_off2, _payload(context=_context()))
    assert "dealer" not in _insert_columns(cur_off2.insert[0])


@pytest.mark.parametrize("value,expected", [
    ("1", True), ("true", True), ("On", True), ("YES", True),
    ("0", False), ("false", False), ("", False), ("nope", False),
])
def test_context_enabled_parsing(monkeypatch, value, expected):
    monkeypatch.setenv(FLAG, value)
    assert cdc_worker.context_enabled() is expected


def test_context_enabled_defaults_off(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert cdc_worker.context_enabled() is False


# ---------------------------------------------------------------------------
# build_context_columns isolado
# ---------------------------------------------------------------------------

def test_build_context_columns_off_returns_nothing():
    cols, vals, ctx = build_context_columns({"context": _context()}, "s")
    assert (cols, vals, ctx) == ([], [], None)


def test_build_context_columns_is_positional_consistent(monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    cols, vals, ctx = build_context_columns({"context": _context()}, "sess-1")
    assert len(cols) == len(vals)
    assert ctx is not None
    assert cols == [c for _k, c in cdc_worker.CONTEXT_COLUMN_MAP]


def test_multi_worker_safety_event_is_self_contained(monkeypatch):
    """Nada é buscado fora do próprio evento + janela de lag do mesmo schema.

    Sob FOR UPDATE SKIP LOCKED com N workers, consultar outra tabela para
    reconstruir o contexto seria corrida; este teste trava esse contrato.
    """
    monkeypatch.setenv(FLAG, "1")
    cur = FakeCursor()
    _apply_spin_result(cur, _payload(context=_context()))
    assert len(cur.executed) == 2
    select_sql = cur.executed[0][0]
    assert "cw.spin_features" in select_sql
    assert "spins_vectors" not in select_sql
    assert "decisions" not in select_sql
