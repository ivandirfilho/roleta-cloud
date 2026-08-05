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


def _reconcile_shift_ex(prev, new, max_window: int = 20, min_overlap: int = 0):
    """Núcleo do shift. Devolve `(k, matched, ambiguous)`.

    `ambiguous=True` significa: HAVIA alinhamento posicional, mas a evidência era
    insuficiente (overlap abaixo de `min_overlap`) ou havia MAIS DE UM k plausível
    com evidência suficiente — nesse caso `matched=False` e o chamador deve tratar
    como `phase_uncertain` (caminho seguro) em vez de inventar k giros.

    `min_overlap=0` desliga a checagem: comportamento byte-idêntico ao histórico
    (aceita o primeiro k que casa, mesmo com m=1 → 1/37 de coincidência).
    Função pura, nunca lança.
    """
    new = list(new) if new else []
    prev = list(prev) if prev else []
    if not new:
        return (0, True, False)     # nada novo a contabilizar
    if not prev:
        # Primeira leitura: não há evidência a exigir (min_overlap não se aplica);
        # trata o topo como 1 giro novo, como sempre fez.
        return (1, True, False)
    try:
        min_overlap = max(0, int(min_overlap))
    except (TypeError, ValueError):
        min_overlap = 0
    max_k = min(len(new), max_window)
    matches = []                     # [(k, m)] de todos os alinhamentos posicionais
    for k in range(0, max_k + 1):
        m = min(len(prev), len(new) - k)
        if m <= 0:
            break
        if all(new[k + i] == prev[i] for i in range(m)):
            if min_overlap <= 0:
                return (k, True, False)   # caminho legado: primeiro match vence
            matches.append((k, m))
    no_align = (min(len(new), max_window), False, False)
    if not matches:
        return no_align
    # `m` decresce monotonicamente com k, logo o primeiro match é o de maior evidência.
    strong = [(k, m) for (k, m) in matches if m >= min_overlap]
    if not strong:
        # Havia match, mas só por coincidência (evidência abaixo do mínimo).
        return (min(len(new), max_window), False, True)
    if len(strong) > 1:
        # Sequência periódica/repetida: mais de um k é plausível com evidência
        # suficiente. Não dá para escolher — ambíguo é o veredito honesto.
        return (min(len(new), max_window), False, True)
    return (strong[0][0], True, False)


def reconcile_shift(prev, new, max_window: int = 20, min_overlap: int = 0):
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

    `min_overlap` (SPR-V1 B2, default 0 = OFF/byte-idêntico) exige evidência mínima
    para aceitar o alinhamento; abaixo dela o resultado é `matched=False` (seguro).

    Robusto a números repetidos (0–36): é alinhamento de subsequência ordenada
    (posição-a-posição), não comparação de conjunto. Função pura, nunca lança.
    """
    k, matched, _ = _reconcile_shift_ex(prev, new, max_window, min_overlap)
    return (k, matched)


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


def phase_advance(prev, new):
    """DIR4/DIR6: decide COMO avançar a fase a partir do shift dos últimos resultados.

    Retorna (gap, intermediates, uncertain):
      - gap: giros perdidos a contabilizar ALÉM do giro atual (>= 0). Só é > 0 quando
        houve ALINHAMENTO — nunca adivinha a partir de um shift sem casamento.
      - intermediates: números perdidos a sincronizar em recent_results, do mais antigo
        ao mais recente (para o próximo giro alinhar e não gerar phase_uncertain falso).
      - uncertain: True se NÃO houve alinhamento (troca de mesa/dealer) → o chamador deve
        pedir resync e NÃO mexer no contador de fase.

    Corrige o bug de somar `k-1` ao contador quando `reconcile_shift` devolve
    `matched=False` (k é um "não sei", não um número de giros). Função pura.
    """
    gap, inter, uncertain, _ = phase_advance_ex(prev, new)
    return (gap, inter, uncertain)


def phase_advance_ex(prev, new, min_overlap: int = 0):
    """SPR-V1 B2: igual a `phase_advance`, mas devolve também `ambiguous`.

    Retorna `(gap, intermediates, uncertain, ambiguous)`. `ambiguous=True` separa
    "gap grande legítimo / troca de mesa" de "havia match, mas sem evidência
    suficiente" — é o que alimenta a métrica `phase_ambiguo_total`. Quando ambíguo,
    `uncertain` também é True (o caminho seguro). Função pura, nunca lança.
    """
    k, matched, ambiguous = _reconcile_shift_ex(prev, new, 20, min_overlap)
    if not matched:
        uncertain = bool(prev) and bool(new)
        return (0, [], uncertain, bool(ambiguous) and uncertain)
    gap = max(0, k - 1)
    inter = []
    if gap > 0:
        new_list = list(new)
        hi = min(k - 1, len(new_list) - 1)
        inter = [new_list[i] for i in range(hi, 0, -1)]
    return (gap, inter, False, False)
