"""Error Engine — classificador puro do processo do erro (05/08 noite-2).

Motivação (Manutenabilidade_iso.md, ADENDO 05/08 noite-2): a resolução hoje
registra apenas hit/miss + wheel_dist agregado. Para o motor de R2
dealer-aware aprender COM o erro (e não apenas com a taxa de acerto), cada
resolução ganha uma classe de erro que descreve *por que* a aposta falhou.

Taxonomia (precedência da primeira à última — a primeira que casar vence):

1. DATA_SUSPECT   — a fase do spin era incerta (vision instável / corte de
                    stream). Aprendizado deve ser CONGELADO: o erro pode ser
                    do dado, não da estratégia.
2. HIT            — acertou; não é erro (classe presente para o funil DNA
                    ficar completo e permitir taxas por classe).
3. GEOMETRY_MISS  — o resultado caiu a <=2 casas da borda da cobertura
                    apostada ("quase"): a força estava certa, a geometria da
                    disjunção/raio é que perdeu por pouco.
4. SIGNATURE_SHIFT— a mediana dos últimos 5 erros assinados (incluindo o
                    atual) tem |mediana| >= 4: viés sistemático de direção,
                    o dealer mudou a assinatura e o centro está deslocado.
5. FORCE_MISS     — |erro assinado| >= 8: a previsão de força errou feio
                    neste spin (outlier de arremesso).
6. VARIANCE       — miss dentro do ruído esperado; nada estrutural a corrigir.

Módulo PURO: sem I/O, sem flags, sem imports do servidor — decisão de
habilitar/usar fica no call-site (server/message_handler.py) atrás de
SDA_ERROR_ENGINE (default OFF). Testes: tests/test_error_engine.py.
"""
from __future__ import annotations

import statistics
from typing import Sequence

# Classes expostas (ordem = precedência).
ERROR_CLASSES = (
    "DATA_SUSPECT",
    "HIT",
    "GEOMETRY_MISS",
    "SIGNATURE_SHIFT",
    "FORCE_MISS",
    "VARIANCE",
)

# Limiares da taxonomia (casas da roda europeia de 37 números).
GEOMETRY_GAP_MAX = 2       # miss a <=2 casas da borda da cobertura
SIGNATURE_WINDOW = 5       # mediana dos últimos N erros assinados
SIGNATURE_MEDIAN_MIN = 4   # |mediana| >= 4 => viés sistemático
FORCE_MISS_MIN = 8         # |erro assinado| >= 8 => outlier de força

# Classes em que o aprendizado (bandit/EWMA) deve ser congelado.
FROZEN_CLASSES = frozenset({"DATA_SUSPECT"})


def classify_error(
    *,
    hit: bool,
    data_suspect: bool,
    signed_err: int | float | None,
    gap_to_coverage: int | float | None,
    err_hist: Sequence[float] | None = None,
) -> str:
    """Classifica a resolução de um spin. Retorna uma das ERROR_CLASSES.

    Args:
        hit: resultado caiu dentro da cobertura apostada.
        data_suspect: fase incerta no spin (game_state.last_phase_uncertain).
        signed_err: distância assinada centro→resultado no sentido do giro
            (roulette.compute_wheel_dist_dir, faixa [-18, +18]). None quando
            indisponível (ex.: centro ausente) — pula SIGNATURE/FORCE.
        gap_to_coverage: menor distância circular do resultado a qualquer
            número da cobertura apostada (0 quando hit). None => pula GEOMETRY.
        err_hist: erros assinados recentes MAIS o atual (mais antigo→mais
            novo). Usa os últimos SIGNATURE_WINDOW; exige janela cheia.

    Nunca levanta para entradas None/parciais: degrada para as classes que
    ainda são decidíveis (contrato defensivo para o hot path).
    """
    if data_suspect:
        return "DATA_SUSPECT"
    if hit:
        return "HIT"
    if gap_to_coverage is not None and 0 <= gap_to_coverage <= GEOMETRY_GAP_MAX:
        return "GEOMETRY_MISS"
    if err_hist:
        tail = [float(e) for e in err_hist[-SIGNATURE_WINDOW:]]
        if len(tail) >= SIGNATURE_WINDOW:
            if abs(statistics.median(tail)) >= SIGNATURE_MEDIAN_MIN:
                return "SIGNATURE_SHIFT"
    if signed_err is not None and abs(float(signed_err)) >= FORCE_MISS_MIN:
        return "FORCE_MISS"
    return "VARIANCE"


def is_frozen(error_class: str) -> bool:
    """True quando a classe manda congelar o aprendizado neste spin."""
    return error_class in FROZEN_CLASSES
