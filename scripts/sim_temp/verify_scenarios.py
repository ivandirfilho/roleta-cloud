"""Verificacao dos cenarios criticos — v4.3 (M02-PctSigmoid)"""
import sys, os
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
os.chdir(project_root)

from strategies.sda17 import SDA17Strategy
from core.roulette import roulette
from state.timeline import Timeline
from database.models import Decision

WHEEL = roulette.WHEEL_SEQUENCE
results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"  [{status}] {name}: {detail}")

print("=" * 60)
print("VALIDACAO DE CENARIOS CRITICOS — v4.3 (M02-PctSigmoid)")
print("=" * 60)

# C1: CW update_adaptive stores history
s = SDA17Strategy()
s.update_adaptive("cw", 10, 23, WHEEL)
s.update_adaptive("cw", 15, 30, WHEEL)
check("C1 CW history append", len(s.cw_history) == 2, f"len={len(s.cw_history)}")

# C2: CCW update_adaptive stores history
s.update_adaptive("ccw", 10, 5, WHEEL)
check("C2 CCW history append", len(s.ccw_history) == 1, f"len={len(s.ccw_history)}")

# C3: _wheel in analyze
s2 = SDA17Strategy()
assert s2._wheel == []
tl = Timeline(direction="ccw")
for f in [10, 12, 8, 11, 9, 13, 7]:
    tl.add(f)
s2.analyze(tl, 10, WHEEL)
check("C3 _wheel in analyze()", len(s2._wheel) == 37, f"slots={len(s2._wheel)}")

# C4: Asymmetric offset returns tuple (M02 sigmoid state)
s3 = SDA17Strategy()
s3._wheel = WHEEL
s3._sigmoid_off = {"cw_off2": 11.5, "cw_off3": 9.8}
off2, off3 = s3._get_adaptive_offset("horario")
check("C4 asymmetric offset tuple", isinstance(off2, int) and isinstance(off3, int),
      f"off_c2={off2}, off_c3={off3}")

# C5: Offsets within bounds
ok5 = 7 <= off2 <= 13 and 7 <= off3 <= 13
check("C5 offset bounds", ok5, f"off_c2={off2} in [7,13], off_c3={off3} in [7,13]")

# C6: Decision model fields
d = Decision(sda_offset=11, sda_offset_type="sigmoid")
dd = d.to_dict()
ok6 = dd.get("sda_offset") == 11 and dd.get("sda_offset_type") == "sigmoid"
check("C6 Decision model", ok6, f"offset={dd.get('sda_offset')}, type={dd.get('sda_offset_type')}")

# C7: persistence chain (histories + sigmoid_off)
s5 = SDA17Strategy()
s5.update_adaptive("cw", 15, 30, WHEEL)
s5.update_adaptive("ccw", 10, 23, WHEEL)
state = s5.get_adaptive_state()
s6 = SDA17Strategy()
s6.load_adaptive_state(state)
ok7 = (s6.cw_history == s5.cw_history and s6.ccw_history == s5.ccw_history
       and s6._sigmoid_off == s5._sigmoid_off)
check("C7 persistence chain", ok7,
      f"cw_hist={len(s6.cw_history)}, ccw_hist={len(s6.ccw_history)}, sigmoid_keys={list(s6._sigmoid_off.keys())}")

# C8: Backward compat — old state with cw_ema loads without error
s7 = SDA17Strategy()
s7.load_adaptive_state({"cw_ema": 12.0, "ccw_history": [(10, 23)]})
check("C8 backward compat cw_ema", len(s7.cw_history) == 0 and len(s7.ccw_history) == 1,
      f"cw_hist={len(s7.cw_history)}, ccw_hist={len(s7.ccw_history)}")

# C9: _circ_dir returns correct direction
s8 = SDA17Strategy()
d1 = s8._circ_dir(0, 32, WHEEL)
d2 = s8._circ_dir(0, 26, WHEEL)
check("C9 _circ_dir direction", d1 == 1 and d2 == -1, f"d1={d1}, d2={d2}")

# C10: DB migration
import sqlite3, tempfile
dbpath = os.path.join(tempfile.gettempdir(), "test_migration_v43.db")
if os.path.exists(dbpath):
    os.remove(dbpath)
from database.sqlite_repo import SQLiteDecisionRepository
repo = SQLiteDecisionRepository(db_path=dbpath)
conn = sqlite3.connect(dbpath)
conn.row_factory = sqlite3.Row
r = conn.execute("PRAGMA table_info(decisions)").fetchall()
cols = [row["name"] for row in r]
ok10 = "sda_offset" in cols and "sda_offset_type" in cols
check("C10 DB schema migration", ok10, f"cols={[c for c in cols if 'offset' in c]}")
conn.close()
try:
    os.remove(dbpath)
except PermissionError:
    pass

print()
print("=" * 60)

# C11: v4.3 parameter values
s9 = SDA17Strategy()
ok11 = (s9.OFFSET_MAX == 13 and s9.BAYESIAN_DEFAULT == 10 and
        s9.BAYESIAN_WARMUP == 2 and s9.SIGMOID_K == 6 and
        s9.SIGMOID_SCALE == 2.0 and s9.HIT_TIGHTEN == 0.08 and
        s9.MISS_CROSS_RATE == 0.3)
check("C11 v4.3 params", ok11,
      f"MAX={s9.OFFSET_MAX}, DEFAULT={s9.BAYESIAN_DEFAULT}, WARMUP={s9.BAYESIAN_WARMUP}, "
      f"SIGK={s9.SIGMOID_K}, SCALE={s9.SIGMOID_SCALE}, TIGHTEN={s9.HIT_TIGHTEN}")

# C12: M02 sigmoid — hit tightens toward center=10
s10 = SDA17Strategy()
s10._wheel = WHEEL
s10._sigmoid_off = {"cw_off2": 13.0, "cw_off3": 13.0}
# Simulate a HIT: c1=10, result must be in coverage
c1_idx = WHEEL.index(10)
c2 = WHEEL[(c1_idx + 13) % 37]
result_in_cov = WHEEL[(c1_idx + 1) % 37]  # neighbor of c1
s10._pct_sigmoid_update("cw", 10, result_in_cov)
new_off2 = s10._sigmoid_off["cw_off2"]
new_off3 = s10._sigmoid_off["cw_off3"]
check("C12 sigmoid hit tightens", new_off2 < 13.0 and new_off3 < 13.0,
      f"off2: 13.0->{new_off2:.2f}, off3: 13.0->{new_off3:.2f}")

# C13: M02 sigmoid — miss expands in error direction (max adj ~2.0)
s11 = SDA17Strategy()
s11._wheel = WHEEL
s11._sigmoid_off = {"ccw_off2": 10.0, "ccw_off3": 10.0}
# Simulate a MISS far away: c1=10, result far CW
far_result = WHEEL[(c1_idx + 18) % 37]  # opposite side of wheel
s11._pct_sigmoid_update("ccw", 10, far_result)
miss_off2 = s11._sigmoid_off["ccw_off2"]
miss_off3 = s11._sigmoid_off["ccw_off3"]
# sigmoid saturates at ~2.0, so off2 should grow but not beyond MAX
check("C13 sigmoid miss expands", miss_off2 != 10.0 or miss_off3 != 10.0,
      f"off2: 10.0->{miss_off2:.2f}, off3: 10.0->{miss_off3:.2f}")

# C14: Persistence includes sigmoid_off and last_offset
s12 = SDA17Strategy()
s12._last_offset = {"cw": 11, "ccw": 9}
s12._sigmoid_off = {"cw_off2": 11.5, "cw_off3": 10.2, "ccw_off2": 12.0, "ccw_off3": 9.8}
s12.cw_history = [(10, 20)]
state14 = s12.get_adaptive_state()
s13 = SDA17Strategy()
s13.load_adaptive_state(state14)
ok14 = (s13._last_offset.get("cw") == 11 and s13._last_offset.get("ccw") == 9
        and abs(s13._sigmoid_off.get("cw_off2", 0) - 11.5) < 0.01
        and abs(s13._sigmoid_off.get("ccw_off3", 0) - 9.8) < 0.01)
check("C14 full persistence", ok14,
      f"last_off={s13._last_offset}, sigmoid_off={s13._sigmoid_off}")

# C15: Backward compat v4.2 — state without sigmoid_off loads OK
s14 = SDA17Strategy()
s14.load_adaptive_state({"cw_history": [(10, 20)], "last_offset": {"cw": 11}})
check("C15 v4.2 backward compat", len(s14.cw_history) == 1 and s14._sigmoid_off == {},
      f"sigmoid_off={s14._sigmoid_off}")

# C16: min_forces=2 — Triple Focus activates with just 2 forces
s15 = SDA17Strategy()
tl2 = Timeline(direction="cw")
tl2.add(10)
tl2.add(12)
result16 = s15.analyze(tl2, 10, WHEEL)
# With 2 forces and both valid (>0), should NOT fall to SDA-19 
has_triple = len(result16.details.get("centers", [])) == 3
check("C16 warmup=2 triple focus", has_triple,
      f"centers={result16.details.get('centers', [])}, method={result16.details.get('method', '')}")

# C17: SDA-19 fallback only with <2 valid forces
s16 = SDA17Strategy()
tl3 = Timeline(direction="cw")
tl3.add(10)
result17 = s16.analyze(tl3, 10, WHEEL)
# With only 1 valid force after filtering, should fall to SDA-19 (or should_bet=False)
is_fallback = result17.details.get("method") == "fallback_sda19" or not result17.should_bet
check("C17 SDA-19 fallback <2", is_fallback,
      f"method={result17.details.get('method', 'N/A')}, should_bet={result17.should_bet}")

# C18: offset_type is "sigmoid" in details
s17 = SDA17Strategy()
tl4 = Timeline(direction="ccw")
for f in [10, 12, 8, 11, 9]:
    tl4.add(f)
result18 = s17.analyze(tl4, 10, WHEEL)
check("C18 offset_type sigmoid", result18.details.get("offset_type") == "sigmoid",
      f"type={result18.details.get('offset_type', 'N/A')}")

print()
print("=" * 60)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print(f"RESULTADO: {passed}/{len(results)} PASS, {failed} FAIL")
if failed == 0:
    print("[OK] TODOS OS CENARIOS VALIDADOS COM SUCESSO")
else:
    print("[ERRO] CENARIOS COM FALHA DETECTADOS")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"  FAIL: {name} -- {detail}")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
