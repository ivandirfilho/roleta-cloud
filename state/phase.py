"""Sentido-fase (DIR3+): o sentido do giro é uma FASE alternada, não um dado lido.

A roleta opera UM giro em cada sentido (horário → anti-horário → horário …). Por isso
o operador informa a fase inicial uma única vez (seed) e o sistema alterna. A fase de
qualquer giro é então DETERMINÍSTICA e recuperável de (seed, n), sem depender de
nenhuma variável volátil:

    fase(n) = seed_parity                 se (n - seed_n) é par
            = oposto(seed_parity)         se (n - seed_n) é ímpar

Onde n = índice do giro real (contador de giros). Funções puras → 100% testáveis.
A reconciliação do contador n pelos últimos resultados (shift) vive em DIR4.
"""

HORARIO = "horario"
ANTI = "anti-horario"
VALID = (HORARIO, ANTI)


def opposite(direction: str) -> str:
    """Sentido oposto. Entrada inválida cai para o oposto de HORARIO (neutro)."""
    return ANTI if direction == HORARIO else HORARIO


def normalize(direction: str) -> str:
    """Normaliza aliases comuns (cw/ccw) para o vocabulário canônico."""
    if direction in ("cw", "horario"):
        return HORARIO
    if direction in ("ccw", "anti-horario"):
        return ANTI
    return direction


def project_phase(seed_parity: str, seed_n: int, n: int) -> str:
    """Fase determinística do giro n, ancorada no seed do operador.

    seed_parity vazio/ inválido → assume HORARIO (fallback neutro, nunca lança).
    """
    base = seed_parity if seed_parity in VALID else HORARIO
    try:
        delta = (int(n) - int(seed_n)) % 2
    except (TypeError, ValueError):
        delta = 0
    return base if delta == 0 else opposite(base)
