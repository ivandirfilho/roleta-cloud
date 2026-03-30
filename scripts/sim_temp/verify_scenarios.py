"""Verificação dos 8 cenários críticos pós-correção v4.0.3"""
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
print("VALIDAÇÃO DE CENÁRIOS CRÍTICOS — v4.0.3")
print("=" * 60)

# C1: EMA clamp upper
s = SDA17Strategy()
s.cw_ema = 16.0
s.update_adaptive("cw", 10, 23, WHEEL)
check("C1 EMA upper clamp", s.cw_ema <= 16.0, f"ema={s.cw_ema:.4f}")

# C2: EMA clamp lower
s.cw_ema = 8.0
s.update_adaptive("cw", 10, 5, WHEEL)
check("C2 EMA lower clamp", s.cw_ema >= 8.0, f"ema={s.cw_ema:.4f}")

# C3: _wheel in analyze
s2 = SDA17Strategy()
assert s2._wheel == []
tl = Timeline(direction="ccw")
for f in [10, 12, 8, 11, 9, 13, 7]:
    tl.add(f)
s2.analyze(tl, 10, WHEEL)
check("C3 _wheel in analyze()", len(s2._wheel) == 37, f"slots={len(s2._wheel)}")

# C4: load ema=25 -> clamp 16
s3 = SDA17Strategy()
s3.load_adaptive_state({"cw_ema": 25.0, "ccw_history": []})
check("C4 load ema=25 clamp", s3.cw_ema == 16.0, f"ema={s3.cw_ema}")

# C5: load ema=3 -> clamp 8
s4 = SDA17Strategy()
s4.load_adaptive_state({"cw_ema": 3.0, "ccw_history": []})
check("C5 load ema=3 clamp", s4.cw_ema == 8.0, f"ema={s4.cw_ema}")

# C6: Decision model fields
d = Decision(sda_offset=11, sda_offset_type="bayesian")
dd = d.to_dict()
ok6 = dd.get("sda_offset") == 11 and dd.get("sda_offset_type") == "bayesian"
check("C6 Decision model", ok6, f"offset={dd.get('sda_offset')}, type={dd.get('sda_offset_type')}")

# C7: persistence chain
s5 = SDA17Strategy()
s5.update_adaptive("cw", 15, 30, WHEEL)
s5.update_adaptive("ccw", 10, 23, WHEEL)
state = s5.get_adaptive_state()
s6 = SDA17Strategy()
s6.load_adaptive_state(state)
ok7 = abs(s6.cw_ema - s5.cw_ema) < 0.001 and s6.ccw_history == s5.ccw_history
check("C7 persistence chain", ok7, f"ema={s6.cw_ema:.2f}, hist={len(s6.ccw_history)}")

# C8: DB migration
import sqlite3, tempfile
dbpath = os.path.join(tempfile.gettempdir(), "test_migration_v403.db")
if os.path.exists(dbpath):
    os.remove(dbpath)
from database.sqlite_repo import SQLiteDecisionRepository
repo = SQLiteDecisionRepository(db_path=dbpath)
conn = sqlite3.connect(dbpath)
conn.row_factory = sqlite3.Row
r = conn.execute("PRAGMA table_info(decisions)").fetchall()
cols = [row["name"] for row in r]
ok8 = "sda_offset" in cols and "sda_offset_type" in cols
check("C8 DB schema migration", ok8, f"cols={[c for c in cols if 'offset' in c]}")
conn.close()
try:
    os.remove(dbpath)
except PermissionError:
    pass  # Windows file lock — DB was verified

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
            print(f"  FAIL: {name} — {detail}")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
