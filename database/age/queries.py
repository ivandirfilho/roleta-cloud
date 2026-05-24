"""S8 — Helpers Apache AGE Cypher para grafos cw_graph / ccw_graph.

AGE expoe Cypher via SQL wrapper:
    SELECT * FROM cypher('cw_graph', $$ MATCH (n) RETURN n $$) AS (n agtype);

Este modulo encapsula esse padrao para o resto do app, mantendo
isolamento cw/ccw (uma query SEMPRE roda em UM grafo, nunca cruza).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)

VALID_GRAPHS = {"cw_graph", "ccw_graph"}


def _validate_graph(graph: str) -> None:
    if graph not in VALID_GRAPHS:
        raise ValueError(f"graph invalido: {graph!r}. Use {VALID_GRAPHS}.")


def run_cypher(
    conn,
    graph: str,
    cypher: str,
    columns: Sequence[str],
) -> list[tuple[Any, ...]]:
    """Executa Cypher em um grafo AGE e retorna rows como tuplas de agtype.

    Args:
        conn: psycopg2 connection (autocommit ou em transacao).
        graph: 'cw_graph' ou 'ccw_graph' (validado contra whitelist).
        cypher: texto do Cypher (sem dollar-quoting; este modulo aplica).
        columns: lista de aliases de retorno; tamanho deve casar com RETURN.

    Returns:
        Lista de tuplas. Caller eh responsavel por parsear agtype.

    Raises:
        ValueError: graph fora da whitelist (proteca anti-injection).
    """
    _validate_graph(graph)
    cols_decl = ", ".join(f"{c} agtype" for c in columns)
    sql = (
        "LOAD 'age'; "
        "SET search_path = ag_catalog, \"$user\", public; "
        f"SELECT * FROM cypher('{graph}', $cy$ {cypher} $cy$) AS ({cols_decl});"
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def add_spin_node(
    conn,
    graph: str,
    spin_number: int,
    force: int,
    decision_id: int,
) -> None:
    """Cria no Spin no grafo da direcao. Idempotente por decision_id."""
    _validate_graph(graph)
    cypher = (
        "MERGE (s:Spin {decision_id: %d}) "
        "SET s.spin_number = %d, s.force = %d "
        "RETURN s"
    ) % (decision_id, spin_number, force)
    run_cypher(conn, graph, cypher, ["s"])


def link_sequence(
    conn,
    graph: str,
    prev_decision_id: int,
    curr_decision_id: int,
) -> None:
    """Cria relacionamento (prev)-[:NEXT]->(curr) entre dois Spin nodes."""
    _validate_graph(graph)
    cypher = (
        "MATCH (a:Spin {decision_id: %d}), (b:Spin {decision_id: %d}) "
        "MERGE (a)-[:NEXT]->(b)"
    ) % (prev_decision_id, curr_decision_id)
    run_cypher(conn, graph, cypher, [])


def find_recent_path(conn, graph: str, depth: int = 6) -> list[tuple[Any, ...]]:
    """Retorna ultimo path de ate `depth` spins (mais recente primeiro).

    Util para S11/S12 (shadow predictor olhando trilhas).
    """
    _validate_graph(graph)
    if not (1 <= depth <= 50):
        raise ValueError("depth fora de [1,50]")
    cypher = (
        f"MATCH p=(s:Spin)-[:NEXT*1..{depth}]->(e:Spin) "
        "RETURN p ORDER BY id(e) DESC LIMIT 1"
    )
    return run_cypher(conn, graph, cypher, ["p"])
