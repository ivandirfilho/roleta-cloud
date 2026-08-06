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
    # ===== SPR-V4 (05/08): contrato `direction_event` + trilha `phase_events` =====
    # Cobertura ANTES de concordancia: sem saber em quantos giros elegiveis houve
    # evento, "99% de acordo" e uma metrica de 200 amostras disfarcada de prova.
    # `vision_event_total` conta INGRESSOS; os seis abaixo particionam os giros
    # elegiveis (exatamente UMA disposicao terminal por giro quando o shadow esta ON).
    "vision_event_total": 0,
    "vision_agree_total": 0,
    "vision_disagree_total": 0,
    "vision_stale_total": 0,
    "vision_unbound_total": 0,
    "vision_selfcontradict_total": 0,
    "vision_missing_total": 0,
    # Falha de escrita da trilha: NAO altera aceitacao do giro nem a aposta, mas
    # INVALIDA a janela como evidencia T4 (ha decisao sem disposicao gravada).
    "phase_events_write_error_total": 0,
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
