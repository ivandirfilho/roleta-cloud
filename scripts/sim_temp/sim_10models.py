"""
Simulação de 10 Modelos Bayesianos de Angulação C2/C3
M15-ADA v4.1 Study — Engenharia Reversa
Premissa: Apostar em TODAS as jogadas, 17 números, 3 centros (C1:7, C2:5, C3:5)
"""
import math
from collections import Counter

WHEEL = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
W_IDX = {n:i for i,n in enumerate(WHEEL)}
W_SIZE = len(WHEEL)

def nb(center, radius):
    """Neighbors of center with given radius on wheel."""
    idx = W_IDX[center]
    return set(WHEEL[(idx + r) % W_SIZE] for r in range(-radius, radius+1))

def cov(c1, off2, off3, r1=3, r2=2, r3=2):
    """Coverage with potentially asymmetric offsets for C2 and C3."""
    idx = W_IDX[c1]
    c2 = WHEEL[(idx + off2) % W_SIZE]
    c3 = WHEEL[(idx - off3) % W_SIZE]
    return nb(c1, r1) | nb(c2, r2) | nb(c3, r3), c2, c3

def cov_sym(c1, off, r1=3, r2=2):
    """Symmetric coverage (same offset both sides)."""
    return cov(c1, off, off, r1, r2, r2)

def circ_dist(a, b):
    """Circular distance on wheel."""
    ia, ib = W_IDX[a], W_IDX[b]
    d = abs(ia - ib)
    return min(d, W_SIZE - d)

def circ_dir(c1, result):
    """Direction from c1 to result: +1 = CW (increasing idx), -1 = CCW."""
    ic = W_IDX[c1]
    ir = W_IDX[result]
    cw = (ir - ic) % W_SIZE
    ccw = (ic - ir) % W_SIZE
    return 1 if cw <= ccw else -1

# ============================================================================
# 10 MODELS
# ============================================================================

def model_01_symmetric_bayesian(history, default=12, win=12, off_min=7, off_max=17):
    """M1: Bayesiano Simétrico — mesmo offset C2 e C3, testa 7-17."""
    if len(history) < 5:
        return default, default
    window = history[-win:]
    best_off, best_hits = default, -1
    for t in range(off_min, off_max+1):
        h = sum(1 for c1, res in window if res in cov_sym(c1, t)[0])
        if h > best_hits:
            best_hits, best_off = h, t
    return best_off, best_off

def model_02_asymmetric_bayesian(history, default=12, win=12):
    """M2: Bayesiano Assimétrico — offsets independentes C2 e C3."""
    if len(history) < 5:
        return default, default
    window = history[-win:]
    best_o2, best_o3, best_hits = default, default, -1
    for o2 in range(6, 16):
        for o3 in range(6, 16):
            h = sum(1 for c1, res in window if res in cov(c1, o2, o3)[0])
            if h > best_hits:
                best_hits, best_o2, best_o3 = h, o2, o3
    return best_o2, best_o3

def model_03_momentum_shift(history, default=12, win=12, off_min=7, off_max=17):
    """M3: Momentum Shift — desloca C2/C3 baseado na tendência dos resultados."""
    if len(history) < 5:
        return default, default
    window = history[-win:]
    # Base: best symmetric offset
    base_off = default
    best_h = -1
    for t in range(off_min, off_max+1):
        h = sum(1 for c1, res in window if res in cov_sym(c1, t)[0])
        if h > best_h:
            best_h, base_off = h, t
    # Momentum: count direction of results relative to C1
    cw_count = sum(1 for c1, res in window[-6:] if circ_dir(c1, res) > 0)
    ccw_count = len(window[-6:]) - cw_count
    shift = 0
    if cw_count > ccw_count + 1:
        shift = -1  # Results tend CW -> pull C2 closer (reduce off2)
    elif ccw_count > cw_count + 1:
        shift = 1   # Results tend CCW -> pull C3 closer (reduce off3)
    off2 = max(off_min, min(off_max, base_off + shift))
    off3 = max(off_min, min(off_max, base_off - shift))
    return off2, off3

def model_04_error_vector(history, default=12, win=12, off_min=7, off_max=17):
    """M4: Error-Vector — acumula viés direcional dos erros."""
    if len(history) < 5:
        return default, default
    window = history[-win:]
    # Compute directional bias from misses
    bias_cw, bias_ccw = 0.0, 0.0
    for c1, res in window:
        d = circ_dir(c1, res)
        dist = circ_dist(c1, res)
        if dist > 5:  # Only count significant misses
            if d > 0:
                bias_cw += dist * 0.15
            else:
                bias_ccw += dist * 0.15
    # Apply bias: if misses tend CW, push C2 further CW
    off2 = max(off_min, min(off_max, round(default + bias_cw - bias_ccw)))
    off3 = max(off_min, min(off_max, round(default + bias_ccw - bias_cw)))
    return off2, off3

def model_05_zone_weighted(history, default=12, win=12, off_min=7, off_max=17):
    """M5: Zone-Weighted — ajusta offset por zona de queda dos resultados."""
    if len(history) < 5:
        return default, default
    window = history[-win:]
    near = mid = far = 0
    for c1, res in window:
        d = circ_dist(c1, res)
        if d <= 6:
            near += 1
        elif d <= 12:
            mid += 1
        else:
            far += 1
    total = near + mid + far
    if total == 0:
        return default, default
    # If results cluster near C1 -> tighter offsets
    # If results scatter far -> wider offsets
    weighted_off = round(off_min + (off_max - off_min) * (mid + 2*far) / (2*total))
    weighted_off = max(off_min, min(off_max, weighted_off))
    return weighted_off, weighted_off

def model_06_dual_band(history, default=12, win=8, state=None):
    """M6: Dual-Band Oscillating — alterna entre banda tight e wide."""
    if state is None:
        state = {"band": "tight", "counter": 0, "tight_hits": 0, "wide_hits": 0}
    if len(history) < 5:
        return default, default, state
    window = history[-win:]
    # Test tight band (7-10) and wide band (11-15)
    tight_h = 0
    for t in range(7, 11):
        tight_h = max(tight_h, sum(1 for c1, r in window if r in cov_sym(c1, t)[0]))
    wide_h = 0
    for t in range(11, 16):
        wide_h = max(wide_h, sum(1 for c1, r in window if r in cov_sym(c1, t)[0]))
    state["tight_hits"] = tight_h
    state["wide_hits"] = wide_h
    state["counter"] += 1
    # Choose band with more hits
    if tight_h >= wide_h:
        state["band"] = "tight"
        # Find best in tight band
        best_off, best_h2 = 8, -1
        for t in range(7, 11):
            h = sum(1 for c1, r in window if r in cov_sym(c1, t)[0])
            if h > best_h2:
                best_h2, best_off = h, t
    else:
        state["band"] = "wide"
        best_off, best_h2 = 12, -1
        for t in range(11, 16):
            h = sum(1 for c1, r in window if r in cov_sym(c1, t)[0])
            if h > best_h2:
                best_h2, best_off = h, t
    return best_off, best_off, state

def model_07_gradient_descent(history, state=None, off_min=7, off_max=17):
    """M7: Gradient Descent — ajusta offset ±1 baseado em hit/miss."""
    if state is None:
        state = {"off": 10, "hits_at_current": 0, "tries_at_current": 0}
    if len(history) < 3:
        return state["off"], state["off"], state
    c1_last, res_last = history[-1]
    was_hit = res_last in cov_sym(c1_last, state["off"])[0]
    state["tries_at_current"] += 1
    if was_hit:
        state["hits_at_current"] += 1
    else:
        # Shift toward result direction
        d = circ_dir(c1_last, res_last)
        dist = circ_dist(c1_last, res_last)
        if dist > 8:
            # Result was far, increase offset
            state["off"] = min(off_max, state["off"] + 1)
        elif dist < 4:
            # Result was near but missed, decrease offset
            state["off"] = max(off_min, state["off"] - 1)
        state["hits_at_current"] = 0
        state["tries_at_current"] = 0
    return state["off"], state["off"], state

def model_08_cluster_split(history, default=12, win=12, off_min=5, off_max=18):
    """M8: Cluster-Split — posiciona C2/C3 nos clusters mais densos dos resultados."""
    if len(history) < 8:
        return default, default
    window = history[-win:]
    results = [res for _, res in window]
    # Find two best positions on wheel that cover most results
    best_o2, best_o3, best_h = default, default, -1
    # Test candidate positions for C2 and C3
    for o2 in range(off_min, off_max+1, 2):  # Step 2 for speed
        for o3 in range(off_min, off_max+1, 2):
            h = 0
            for c1, res in window:
                s, _, _ = cov(c1, o2, o3)
                if res in s:
                    h += 1
            if h > best_h:
                best_h, best_o2, best_o3 = h, o2, o3
    return best_o2, best_o3

def model_09_recency_weighted(history, default=12, win=16, off_min=7, off_max=17):
    """M9: Recency-Weighted Bayesian — pesos exponenciais para resultados recentes."""
    if len(history) < 5:
        return default, default
    window = history[-win:]
    n = len(window)
    best_off, best_score = default, -1.0
    for t in range(off_min, off_max+1):
        score = 0.0
        for i, (c1, res) in enumerate(window):
            weight = 0.7 ** (n - 1 - i)  # Most recent = weight 1.0
            if res in cov_sym(c1, t)[0]:
                score += weight
        if score > best_score:
            best_score, best_off = score, t
    return best_off, best_off

def model_10_multi_prior(history, default=10, win=12, off_min=7, off_max=17):
    """M10: Multi-Prior Bayesian — distribuição posterior com prior Gaussiano."""
    if len(history) < 5:
        return default, default
    window = history[-win:]
    # Prior: Gaussian centered at 10, sigma=3
    prior_center = 10
    prior_sigma = 3.0
    best_off, best_post = default, -999.0
    for t in range(off_min, off_max+1):
        # Likelihood: count hits
        hits = sum(1 for c1, res in window if res in cov_sym(c1, t)[0])
        likelihood = hits / len(window)
        # Prior: Gaussian
        prior = math.exp(-0.5 * ((t - prior_center) / prior_sigma) ** 2)
        # Posterior (log scale for stability)
        posterior = likelihood * prior
        if posterior > best_post:
            best_post, best_off = posterior, t
    return best_off, best_off

# ============================================================================
# DATA
# ============================================================================
cw_data = [
    (2903, 10, 23, True),  (2905, 11, 4, True),   (2907, 29, 23, True),
    (2909, 11, 24, False), (2911, 12, 7, True),   (2913, 25, 8, True),
    (2915, 15, 30, False), (2917, 1, 11, True),   (2919, 24, 10, True),
    (2921, 0, 4, False),   (2923, 25, 22, False), (2925, 3, 27, True),
    (2927, 17, 15, False), (2929, 7, 19, True),   (2931, 31, 34, False),
    (2933, 4, 10, False),  (2935, 29, 28, True),  (2937, 10, 20, False),
    (2939, 33, 3, False),  (2941, 0, 22, False),  (2943, 9, 25, True),
    (2945, 8, 0, True),   (2947, 0, 34, False),  (2949, 10, 23, True),
    (2951, 3, 35, True),  (2953, 27, 10, False), (2955, 13, 29, False),
    (2957, 0, 17, False),  (2959, 26, 9, False),  (2961, 24, 31, False),
    (2963, 2, 1, False),   (2965, 28, 36, False), (2967, 34, 3, False),
    (2969, 7, 14, False),  (2971, 32, 14, False), (2973, 16, 21, False),
    (2975, 21, 30, False), (2977, 3, 30, False),  (2979, 9, 2, False),
    (2981, 31, 22, True),  (2983, 21, 13, False), (2985, 1, 1, True),
    (2987, 3, 7, False),   (2989, 29, 18, True),  (2991, 6, 6, True),
    (2993, 2, 10, False),  (2995, 31, 3, False),  (2997, 7, 9, False),
    (2999, 5, 17, False),
]

ccw_data = [
    (2902, 17, 34, True),  (2904, 20, 11, False), (2906, 9, 16, True),
    (2908, 35, 30, False), (2910, 2, 20, False),  (2912, 27, 26, True),
    (2914, 16, 24, True),  (2916, 24, 7, True),   (2918, 20, 0, False),
    (2920, 2, 31, False),  (2922, 13, 22, False), (2924, 25, 8, False),
    (2926, 21, 36, False), (2928, 10, 6, False),  (2930, 27, 12, False),
    (2932, 34, 30, False), (2934, 31, 22, True),  (2936, 21, 21, True),
    (2938, 35, 3, True),   (2940, 17, 15, True),  (2942, 32, 32, True),
    (2944, 23, 30, True),  (2946, 6, 30, False),  (2948, 5, 5, True),
    (2950, 9, 26, True),   (2952, 25, 36, True),  (2954, 12, 24, False),
    (2956, 28, 9, False),  (2958, 20, 13, False), (2960, 15, 21, True),
    (2962, 4, 14, False),  (2964, 10, 32, False), (2966, 22, 7, True),
    (2968, 11, 7, False),  (2970, 30, 10, True),  (2972, 10, 34, True),
    (2974, 24, 8, False),  (2976, 9, 26, True),   (2978, 26, 27, False),
    (2980, 32, 7, True),   (2982, 8, 2, True),    (2984, 20, 22, False),
    (2986, 15, 19, True),  (2988, 13, 0, False),  (2990, 17, 10, True),
    (2992, 9, 11, False),  (2994, 12, 35, True),  (2996, 11, 7, False),
    (2998, 24, 9, False),  (3000, 20, 34, False),
]

# ============================================================================
# SIMULATION ENGINE
# ============================================================================

def simulate_all(data, label):
    """Simulate all 10 models against the dataset."""
    orig_hits = sum(1 for _,_,_,h in data if h)
    n = len(data)
    
    results = {}
    
    for model_num in range(1, 11):
        history = []
        hits = 0
        details = []
        state = None
        miss_streak = 0
        max_miss = 0
        max_hit = 0
        cur_hit = 0
        cur_miss = 0
        
        for idx, (gid, c1, result, orig_hit) in enumerate(data):
            # Get offset(s) from model
            if model_num == 1:
                o2, o3 = model_01_symmetric_bayesian(history)
            elif model_num == 2:
                o2, o3 = model_02_asymmetric_bayesian(history)
            elif model_num == 3:
                o2, o3 = model_03_momentum_shift(history)
            elif model_num == 4:
                o2, o3 = model_04_error_vector(history)
            elif model_num == 5:
                o2, o3 = model_05_zone_weighted(history)
            elif model_num == 6:
                o2, o3, state = model_06_dual_band(history, state=state)
            elif model_num == 7:
                o2, o3, state = model_07_gradient_descent(history, state=state)
            elif model_num == 8:
                o2, o3 = model_08_cluster_split(history)
            elif model_num == 9:
                o2, o3 = model_09_recency_weighted(history)
            elif model_num == 10:
                o2, o3 = model_10_multi_prior(history)
            
            coverage_set, c2, c3 = cov(c1, o2, o3)
            hit = result in coverage_set
            if hit:
                hits += 1
                cur_hit += 1
                cur_miss = 0
            else:
                cur_miss += 1
                cur_hit = 0
            max_hit = max(max_hit, cur_hit)
            max_miss = max(max_miss, cur_miss)
            
            details.append((gid, c1, o2, o3, c2, c3, result, hit, len(coverage_set)))
            history.append((c1, result))
        
        results[model_num] = {
            "hits": hits,
            "total": n,
            "hr": hits/n*100,
            "max_hit_streak": max_hit,
            "max_miss_streak": max_miss,
            "details": details,
        }
    
    # Oracle: best fixed symmetric offset
    oracle = {}
    for t in range(7, 18):
        oh = sum(1 for _, c1, res, _ in data if res in cov_sym(c1, t)[0])
        oracle[t] = oh
    best_oracle = max(oracle, key=oracle.get)
    
    return results, orig_hits, n, oracle, best_oracle

def print_results(results, orig_hits, n, oracle, best_oracle, label):
    sep = "=" * 78
    print(f"\n{sep}")
    print(f"  SIMULACAO {label} — {n} JOGADAS")
    print(sep)
    
    model_names = {
        1: "M01 Simetrico Bayesiano",
        2: "M02 Assimetrico Bayesiano",
        3: "M03 Momentum Shift",
        4: "M04 Error-Vector",
        5: "M05 Zone-Weighted",
        6: "M06 Dual-Band Oscilante",
        7: "M07 Gradient Descent",
        8: "M08 Cluster-Split",
        9: "M09 Recency-Weighted",
        10: "M10 Multi-Prior Bayesiano",
    }
    
    # Summary table
    print(f"\n--- RANKING DE MODELOS ---")
    print(f"  {'#':>3} | {'Modelo':<30} | {'Acertos':>7} |  {'HR':>6} | {'MissMax':>7} | {'HitMax':>6} | {'P&L R$5':>8}")
    print(f"  ----+--------------------------------+---------+--------+---------+--------+---------")
    
    bet = 5
    pm = 37/17 - 1
    
    ranked = sorted(results.items(), key=lambda x: x[1]["hr"], reverse=True)
    
    for model_num, r in ranked:
        pnl = r["hits"] * bet * pm - (n - r["hits"]) * bet
        print(f"  {model_num:3d} | {model_names[model_num]:<30} | {r['hits']:3d}/{n:<3d} | {r['hr']:5.1f}% | {r['max_miss_streak']:7d} | {r['max_hit_streak']:6d} | {pnl:+8.2f}")
    
    # Original and Oracle
    pnl_orig = orig_hits * bet * pm - (n - orig_hits) * bet
    pnl_oracle = oracle[best_oracle] * bet * pm - (n - oracle[best_oracle]) * bet
    print(f"  ----+--------------------------------+---------+--------+---------+--------+---------")
    print(f"  REF | Original v4.0.2                | {orig_hits:3d}/{n:<3d} | {orig_hits/n*100:5.1f}% |      -- |     -- | {pnl_orig:+8.2f}")
    print(f"  REF | Oraculo (offset={best_oracle:2d})            | {oracle[best_oracle]:3d}/{n:<3d} | {oracle[best_oracle]/n*100:5.1f}% |      -- |     -- | {pnl_oracle:+8.2f}")
    
    # Offset oracle map
    print(f"\n--- MAPA DE OFFSETS (Oraculo) ---")
    for o in range(7, 18):
        h = oracle[o]
        bar = '#' * h + '.' * (n - h)
        mark = " <-- BEST" if o == best_oracle else ""
        print(f"  Offset {o:2d}: {h:2d}/{n} ({h/n*100:.1f}%) |{bar}|{mark}")
    
    # Top 3 models: detailed evolution
    print(f"\n--- DETALHES TOP-3 MODELOS ---")
    for rank, (model_num, r) in enumerate(ranked[:3]):
        print(f"\n  [{rank+1}o] {model_names[model_num]} — {r['hits']}/{n} = {r['hr']:.1f}%")
        print(f"  {'ID':>5} | C1 | O2 | O3 | C2 | C3 | RES | HIT | Cov | HR_Acc")
        print(f"  ------+----+----+----+----+----+-----+-----+-----+-------")
        rh = 0
        for i, (gid, c1, o2, o3, c2, c3, res, hit, ncov) in enumerate(r["details"]):
            if hit:
                rh += 1
            hr = rh / (i+1) * 100
            m = 'Y' if hit else 'N'
            asym = "*" if o2 != o3 else " "
            print(f"  {gid:5d} | {c1:2d} | {o2:2d} | {o3:2d}{asym}| {c2:2d} | {c3:2d} |  {res:2d} |  {m}  |  {ncov:2d} | {hr:.1f}%")
    
    return ranked

# ============================================================================
# MAIN
# ============================================================================
print("=" * 78)
print("  SIMULACAO 10 MODELOS BAYESIANOS DE ANGULACAO C2/C3")
print("  M15-ADA v4.1 Study — Engenharia Reversa")
print("  Premissa: APOSTAR EM TODAS | 17 numeros | C1(7)+C2(5)+C3(5)")
print("  Parametros INDEPENDENTES por direcao")
print("=" * 78)

cw_res, cw_orig, cw_n, cw_or, cw_bo = simulate_all(cw_data, "CW")
print_cw = print_results(cw_res, cw_orig, cw_n, cw_or, cw_bo, "CW (HORARIO)")

ccw_res, ccw_orig, ccw_n, ccw_or, ccw_bo = simulate_all(ccw_data, "CCW")
print_ccw = print_results(ccw_res, ccw_orig, ccw_n, ccw_or, ccw_bo, "CCW (ANTI-HORARIO)")

# Consolidated
print(f"\n{'=' * 78}")
print(f"  CONSOLIDACAO — CW + CCW COMBINADOS")
print(f"{'=' * 78}")

model_names = {
    1: "M01 Simetrico Bayesiano",
    2: "M02 Assimetrico Bayesiano",
    3: "M03 Momentum Shift",
    4: "M04 Error-Vector",
    5: "M05 Zone-Weighted",
    6: "M06 Dual-Band Oscilante",
    7: "M07 Gradient Descent",
    8: "M08 Cluster-Split",
    9: "M09 Recency-Weighted",
    10: "M10 Multi-Prior Bayesiano",
}

bet = 5
pm = 37/17 - 1
total_n = cw_n + ccw_n

print(f"\n  {'#':>3} | {'Modelo':<30} | {'CW HR':>6} | {'CCW HR':>7} | {'Total':>7} | {'CombHR':>6} | {'P&L Total':>10}")
print(f"  ----+--------------------------------+--------+---------+---------+--------+-----------")

combined = []
for m in range(1, 11):
    cw_h = cw_res[m]["hits"]
    ccw_h = ccw_res[m]["hits"]
    total_h = cw_h + ccw_h
    comb_hr = total_h / total_n * 100
    pnl = total_h * bet * pm - (total_n - total_h) * bet
    combined.append((m, cw_h, ccw_h, total_h, comb_hr, pnl))

combined.sort(key=lambda x: x[4], reverse=True)

for m, cwh, ccwh, th, chr_, pnl in combined:
    print(f"  {m:3d} | {model_names[m]:<30} | {cwh/cw_n*100:5.1f}% | {ccwh/ccw_n*100:6.1f}% | {th:3d}/{total_n:<3d} | {chr_:5.1f}% | {pnl:+10.2f}")

# Original
orig_total = cw_orig + ccw_orig
pnl_orig = orig_total * bet * pm - (total_n - orig_total) * bet
print(f"  ----+--------------------------------+--------+---------+---------+--------+-----------")
print(f"  REF | Original v4.0.2                | {cw_orig/cw_n*100:5.1f}% | {ccw_orig/ccw_n*100:6.1f}% | {orig_total:3d}/{total_n:<3d} | {orig_total/total_n*100:5.1f}% | {pnl_orig:+10.2f}")

# Best model improvement
best_m = combined[0]
delta_hr = best_m[4] - orig_total/total_n*100
delta_pnl = best_m[5] - pnl_orig
print(f"\n  MELHOR MODELO: {model_names[best_m[0]]}")
print(f"  Delta HR vs Original: +{delta_hr:.1f}pp")
print(f"  Delta P&L vs Original: +R${delta_pnl:.2f}")
print(f"  Max miss streak CW:  {cw_res[best_m[0]]['max_miss_streak']}")
print(f"  Max miss streak CCW: {ccw_res[best_m[0]]['max_miss_streak']}")
