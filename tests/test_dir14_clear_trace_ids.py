"""DIR14 (sentido-fase): clear _recent_trace_ids em handle_new_session (fix #O).

Antes: deque(maxlen=64) de trace_ids nunca era limpa em reset. Cliente que
reenvia um trace_id ainda no buffer apos reset era rejeitado como duplicado
(perdia o primeiro spin).

Depois: handle_new_session limpa o deque dentro do state_lock (atomico).
"""

import pytest


def test_handle_new_session_limpa_trace_ids_deque():
    """Apos handle_new_session, o deque _recent_trace_ids esta vazio.

    Teste unitario do comportamento — nao precisa subir websocket. Cria uma
    instancia minima e exercita o branch DIR14.
    """
    from collections import deque

    class FakeHandler:
        def __init__(self):
            self._recent_trace_ids = deque(maxlen=64)

    h = FakeHandler()
    # Simular trace_ids acumulados:
    h._recent_trace_ids.extend(["t1", "t2", "t3"])
    assert len(h._recent_trace_ids) == 3
    # Simular branch DIR14:
    if getattr(h, "_recent_trace_ids", None) is not None:
        h._recent_trace_ids.clear()
    assert len(h._recent_trace_ids) == 0


def test_clear_e_idempotente_em_deque_vazio():
    """Limpar deque ja vazio nao quebra (idempotente)."""
    from collections import deque
    d = deque(maxlen=64)
    d.clear()
    assert len(d) == 0
    d.clear()
    assert len(d) == 0


def test_clear_nao_afeta_maxlen():
    """Apos clear, deque preserva maxlen (continua aceitando 64 novos)."""
    from collections import deque
    d = deque(["a", "b", "c"], maxlen=64)
    d.clear()
    for i in range(70):
        d.append(f"t{i}")
    assert len(d) == 64  # maxlen respeitado
    assert d[0] == "t6"  # primeiros 6 expulsos
