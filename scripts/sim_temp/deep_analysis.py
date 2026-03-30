import sqlite3, json, math

db = "/app/data/decisions.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

WHEEL = [0,32,15,19,4,21,2,25,17,34,6,27,13,36,11,30,8,23,10,5,24,16,33,1,20,14,31,9,22,18,29,7,28,12,35,3,26]

def wheel_index(n):
    try: return WHEEL.index(n)
    except: return -1

def circ_dist(a, b):
    ai, bi = wheel_index(a), wheel_index(b)
    if ai < 0 or bi < 0: return 99
    return min((ai-bi)%37, (bi-ai)%37)

def circ_dir(a, b):
    ai, bi = wheel_index(a), wheel_index(b)
    if ai < 0 or bi < 0: return 0
    cw = (bi - ai) % 37
    ccw = (ai - bi) % 37
    if cw == 0: return 0
    return 1 if cw <= ccw else -1

def get_neighbors(center, radius):
    idx = wheel_index(center)
    if idx < 0: return set()
    return set(WHEEL[(idx + d) % 37] for d in range(-radius, radius+1))

def compute_coverage(c1, c2, c3):
    nums = get_neighbors(c1, 3) | get_neighbors(c2, 2) | get_neighbors(c3, 2)
    return nums

print("TOTAL_DECISIONS=" + str(conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]))

# Check how many v4.1.0 decisions (offset_type=bayesian for both directions)
v41 = conn.execute("SELECT COUNT(*) FROM decisions WHERE sda_offset_type='bayesian' AND sda_offset > 0").fetchone()[0]
print(f"V41_DECISIONS={v41}")

for dir_name, label in [("horario", "CW"), ("anti-horario", "CCW")]:
    print(f"\n{'='*80}")
    print(f"=== LAST 25 {label} ({dir_name}) ===")
    print(f"{'='*80}")
    
    rows = conn.execute(f"""
        SELECT id, timestamp, spin_number, spin_direction, spin_force,
               sda_center, sda_centers, sda_numbers, sda_offset, sda_offset_type,
               sda_score, sda_predicted_force, final_action, action_reason,
               result_hit, result_actual, gale_level, gale_bet_value,
               tr_should_bet, tr_confidence, tr_reason, tr_c4_rate
        FROM decisions 
        WHERE spin_direction='{dir_name}'
        ORDER BY id DESC LIMIT 25
    """).fetchall()
    
    hits = 0
    bets = 0
    misses_detail = []
    offset_perf = {}
    
    for i, r in enumerate(rows):
        centers_raw = r['sda_centers'] or str(r['sda_center'])
        try:
            centers = json.loads(centers_raw) if centers_raw.startswith('[') else [int(centers_raw)]
        except:
            centers = [r['sda_center'] or 0]
        
        nums_raw = r['sda_numbers'] or ''
        try:
            if nums_raw.startswith('['):
                nums = json.loads(nums_raw)
            else:
                nums = [int(x.strip()) for x in nums_raw.split(',') if x.strip()] if nums_raw else []
        except:
            nums = []
        
        actual = r['result_actual']
        hit = r['result_hit']
        off = r['sda_offset'] or 0
        off_type = r['sda_offset_type'] or ''
        action = r['final_action']
        force = r['spin_force'] or 0
        pred_force = r['sda_predicted_force'] or 0
        score = r['sda_score'] or 0
        
        hit_str = "PEND"
        if action == 'APOSTAR':
            bets += 1
            if hit == 1:
                hits += 1
                hit_str = "HIT"
            elif hit == 0:
                hit_str = "MISS"
        else:
            hit_str = "SKIP"
        
        # Distance analysis for misses
        dist_to_c1 = circ_dist(centers[0], actual) if actual and len(centers) > 0 else -1
        nearest_center = -1
        nearest_dist = 99
        if actual and len(centers) > 0:
            for ci, c in enumerate(centers):
                d = circ_dist(c, actual)
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_center = ci
        
        # Check if actual was in the predicted numbers
        in_coverage = actual in nums if actual and nums else None
        
        # Compute what the optimal offset would have been (oracle)
        if actual and len(centers) > 0:
            c1 = centers[0]
            oracle_hits = {}
            for test_off in range(7, 18):
                c1_idx = wheel_index(c1)
                if c1_idx >= 0:
                    tc2 = WHEEL[(c1_idx + test_off) % 37]
                    tc3 = WHEEL[(c1_idx - test_off) % 37]
                    cov = compute_coverage(c1, tc2, tc3)
                    if actual in cov:
                        oracle_hits[test_off] = True
            oracle_offsets = sorted(oracle_hits.keys()) if oracle_hits else []
        else:
            oracle_offsets = []
        
        # Track offset performance
        if off > 0 and action == 'APOSTAR' and hit is not None:
            if off not in offset_perf:
                offset_perf[off] = {'hits': 0, 'total': 0}
            offset_perf[off]['total'] += 1
            if hit == 1:
                offset_perf[off]['hits'] += 1
        
        c_str = ','.join(str(c) for c in centers)
        print(f"  [{i+1:>2}] id={r['id']:>5} | #{r['spin_number']:>3} | force={force:>2} pred={pred_force:>2} | "
              f"off={off:>2} {off_type:>9} | score={score} | C=[{c_str}] | "
              f"actual={actual or '--':>3} | {hit_str:>4} | dist_c1={dist_to_c1:>2} near_c={nearest_center}:{nearest_dist} | "
              f"oracle={oracle_offsets} | gale=G{r['gale_level'] or 1}")
        
        if hit_str == "MISS" and actual:
            misses_detail.append({
                'id': r['id'], 'spin': r['spin_number'], 'c1': centers[0],
                'actual': actual, 'dist_c1': dist_to_c1, 'off': off,
                'oracle': oracle_offsets, 'nearest': nearest_dist,
                'pred_force': pred_force, 'real_force': force
            })
    
    rate = hits/max(bets,1)*100
    print(f"\n  {label} Summary: {hits}/{bets} = {rate:.1f}% HR")
    
    print(f"\n  Offset Performance:")
    for off_val in sorted(offset_perf.keys()):
        p = offset_perf[off_val]
        r2 = p['hits']/max(p['total'],1)*100
        print(f"    offset={off_val:>2}: {p['hits']}/{p['total']} = {r2:.0f}%")
    
    print(f"\n  Miss Analysis ({len(misses_detail)} misses):")
    for m in misses_detail:
        force_err = abs(m['pred_force'] - m['real_force']) if m['pred_force'] and m['real_force'] else -1
        print(f"    id={m['id']} | C1={m['c1']} actual={m['actual']} | dist_c1={m['dist_c1']} | "
              f"off_used={m['off']} oracle={m['oracle']} | force_err={force_err} | "
              f"{'OFFSET_BUG' if m['oracle'] and m['off'] not in m['oracle'] else 'FORCE_MISS' if not m['oracle'] else 'OK'}")

# Global v4.1.0 stats
print(f"\n{'='*80}")
print("=== V4.1.0 GLOBAL STATS ===")
print(f"{'='*80}")
for dir_name, label in [("horario", "CW"), ("anti-horario", "CCW")]:
    r = conn.execute(f"""
        SELECT COUNT(*) as t, 
               SUM(CASE WHEN result_hit=1 THEN 1 ELSE 0 END) as h,
               AVG(sda_offset) as avg_off
        FROM decisions 
        WHERE spin_direction='{dir_name}' AND sda_offset_type='bayesian' AND sda_offset > 0 AND final_action='APOSTAR'
    """).fetchone()
    if r['t'] > 0:
        print(f"  {label}: {r['h']}/{r['t']} = {r['h']/r['t']*100:.1f}% | avg_off={r['avg_off']:.1f}")

# Check for v4.1.0 specific (both dirs bayesian)
for dir_name, label in [("horario", "CW"), ("anti-horario", "CCW")]:
    print(f"\n  {label} offset_type distribution:")
    rows = conn.execute(f"""
        SELECT sda_offset_type, COUNT(*) as cnt, 
               SUM(CASE WHEN result_hit=1 THEN 1 ELSE 0 END) as h
        FROM decisions 
        WHERE spin_direction='{dir_name}' AND sda_offset > 0 AND final_action='APOSTAR'
        GROUP BY sda_offset_type
    """).fetchall()
    for row in rows:
        rate = row['h']/max(row['cnt'],1)*100
        print(f"    {row['sda_offset_type']:>10}: {row['h']}/{row['cnt']} = {rate:.1f}%")

conn.close()
