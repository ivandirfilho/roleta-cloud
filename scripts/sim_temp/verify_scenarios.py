"""Verificacao dos cenarios criticos pos-correcao v4.1 (M04 Error-Vector)"""
import sys, os
# Ensure project root is on path
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
print("VALIDACAO DE CENARIOS CRITICOS — v4.2 (Anti-Drift Guardrails)")
print("=" * 60)

# C1: CW update_adaptive stores history (no longer EMA)
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

# C4: Asymmetric offset returns tuple
s3 = SDA17Strategy()
s3._wheel = WHEEL
# Fill enough history for warmup
for i in range(6):
    s3.cw_history.append((WHEEL[i], WHEEL[i+5]))
off2, off3 = s3._get_adaptive_offset("horario")
check("C4 asymmetric offset tuple", isinstance(off2, int) and isinstance(off3, int),
      f"off_c2={off2}, off_c3={off3}")

# C5: Offsets within bounds
ok5 = 7 <= off2 <= 13 and 7 <= off3 <= 13
check("C5 offset bounds", ok5, f"off_c2={off2} in [7,13], off_c3={off3} in [7,13]")

# C6: Decision model fields
d = Decision(sda_offset=11, sda_offset_type="bayesian")
dd = d.to_dict()
ok6 = dd.get("sda_offset") == 11 and dd.get("sda_offset_type") == "bayesian"
check("C6 Decision model", ok6, f"offset={dd.get('sda_offset')}, type={dd.get('sda_offset_type')}")

# C7: persistence chain (both histories)
s5 = SDA17Strategy()
s5.update_adaptive("cw", 15, 30, WHEEL)
s5.update_adaptive("ccw", 10, 23, WHEEL)
state = s5.get_adaptive_state()
s6 = SDA17Strategy()
s6.load_adaptive_state(state)
ok7 = s6.cw_history == s5.cw_history and s6.ccw_history == s5.ccw_history
check("C7 persistence chain", ok7, f"cw_hist={len(s6.cw_history)}, ccw_hist={len(s6.ccw_history)}")

# C8: Backward compat — old state with cw_ema loads without error
s7 = SDA17Strategy()
s7.load_adaptive_state({"cw_ema": 12.0, "ccw_history": [(10, 23)]})
check("C8 backward compat cw_ema", len(s7.cw_history) == 0 and len(s7.ccw_history) == 1,
      f"cw_hist={len(s7.cw_history)}, ccw_hist={len(s7.ccw_history)}")

# C9: _circ_dir returns correct direction
s8 = SDA17Strategy()
d1 = s8._circ_dir(0, 32, WHEEL)  # 0 is at index 0, 32 at index 1 -> +1 (cw)
d2 = s8._circ_dir(0, 26, WHEEL)  # 0 at 0, 26 at 36 -> -1 (ccw, closer going back)
check("C9 _circ_dir direction", d1 == 1 and d2 == -1, f"d1={d1}, d2={d2}")

# C10: DB migration
import sqlite3, tempfile
dbpath = os.path.join(tempfile.gettempdir(), "test_migration_v41.db")
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

# C11: v4.2 parameter values
s9 = SDA17Strategy()
ok11 = (s9.OFFSET_MAX == 13 and s9.PRIOR_STRENGTH == 0.5 and
        s9.ERROR_THRESHOLD == 7 and s9.ERROR_DECAY == 0.08 and
        s9.MAX_DELTA_OFFSET == 2 and s9.SYMMETRY_CAP == 4)
check("C11 v4.2 params", ok11,
      f"MAX={s9.OFFSET_MAX}, PRIOR={s9.PRIOR_STRENGTH}, THRESH={s9.ERROR_THRESHOLD}, "
      f"DECAY={s9.ERROR_DECAY}, DELTA={s9.MAX_DELTA_OFFSET}, SYMCAP={s9.SYMMETRY_CAP}")

# C12: Momentum limiter — offset cannot jump more than ±2 per call
s10 = SDA17Strategy()
s10._wheel = WHEEL
# Force known last_offset via internal state
s10._last_offset["cw"] = 10
for i in range(8):
    s10.cw_history.append((WHEEL[i], WHEEL[(i+15) % 37]))
o2, o3 = s10._get_adaptive_offset("horario")
avg_new = round((o2 + o3) / 2)
check("C12 momentum limiter", abs(avg_new - 10) <= 2,
      f"last=10, new_avg={avg_new}, off_c2={o2}, off_c3={o3}")

# C13: Symmetry cap — |off_c2 - off_c3| <= SYMMETRY_CAP
check("C13 symmetry cap", abs(o2 - o3) <= s10.SYMMETRY_CAP,
      f"|{o2} - {o3}| = {abs(o2 - o3)} <= {s10.SYMMETRY_CAP}")

# C14: Persistence includes last_offset
s11 = SDA17Strategy()
s11._last_offset = {"cw": 11, "ccw": 9}
s11.cw_history = [(10, 20)]
state14 = s11.get_adaptive_state()
s12 = SDA17Strategy()
s12.load_adaptive_state(state14)
ok14 = s12._last_offset.get("cw") == 11 and s12._last_offset.get("ccw") == 9
check("C14 last_offset persistence", ok14, f"loaded={s12._last_offset}")

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
