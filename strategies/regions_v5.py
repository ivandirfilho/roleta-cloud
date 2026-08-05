"""V5 "17/21 por sentido" — composer assinatura-primeiro (estrategia_proposta_03_08.md §2).

Funções PURAS e determinísticas (sem estado, sem I/O): recebem forças/resultados
do SENTIDO corrente e devolvem as DUAS coberturas aninhadas (C17 ⊂ C21) com os
MESMOS centros — só os raios mudam (R1 nunca encolhe; R2/R3 cedem no modo-17).

Regiões (por sentido, isolamento estrito — INV-1):
  R1 = cluster de força de gravidade-7 de máxima cobertura nas últimas 8 forças
       (inversão de prioridade vs V4: o braço denso vira primário, SEM filtro
       residual). R1 NUNCA se move na disjunção.
  R2 = 2º cluster condicionado à tendência (Theil–Sen sobre 5 forças, só o
       sinal com deadband 1,0): acelerando/freando → cluster no lado do sinal;
       neutro → cluster mais denso do resíduo; resíduo vazio → R1±7.
       Clamp circular ±8 de R1; empurrado p/ posição disjunta (gap 7).
  R3 = zona mais fria (heatmap triangular, raio de pintura 3) dos últimos 12
       resultados DO MESMO sentido (corrige débito V4: C3 misturava cw+ccw).
       Cede sempre a {R1,R2}.

V5.1 "assinatura-4" (05/08, spec exata do operador — ativa com ``spec4=True``,
flag SDA_V5_SIG4; caminho default byte-idêntico ao go-live 04/08):
  R1 = idem, mas janela das últimas **4** forças do sentido-alvo.
  R2 = PROJEÇÃO DE TENDÊNCIA do próprio R1: "o sistema está acelerando ou
       freando?" — slope Theil–Sen (janela 4) vira deslocamento em casas de
       força: r2_force = r1_force + clamp(round(slope), ±8). Acelerando →
       região adiante; freando → atrás; neutro (delta≈0) → a disjunção empurra
       p/ o vizinho +7 (determinístico). NÃO usa 2º cluster do resíduo.
  R3 = região MENOS VISITADA da divisão FIXA da roda em 6 regiões contíguas
       (5×6 + 1×7 na ordem física, a partir do zero), placar `region6_counts`
       alimentado por TODOS os giros dos DOIS sentidos (state/game.py).
       Sobrepôs R1/R2? snap para a região DISJUNTA mais próxima da indicada
       (regra do operador); nenhuma disjunta → empurra posicional.

Warmup (<3 resultados no sentido): tríade-prior {0,+12,+24} ancorada em
apply_force(last_number, 10) — gaps 12/12/13 ≥ 7 ⇒ disjunta por construção
(INV-3: SEMPRE há indicação, mesmo sem dado algum).

Anchor da projeção força→número: ``last_number`` GLOBAL (a força da timeline é
medida do número anterior global ao resultado — `state/game.py process_spin`),
idêntico ao V4 (`_build_v4_regions`).
"""
from typing import Dict, List, Optional, Sequence, Tuple

# ---- Constantes (§2.1 — padrão REGIONS_V4_*) ----
V5_R1_WINDOW = 8            # janela de forças p/ o scan de R1 (2× a C2_WINDOW do V4)
V5_GRAVITY = 7              # poço de gravidade ±3 ≡ raio da região (= REGIONS_V4_GRAVITY)
V5_TS_WINDOW = 5            # janela Theil–Sen (inclinação da assinatura)
V5_TS_DEADBAND = 1.0        # |slope| ≤ 1,0 casa/giro = tendência neutra (≈1σ do ruído)
V5_R2_CLAMP = 8             # R2 preso ao arco de assinatura de R1 (±8 casas de força)
V5_R3_WINDOW = 12           # resultados do MESMO sentido p/ o heatmap frio
V5_R3_PAINT_RADIUS = 3      # raio de pintura do heatmap triangular
V5_DISJOINT_GAP = 7         # gap circular mínimo entre centros (= 2·3+1, uniforme)
V5_RADII_21 = (3, 3, 3)     # 7+7+7 = 21
V5_RADII_17 = (3, 2, 2)     # 7+5+5 = 17 (R1 nunca encolhe)
V5_WARMUP_MIN_RESULTS = 3   # abaixo disso (por sentido) → tríade-prior
V5_PRIOR_OFFSET = 10        # âncora do warmup (= BAYESIAN_DEFAULT)
V5_WARMUP_TRIAD = (0, 12, 24)  # offsets da tríade (gaps 12/12/13 ≥ 7 ⇒ disjuntos)
V5_MODE_DEFAULT = 17        # estado inicial/pós-reset do seletor
V5_MAX_21_PER_SESSION_DIR = 5  # teto de jogadas-21 por sessão×sentido → LOCK17

# ---- V5.1 "assinatura-4" (05/08 — spec exata do operador; gated SDA_V5_SIG4) ----
V5_SIG4_WINDOW = 4          # "últimas 4 jogadas": janela de R1 E da Theil–Sen
REGION6_SIZES = (6, 6, 6, 6, 6, 7)  # divisão fixa da roda: 5×6 + 1×7 = 37
REGION6_LABELS = ("g1", "g2", "g3", "g4", "g5", "g6")


# ---- Primitivas circulares (mesmas convenções do sda17.py) ----

def _wheel_index(number: int, wheel: Sequence[int]) -> int:
    try:
        return list(wheel).index(number)
    except ValueError:
        return 0


def circ_dist_idx(a: int, b: int, wheel: Sequence[int]) -> int:
    """Distância circular NÃO-assinada (casas na roda) entre dois números."""
    ia, ib = _wheel_index(a, wheel), _wheel_index(b, wheel)
    size = len(wheel)
    d = abs(ia - ib)
    return min(d, size - d)


def circ_force_dist(f1: int, f2: int, size: int) -> int:
    """Distância circular entre dois valores de FORÇA (mod size)."""
    d = abs(int(f1) - int(f2)) % size
    return min(d, size - d)


def signed_force_diff(f: int, ref: int, size: int) -> int:
    """Diferença circular ASSINADA ref→f em [-size//2, size//2]."""
    half = size // 2
    return (int(f) - int(ref) + half) % size - half


def apply_force(from_number: int, force: int, direction: str,
                wheel: Sequence[int]) -> int:
    """Projeta uma força a partir de um número (cw = +idx, ccw = −idx)."""
    wheel = list(wheel)
    idx = _wheel_index(from_number, wheel)
    size = len(wheel)
    if direction in ("cw", "horario"):
        return wheel[(idx + int(force)) % size]
    return wheel[(idx - int(force)) % size]


def get_neighbors(center: int, radius: int, wheel: Sequence[int]) -> List[int]:
    """Vizinhança circular ±radius (2·radius+1 números)."""
    wheel = list(wheel)
    idx = _wheel_index(center, wheel)
    size = len(wheel)
    return [wheel[(idx + d) % size] for d in range(-int(radius), int(radius) + 1)]


def regions_disjoint(a: int, b: int, wheel: Sequence[int],
                     gap: int = V5_DISJOINT_GAP) -> bool:
    """Dois centros são disjuntos sse a distância circular ≥ gap (7 = 2·3+1)."""
    return circ_dist_idx(a, b, wheel) >= gap


def nearest_non_overlapping(ideal: int, occupied: Sequence[int],
                            wheel: Sequence[int],
                            gap: int = V5_DISJOINT_GAP) -> int:
    """Empurra um centro ideal p/ a posição mais próxima disjunta de `occupied`.
    Empate ±d → lado + (horário na sequência) primeiro — determinístico."""
    wheel = list(wheel)
    if all(regions_disjoint(ideal, o, wheel, gap) for o in occupied):
        return ideal
    i0 = _wheel_index(ideal, wheel)
    size = len(wheel)
    for d in range(1, size // 2 + 1):
        for cand in (wheel[(i0 + d) % size], wheel[(i0 - d) % size]):
            if all(regions_disjoint(cand, o, wheel, gap) for o in occupied):
                return cand
    return ideal  # degenerado (não ocorre com ≤2 ocupantes em 37 casas)


# ---- Blocos do composer (§2.2) ----

def theil_sen_slope(forces_recent_first: Sequence[int],
                    window: int = V5_TS_WINDOW) -> Optional[float]:
    """Inclinação Theil–Sen (mediana das inclinações par-a-par) das últimas
    `window` forças, em ordem CRONOLÓGICA. ≥3 pontos; senão None (neutro)."""
    chrono = list(forces_recent_first)[:window][::-1]  # antiga → recente
    n = len(chrono)
    if n < 3:
        return None
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            slopes.append((chrono[j] - chrono[i]) / float(j - i))
    slopes.sort()
    m = len(slopes)
    mid = m // 2
    return slopes[mid] if m % 2 else (slopes[mid - 1] + slopes[mid]) / 2.0


def gravity_scan(forces_recent_first: Sequence[int], size: int,
                 gravity: int = V5_GRAVITY) -> Optional[Tuple[int, int]]:
    """Força-candidata que maximiza a cobertura do poço ±gravity sobre a janela.

    Tie-break §2.1: cobertura↓ → mais recente → |f|↑ (iteração recente-primeiro
    com desempate estável). Retorna (força, cobertura) ou None se janela vazia.
    """
    window = [int(f) for f in forces_recent_first]
    if not window:
        return None
    best: Optional[Tuple[int, int]] = None
    best_key: Optional[Tuple[int, int, int]] = None
    for recency, cand in enumerate(window):
        cov = sum(1 for f in window if circ_force_dist(f, cand, size) <= gravity)
        key = (-cov, recency, -abs(cand))
        if best_key is None or key < best_key:
            best_key, best = key, (cand, cov)
    return best


def cold_center(results_chrono: Sequence[int], occupied: Sequence[int],
                wheel: Sequence[int], window: int = V5_R3_WINDOW,
                paint_radius: int = V5_R3_PAINT_RADIUS,
                gap: int = V5_DISJOINT_GAP) -> int:
    """R3 = centro mais frio do heatmap triangular dos últimos `window`
    resultados DO SENTIDO, disjunto de `occupied` (cede sempre).
    Tie-break: menor calor → mais distante de occupied → menor idx na roda."""
    wheel = list(wheel)
    last = [r for r in list(results_chrono)[-window:] if r in wheel]
    heat = {n: 0 for n in wheel}
    for res in last:
        for n in get_neighbors(res, paint_radius, wheel):
            heat[n] += (paint_radius + 1) - circ_dist_idx(res, n, wheel)
    cands = [c for c in wheel
             if all(regions_disjoint(c, o, wheel, gap) for o in occupied)]
    if not cands:  # fallback INV-3: o mais distante dos ocupados
        return max((c for c in wheel if c not in occupied),
                   key=lambda c: min(circ_dist_idx(c, o, wheel) for o in occupied))

    def _key(c: int):
        warmth = sum(heat[n] for n in get_neighbors(c, paint_radius, wheel))
        mind = min(circ_dist_idx(c, o, wheel) for o in occupied)
        return (warmth, -mind, _wheel_index(c, wheel))

    return min(cands, key=_key)


# ---- V5.1: divisão fixa em 6 regiões (placar de visitas, ambos os sentidos) ----

def region6_bounds() -> List[Tuple[int, int]]:
    """(start_idx, size) de cada região contígua na ordem física da roda."""
    out: List[Tuple[int, int]] = []
    start = 0
    for size in REGION6_SIZES:
        out.append((start, size))
        start += size
    return out


def region6_of(number: int, wheel: Sequence[int]) -> Optional[int]:
    """Índice 0..5 da região fixa que contém `number` (None se fora da roda)."""
    wheel = list(wheel)
    if number not in wheel:
        return None
    idx = wheel.index(number)
    for gi, (start, size) in enumerate(region6_bounds()):
        if start <= idx < start + size:
            return gi
    return None


def region6_centers(wheel: Sequence[int]) -> List[int]:
    """Número central de cada região (idx start + size//2): no G6 (7 números)
    o raio-3 cobre a região EXATA; nos de 6, cobre os 6 + 1 vizinho."""
    wheel = list(wheel)
    return [wheel[start + size // 2] for start, size in region6_bounds()]


def least_visited_center(region6_counts: Sequence[int], occupied: Sequence[int],
                         wheel: Sequence[int],
                         gap: int = V5_DISJOINT_GAP) -> Tuple[int, int]:
    """R3 da V5.1: centro da região MENOS visitada do placar fixo.

    Regra do operador p/ sobreposição: se o centro da região indicada colide
    com {R1,R2}, snap para a região DISJUNTA cujo centro é o mais PRÓXIMO do
    indicado (desempate: menos visitada → menor índice). Nenhuma região
    disjunta (degenerado) → empurra posicional. Retorna (centro, idx_região).
    """
    wheel = list(wheel)
    n_reg = len(REGION6_SIZES)
    counts = [int(c) for c in list(region6_counts)[:n_reg]]
    counts += [0] * (n_reg - len(counts))
    centers = region6_centers(wheel)

    def _rank(gi: int):
        # menos visitada; desempate: mais distante dos ocupados → menor índice
        mind = min((circ_dist_idx(centers[gi], o, wheel) for o in occupied),
                   default=len(wheel))
        return (counts[gi], -mind, gi)

    ideal_gi = min(range(n_reg), key=_rank)
    ideal = centers[ideal_gi]
    if all(regions_disjoint(ideal, o, wheel, gap) for o in occupied):
        return ideal, ideal_gi
    disjoint = [gi for gi in range(n_reg) if gi != ideal_gi
                and all(regions_disjoint(centers[gi], o, wheel, gap)
                        for o in occupied)]
    if disjoint:
        snap_gi = min(disjoint,
                      key=lambda gi: (circ_dist_idx(centers[gi], ideal, wheel),
                                      counts[gi], gi))
        return centers[snap_gi], snap_gi
    return nearest_non_overlapping(ideal, occupied, wheel, gap), ideal_gi


def _coverage(centers: Sequence[int], radii: Sequence[int],
              wheel: Sequence[int]) -> List[int]:
    nums: set = set()
    for c, r in zip(centers, radii):
        nums |= set(get_neighbors(c, r, wheel))
    return sorted(nums)


def compose_v5(direction: str, forces_recent_first: Sequence[int],
               results_chrono: Sequence[int], last_number: Optional[int],
               wheel: Sequence[int], spec4: bool = False,
               region6_counts: Optional[Sequence[int]] = None) -> Dict:
    """Compõe as DUAS coberturas aninhadas do sentido (§2.2). Puro/determinístico.

    Args:
        direction: "cw"/"ccw" (ou "horario"/"anti-horario") — sentido ALVO.
        forces_recent_first: forças da timeline DO SENTIDO (índice 0 = recente).
        results_chrono: resultados brutos DO SENTIDO em ordem cronológica
            (``cw_history``/``ccw_history`` → actual_result).
        last_number: número atual da roda (âncora da projeção força→número).
        wheel: sequência física da roda (37 números).
        spec4: V5.1 "assinatura-4" (flag SDA_V5_SIG4) — R1 janela 4, R2 =
            projeção de tendência de R1, R3 = região menos visitada das 6
            fixas. False = caminho go-live 04/08 byte-idêntico.
        region6_counts: placar de visitas das 6 regiões fixas (AMBOS os
            sentidos; `GameState.region6_counts`). Só usado com spec4; se
            None, R3 degrada para a zona fria (defensivo).

    Returns:
        dict com centers=[r1,r2,r3] (idênticos nos 2 modos), numbers17 (17
        distintos), numbers21 (21 distintos, ⊇ numbers17), regioes17/regioes21
        (label/center/radius p/ overlay), warmup, r1_force, trend, slope;
        com spec4: + spec4, r2_delta, r3_region.
    """
    wheel = list(wheel)
    size = len(wheel)
    if last_number is None or last_number not in wheel:
        last_number = results_chrono[-1] if results_chrono else wheel[0]

    results = [int(r) for r in results_chrono if r in wheel]
    warmup = len(results) < V5_WARMUP_MIN_RESULTS

    ts_window = V5_SIG4_WINDOW if spec4 else V5_TS_WINDOW
    slope = theil_sen_slope(forces_recent_first, window=ts_window)
    trend = None
    if slope is not None:
        if slope > V5_TS_DEADBAND:
            trend = "accel"
        elif slope < -V5_TS_DEADBAND:
            trend = "brake"
        else:
            trend = "neutral"

    r1_force: Optional[int] = None
    r2_delta: Optional[int] = None
    r3_region: Optional[str] = None
    if warmup:
        # 1. WARMUP — tríade-prior ancorada em apply_force(last, 10): INV-3 sem dados.
        centers = [apply_force(last_number, V5_PRIOR_OFFSET + off, direction, wheel)
                   for off in V5_WARMUP_TRIAD]
    else:
        # 2. R1 — cluster de gravidade-7 de máxima cobertura (sem filtro residual).
        #    spec4: "últimas 4 jogadas" do sentido-alvo (senão janela 8 do go-live).
        r1_window = V5_SIG4_WINDOW if spec4 else V5_R1_WINDOW
        window = [int(f) for f in list(forces_recent_first)[:r1_window]]
        scan = gravity_scan(window, size)
        if scan is None:  # sem forças (só resultados) → prior (INV-3)
            r1_force = V5_PRIOR_OFFSET
        else:
            r1_force = scan[0]
        r1 = apply_force(last_number, r1_force, direction, wheel)

        if spec4:
            # 3a. R2 spec4 — PROJEÇÃO: o próprio R1 deslocado pela tendência
            #     (acelerando → adiante; freando → atrás). Neutro (delta 0) →
            #     a disjunção empurra p/ o vizinho +7 (determinístico).
            r2_delta = 0 if slope is None else int(round(slope))
            if r2_delta > V5_R2_CLAMP:
                r2_delta = V5_R2_CLAMP
            elif r2_delta < -V5_R2_CLAMP:
                r2_delta = -V5_R2_CLAMP
            r2_force_clamped = (r1_force + r2_delta) % size
            r2_ideal = apply_force(last_number, r2_force_clamped, direction, wheel)
            r2 = nearest_non_overlapping(r2_ideal, [r1], wheel)
        else:
            # 3. R2 — 2º cluster condicionado à tendência; resíduo = fora do poço de R1.
            residual = [f for f in window
                        if circ_force_dist(f, r1_force, size) > V5_GRAVITY]
            side = 1 if (slope is None or slope >= 0) else -1
            r2_force: Optional[int] = None
            if residual and trend in ("accel", "brake"):
                sided = [f for f in residual
                         if signed_force_diff(f, r1_force, size) * side > 0]
                pool = sided or residual  # lado vazio → resíduo puro (determinístico)
                r2_force = gravity_scan(pool, size)[0]
            elif residual:
                r2_force = gravity_scan(residual, size)[0]
            if r2_force is None:
                r2_force = r1_force + side * V5_GRAVITY  # sintetiza R1±7
            # clamp circular a ±8 de R1 (arco de assinatura)
            diff = signed_force_diff(r2_force, r1_force, size)
            if abs(diff) > V5_R2_CLAMP:
                diff = V5_R2_CLAMP if diff > 0 else -V5_R2_CLAMP
            r2_force_clamped = (r1_force + diff) % size
            r2_ideal = apply_force(last_number, r2_force_clamped, direction, wheel)
            r2 = nearest_non_overlapping(r2_ideal, [r1], wheel)

        if spec4 and region6_counts is not None:
            # 4a. R3 spec4 — região MENOS VISITADA das 6 fixas (ambos os sentidos).
            r3, r3_gi = least_visited_center(region6_counts, [r1, r2], wheel)
            r3_region = REGION6_LABELS[r3_gi]
        else:
            # 4. R3 — zona fria do MESMO sentido; cede sempre a {R1,R2}.
            r3 = cold_center(results, [r1, r2], wheel)
        centers = [r1, r2, r3]

    # 5. SAÍDA — mesmos centros nos 2 modos; só raios mudam ⇒ C17 ⊂ C21.
    numbers21 = _coverage(centers, V5_RADII_21, wheel)
    numbers17 = _coverage(centers, V5_RADII_17, wheel)

    def _regioes(radii: Sequence[int]) -> List[Dict]:
        out = []
        for label, c, r in zip(("r1", "r2", "r3"), centers, radii):
            reg = {"label": label, "center": c, "radius": r}
            if warmup:
                reg["status"] = "aquecendo"
            out.append(reg)
        return out

    result = {
        "centers": list(centers),
        "numbers17": numbers17,
        "numbers21": numbers21,
        "regioes17": _regioes(V5_RADII_17),
        "regioes21": _regioes(V5_RADII_21),
        "warmup": warmup,
        "r1_force": r1_force,
        "trend": trend,
        "slope": slope,
    }
    if spec4:
        result["spec4"] = True
        result["r2_delta"] = r2_delta
        result["r3_region"] = r3_region
    return result
