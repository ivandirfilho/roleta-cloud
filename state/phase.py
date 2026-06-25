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


def reconcile_shift(prev, new, max_window: int = 20):
    """Reconciliação por SHIFT: conta quantos giros NOVOS há em `new` em relação a
    `prev`, ambos ordenados do mais recente (índice 0) para o mais antigo.

    Encontra o menor k >= 0 tal que a CAUDA de `new` (a partir de k) casa com a
    CABEÇA de `prev`:  new[k : k+m] == prev[0 : m].

    Retorna (k, matched):
      - k = 0, matched=True  → nenhum giro novo (duplicado / re-render do DOM);
      - k = 1, matched=True  → um giro novo (caso normal);
      - k >= 2, matched=True → GAP recuperado (cliente dormiu / 2 giros num tick);
      - matched=False        → sem alinhamento (lista nova = troca de mesa/dealer)
                               → o chamador deve pedir resync, não adivinhar.

    Robusto a números repetidos (0–36): é alinhamento de subsequência ordenada
    (posição-a-posição), não comparação de conjunto. Função pura, nunca lança.
    """
    new = list(new) if new else []
    prev = list(prev) if prev else []
    if not new:
        return (0, True)        # nada novo a contabilizar
    if not prev:
        return (1, True)        # primeira leitura: trata o topo como 1 giro novo
    max_k = min(len(new), max_window)
    for k in range(0, max_k + 1):
        m = min(len(prev), len(new) - k)
        if m <= 0:
            break
        if all(new[k + i] == prev[i] for i in range(m)):
            return (k, True)
    return (min(len(new), max_window), False)   # sem alinhamento → resync
