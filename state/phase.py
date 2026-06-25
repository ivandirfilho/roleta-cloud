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


# Prioridade de fontes de direção (maior = mais forte). O operador e a correção
# manual vencem; o vídeo confiável vence o toggle determinístico; o toggle é o default.
SOURCE_PRIORITY = {
    "operator_seed": 100,
    "manual_fix": 100,
    "vision": 50,
    "dom_hint": 20,
    "deterministic_toggle": 10,
}


def fuse_direction(signals, default_direction, min_vision_conf: float = 0.7):
    """DIR7 (sentido-fase): funde sinais de direção por PRIORIDADE/confiança.

    `signals`: lista de dicts {"source","direction","confidence"}. Sinais 'vision'
    abaixo de `min_vision_conf` são descartados (o toggle prevalece). Empate de
    prioridade → o de maior confiança. Sem sinais válidos → (default, toggle).

    Estrutura STAND-BY para o futuro módulo de vídeo: basta o serviço publicar um
    sinal {"source":"vision",...} que ele entra na fusão sem mudar mais nada.
    Função pura, nunca lança. Retorna (direction, source).
    """
    best = None
    best_key = (-1, -1.0)
    for sig in signals or []:
        try:
            src = (sig.get("source") or "").strip()
            direction = normalize(sig.get("direction") or "")
            conf = float(sig.get("confidence") or 0.0)
        except (AttributeError, TypeError, ValueError):
            continue
        if direction not in VALID:
            continue
        if src == "vision" and conf < min_vision_conf:
            continue
        key = (SOURCE_PRIORITY.get(src, 0), conf)
        if key > best_key:
            best_key = key
            best = (direction, src)
    if best is None:
        base = default_direction if default_direction in VALID else HORARIO
        return (base, "deterministic_toggle")
    return best
