"""DIR8 (sentido-fase): contadores de observabilidade da fase.

Singleton leve (asyncio mono-thread no runtime). Exposto em tempo real no bloco
`sentido.stats` do state_sync (overlay/dashboard) e pronto para /metrics (Prometheus).
Atende à premissa: observabilidade não espera — lê o estado vivo a qualquer momento.
"""

from typing import Dict

_COUNTERS: Dict[str, int] = {
    "gap_recuperado_total": 0,
    "phase_uncertain_total": 0,
    "direction_divergence_total": 0,
    # SPR-V1 (05/08): o dict é FECHADO — incr() de chave desconhecida é no-op
    # silencioso. Toda métrica nova PRECISA nascer aqui, senão o caminho de erro
    # que ela deveria denunciar fica invisível.
    # B1: gap recuperado sem buffer de fase disponível (estado legado/corrompido).
    "phase_buffer_missing_total": 0,
    # B2: havia alinhamento, mas sem evidência suficiente (ou com mais de um k
    # plausível) → tratado como phase_uncertain em vez de inventar giros.
    "phase_ambiguo_total": 0,
    # B3/DIR21: giro rejeitado por ser fisicamente impossível (intervalo mínimo).
    "spin_implausivel_total": 0,
    # B5/DIR22: dois giros consecutivos com o mesmo sentido final (fora de gap/reset).
    "alternancia_violada_total": 0,
}


def incr(name: str, by: int = 1) -> None:
    """Incrementa um contador conhecido (no-op silencioso para nomes desconhecidos)."""
    if name in _COUNTERS:
        try:
            _COUNTERS[name] += int(by)
        except (TypeError, ValueError):
            pass


def snapshot() -> Dict[str, int]:
    """Cópia imutável dos contadores (para publicar no state_sync ou /metrics)."""
    return dict(_COUNTERS)


def reset() -> None:
    """Zera todos os contadores (usado em testes)."""
    for k in _COUNTERS:
        _COUNTERS[k] = 0
