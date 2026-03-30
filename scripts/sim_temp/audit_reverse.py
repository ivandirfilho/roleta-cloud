"""Auditoria profunda: engenharia reversa das ultimas 50 jogadas por sentido."""
import sqlite3, json, sys

WHEEL = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]
W_IDX = {v: i for i, v in enumerate(WHEEL)}

def neighbors(center, radius):
    idx = W_IDX[center]
    return [WHEEL[(idx + d) % 37] for d in range(-radius, radius + 1)]

def coverage_set(c1, c2, c3):
    s = set(neighbors(c1, 3))
    s |= set(neighbors(c2, 2))
    s |= set(neighbors(c3, 2))
    return s

def oracle_offsets(c1, actual, off_min=7, off_max=17):
    """Quais offsets simetricos cobririam o resultado?"""
    hits = []
    for off in range(off_min, off_max + 1):
        idx = W_IDX[c1]
        c2 = WHEEL[(idx + off) % 37]
        c3 = WHEEL[(idx - off) % 37]
        if actual in coverage_set(c1, c2, c3):
            hits.append(off)
    return hits

conn = sqlite3.connect("/app/data/decisions.db")
conn.row_factory = sqlite3.Row

for direction, label in [("horario", "CW"), ("anti-horario", "CCW")]:
    rows = conn.execute("""
        SELECT id, spin_number, spin_direction, spin_force,
               sda_center, sda_centers, sda_numbers, sda_predicted_force,
               sda_offset, sda_offset_type, sda_score,
               final_action, result_hit, result_actual,
               gale_level, tr_should_bet, tr_confidence
        FROM decisions
        WHERE spin_direction = ?
        ORDER BY id DESC LIMIT 50
    """, (direction,)).fetchall()

    print("=" * 100)
    print(f"=== ULTIMAS {len(rows)} JOGADAS {label} ({direction}) ===")
    print("=" * 100)

    hits = 0
    misses = 0
    resolved = 0
    bugs_c2c3 = 0
    bugs_coverage = 0
    bugs_hit = 0
    offset_dist = {}
    miss_causes = {"offset_high": 0, "offset_low": 0, "force_err": 0, "fallback": 0, "no_oracle": 0}

    for i, r in enumerate(rows):
        rid = r["id"]
        num = r["spin_number"]
        force = r["spin_force"] or 0
        c1_db = r["sda_center"]
        centers_raw = r["sda_centers"]
        numbers_raw = r["sda_numbers"]
        pred_force = r["sda_predicted_force"] or 0
        off_db = r["sda_offset"] or 0
        off_type = r["sda_offset_type"] or ""
        score = r["sda_score"] or 0
        action = r["final_action"] or ""
        hit = r["result_hit"]
        actual = r["result_actual"]
        gale = r["gale_level"] or 1

        # Parse JSON fields
        try:
            centers = json.loads(centers_raw) if centers_raw else [c1_db]
        except:
            centers = [c1_db]
        try:
            numbers_db = json.loads(numbers_raw) if numbers_raw else []
        except:
            numbers_db = []

        # === VERIFICACAO 1: C2 e C3 posicoes ===
        c2c3_ok = True
        c2_expected = None
        c3_expected = None
        if len(centers) == 3 and off_db > 0:
            c1, c2_db, c3_db = centers[0], centers[1], centers[2]
            c1_idx = W_IDX.get(c1, -1)
            if c1_idx >= 0:
                c2_expected = WHEEL[(c1_idx + off_db) % 37]
                # off_c3 not stored in DB; we can only verify c2
                if c2_db != c2_expected:
                    c2c3_ok = False
                    bugs_c2c3 += 1
        elif len(centers) == 1:
            c1 = centers[0]
        else:
            c1 = c1_db

        # === VERIFICACAO 2: Coverage match ===
        coverage_ok = True
        if len(centers) == 3 and numbers_db:
            c1, c2_db, c3_db = centers
            expected_nums = sorted(coverage_set(c1, c2_db, c3_db))
            actual_nums = sorted(numbers_db)
            if expected_nums != actual_nums:
                coverage_ok = False
                bugs_coverage += 1

        # === VERIFICACAO 3: Hit/Miss consistency ===
        hit_ok = True
        if hit is not None and actual is not None and numbers_db:
            expected_hit = 1 if actual in numbers_db else 0
            if expected_hit != hit:
                hit_ok = False
                bugs_hit += 1

        # === Estatisticas ===
        status = "PEND"
        if hit == 1:
            status = " HIT"
            hits += 1
            resolved += 1
        elif hit == 0:
            status = "MISS"
            misses += 1
            resolved += 1
        elif hit is None and actual is not None:
            status = "NCHK"

        if off_db > 0:
            offset_dist[off_db] = offset_dist.get(off_db, [0, 0])
            offset_dist[off_db][0] += 1
            if hit == 1:
                offset_dist[off_db][1] += 1

        # === Oracle analysis for misses ===
        oracle = []
        miss_cause = ""
        if hit == 0 and actual is not None and c1_db:
            oracle = oracle_offsets(c1_db, actual, 7, 13)  # v4.2 range
            if not oracle:
                oracle_17 = oracle_offsets(c1_db, actual, 7, 17)  # full range
                if oracle_17:
                    miss_cause = "OFFSET_RANGE"  # would hit with old range
                else:
                    miss_cause = "NO_ORACLE"
                    miss_causes["no_oracle"] += 1
            elif off_db > 0:
                if off_db > max(oracle):
                    miss_cause = "OFF_HIGH"
                    miss_causes["offset_high"] += 1
                elif off_db < min(oracle):
                    miss_cause = "OFF_LOW"
                    miss_causes["offset_low"] += 1
                else:
                    miss_cause = "ASYM"  # offset in oracle but asymmetric miss
            elif off_db == 0:
                miss_cause = "FALLBACK"
                miss_causes["fallback"] += 1

        # === Print ===
        flags = ""
        if not c2c3_ok:
            flags += " [BUG-C2]"
        if not coverage_ok:
            flags += " [BUG-COV]"
        if not hit_ok:
            flags += " [BUG-HIT]"

        actual_str = f"{actual:2d}" if actual is not None else "--"
        oracle_str = f"oracle={oracle}" if oracle else ""
        mc_str = f"cause={miss_cause}" if miss_cause else ""

        print(f"  [{i+1:2d}] id={rid} | #{num:2d} | f={force:2d} pf={pred_force:2d} | "
              f"off={off_db:2d} {off_type:8s} | sc={score} | "
              f"C=[{','.join(str(c) for c in centers)}] | "
              f"act={actual_str} | {status} | "
              f"nums={len(numbers_db)} "
              f"{oracle_str} {mc_str}{flags}")

    print()
    hr = (hits / resolved * 100) if resolved > 0 else 0
    print(f"  RESUMO {label}: {hits}/{resolved} = {hr:.1f}% HR")
    print(f"  Bugs: C2/C3={bugs_c2c3}, Coverage={bugs_coverage}, Hit={bugs_hit}")
    print()
    print(f"  OFFSET PERFORMANCE:")
    for off in sorted(offset_dist.keys()):
        total, h = offset_dist[off]
        pct = h / total * 100 if total > 0 else 0
        print(f"    off={off:2d}: {h}/{total} = {pct:.0f}%")
    print()
    if any(v > 0 for v in miss_causes.values()):
        print(f"  MISS CAUSES:")
        for cause, count in sorted(miss_causes.items(), key=lambda x: -x[1]):
            if count > 0:
                print(f"    {cause}: {count}")
    print()

conn.close()
print("AUDITORIA COMPLETA")
