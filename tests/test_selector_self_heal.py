"""Tests for selector_health.js (NB-07 self-heal — Sprint 2-plena, passos_escuta_junho §4.9.3).

Núcleo PURO e determinístico do self-heal de seletores. Decisão do debate
(proponente/contrário/juiz, 19/06): lógica de promoção/reversão/telemetria como
módulo puro testável, com promoção DEFAULT OFF e guard-rails contra o cenário A1
(promover timer/saldo/ficha como se fosse spin). Harness Node via subprocess,
espelhando tests/test_provider_router.py.
"""

import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "extension" / "selector_health.js"


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _node_available(), reason="Node.js required for selector_health tests")


# Prelúdio JS compartilhado: require + helpers para montar estados de saúde.
_PRELUDE = (
    "const m = require(%s);\n"
    "function feedActiveMisses(h, n){ for(let i=0;i<n;i++) h=m.recordTick(h,{selectorId:'primary',value:99,nowMs:i+1}); return h; }\n"
    "function feedCand(h, vals, sel){ sel=sel||'fallback'; for(let i=0;i<vals.length;i++) h=m.recordTick(h,{selectorId:sel,value:vals[i],nowMs:100+i}); return h; }\n"
    "function promotable(){ let h=m.emptyHealth(); h=m.recordTick(h,{selectorId:'primary',value:0,nowMs:0}); h=feedActiveMisses(h,6); h=feedCand(h,[0,17,32,5,26,8,21]); return h; }\n"
) % json.dumps(str(HELPER))


def _run(body: str):
    script = _PRELUDE + "const __out=(function(){\n" + body + "\n})();\nprocess.stdout.write(JSON.stringify(__out));\n"
    res = subprocess.run(["node", "-e", script], cwd=REPO, text=True, capture_output=True, check=True)
    return json.loads(res.stdout)


# 1
def test_self_heal_loads():
    out = _run("return {keys:Object.keys(m), defaults:m.SELF_HEAL_DEFAULTS};")
    for name in [
        "SELF_HEAL_DEFAULTS", "isValidRouletteNumber", "isSemanticallyValidTick", "classifyDrift",
        "hashSelector", "emptyHealth", "recordTick", "pickPromotion", "applyPromotion",
        "shouldRevert", "applyRevert", "driftTelemetry", "evaluatePolicy",
        "serializeHealth", "deserializeHealth",
    ]:
        assert name in out["keys"], name
    d = out["defaults"]
    assert d["promoteAfterMisses"] == 5 and d["confirmHits"] == 3 and d["quarantineK"] == 3
    assert d["promotionTtlMs"] == 600000


# 2
def test_is_valid_roulette_number_range():
    out = _run("return [m.isValidRouletteNumber(0), m.isValidRouletteNumber(36), m.isValidRouletteNumber(-1), m.isValidRouletteNumber(37), m.isValidRouletteNumber(1.5), m.isValidRouletteNumber('3'), m.isValidRouletteNumber(NaN)];")
    assert out == [True, True, False, False, False, False, False]


# 3
def test_empty_health_shape_serializable():
    out = _run("const h=m.emptyHealth(); const rt=m.deserializeHealth(m.serializeHealth(h)); return {h, identical: JSON.stringify(h)===JSON.stringify(rt)};")
    assert out["h"]["version"] == 1
    assert out["h"]["active"] is None
    assert out["h"]["candidates"] == {}
    assert out["identical"] is True


# 4 — Guard-rail A1: valor estático (saldo/ficha congelada) nunca é semântico.
def test_semantic_reject_static_value_A1():
    out = _run("return m.isSemanticallyValidTick([12,12,12,12]);")
    assert out is False


# 5 — Guard-rail A1: timer/countdown (inteiros consecutivos) nunca é semântico.
def test_semantic_reject_timer_like_A1():
    out = _run("return [m.isSemanticallyValidTick([9,8,7,6,5]), m.isSemanticallyValidTick([18,19,20])];")
    assert out == [False, False]


# 6
def test_semantic_accept_roulette_variation():
    out = _run("return m.isSemanticallyValidTick([0,17,32,5,26]);")
    assert out is True


# 7
def test_record_tick_increments_misses_immutable():
    out = _run(
        "let h1=m.recordTick(m.emptyHealth(),{selectorId:'primary',value:0,nowMs:1});"
        "const before=JSON.stringify(h1);"
        "let h2=m.recordTick(h1,{selectorId:'primary',value:99,nowMs:2});"
        "return {inputUnchanged: JSON.stringify(h1)===before, m1:h1.candidates.primary.consecutiveMisses, m2:h2.candidates.primary.consecutiveMisses};"
    )
    assert out["inputUnchanged"] is True
    assert out["m2"] > out["m1"]


# 8
def test_record_tick_confirm_requires_semantic():
    out = _run(
        "let h=m.recordTick(m.emptyHealth(),{selectorId:'primary',value:0,nowMs:0});"
        "h=feedCand(h,[7,7,7,7]);"
        "const afterStatic=h.candidates.fallback.confirmHits;"
        "h=feedCand(h,[0,17,32,5,26]);"
        "const afterVaried=h.candidates.fallback.confirmHits;"
        "return {afterStatic, afterVaried};"
    )
    assert out["afterStatic"] == 0
    assert out["afterVaried"] > 0


# 9
def test_pick_promotion_requires_misses_and_confirm():
    out = _run(
        "let low=m.emptyHealth(); low=m.recordTick(low,{selectorId:'primary',value:0,nowMs:0}); low=feedActiveMisses(low,2); low=feedCand(low,[0,17,32,5,26]);"
        "const p1=m.pickPromotion(low);"
        "const p2=m.pickPromotion(promotable());"
        "return {below:p1.shouldPromote, ok:p2.shouldPromote, cand:p2.candidateId};"
    )
    assert out["below"] is False
    assert out["ok"] is True
    assert out["cand"] == "fallback"


# 10 — quarentena: bloqueia até quarantineHits >= quarantineK (streak consecutivo).
def test_quarantine_k_confirmation_before_promote():
    out = _run(
        "let h=m.emptyHealth(); h=m.recordTick(h,{selectorId:'primary',value:0,nowMs:0}); h=feedActiveMisses(h,6);"
        "h=feedCand(h,[0,17,32,99,5,26]);"  # 99 quebra o streak de quarentena
        "const blocked=m.pickPromotion(h);"
        "h=feedCand(h,[8],'fallback');"  # restaura streak -> q>=3
        "const allowed=m.pickPromotion(h);"
        "return {confirm:h.candidates.fallback.confirmHits, qhits:h.candidates.fallback.quarantineHits, blocked:blocked.shouldPromote, blockedReason:blocked.reason, allowed:allowed.shouldPromote};"
    )
    assert out["confirm"] >= 3
    assert out["blocked"] is False
    assert out["allowed"] is True


# 11
def test_apply_promotion_sets_ttl_and_reversible():
    out = _run(
        "let h=promotable(); const pick=m.pickPromotion(h); h=m.applyPromotion(h, pick.candidateId, 100);"
        "return {active:h.active, previous:h.previousActive, promotedAt:h.candidates.fallback.promotedAt, ttl:h.promotionTtlUntil};"
    )
    assert out["active"] == "fallback"
    assert out["previous"] == "primary"
    assert out["promotedAt"] == 100
    assert out["ttl"] == 100 + 600000


# 12
def test_should_revert_on_ttl_expiry():
    out = _run(
        "let h=promotable(); const pick=m.pickPromotion(h); h=m.applyPromotion(h, pick.candidateId, 100);"
        "const rev=m.shouldRevert(h, 100+600000+50);"
        "const r=m.applyRevert(h, 700000);"
        "return {revert:rev.revert, reason:rev.reason, activeAfter:r.active, prevAfter:r.previousActive};"
    )
    assert out["revert"] is True
    assert out["reason"] == "ttl-expired"
    assert out["activeAfter"] == "primary"
    assert out["prevAfter"] is None


# 13
def test_should_revert_on_repeated_invalid():
    out = _run(
        "let h=promotable(); const pick=m.pickPromotion(h); h=m.applyPromotion(h, pick.candidateId, 100);"
        "for(let i=0;i<3;i++) h=m.recordTick(h,{selectorId:'fallback',value:99,nowMs:200+i});"
        "const rev=m.shouldRevert(h, 250);"
        "return {misses:h.candidates.fallback.consecutiveMisses, revert:rev.revert, reason:rev.reason};"
    )
    assert out["misses"] >= 3
    assert out["revert"] is True
    assert out["reason"] == "probation-failed"


# 14 — off = byte-idêntico, NUNCA promove mesmo com thresholds batidos.
def test_policy_off_is_byte_identical():
    out = _run(
        "const h=promotable(); const ev=m.evaluatePolicy(h,'off',{nowMs:100});"
        "return {action:ev.action, identical: JSON.stringify(ev.nextHealth)===JSON.stringify(h)};"
    )
    assert out["action"] == "none"
    assert out["identical"] is True


# 15
def test_policy_shadow_observes_no_promote():
    out = _run(
        "const h=promotable(); const ev=m.evaluatePolicy(h,'shadow',{nowMs:100});"
        "return {action:ev.action, active:ev.nextHealth.active, hasTel: Array.isArray(ev.telemetry.candidates), identical: JSON.stringify(ev.nextHealth)===JSON.stringify(h)};"
    )
    assert out["action"] == "none"
    assert out["active"] == "primary"  # não promoveu
    assert out["hasTel"] is True
    assert out["identical"] is True


# 16
def test_policy_auto_promotes_when_all_guardrails_pass():
    out = _run(
        "const h=promotable(); const ev=m.evaluatePolicy(h,'auto',{nowMs:100});"
        "return {action:ev.action, active:ev.nextHealth.active};"
    )
    assert out["action"] == "promote"
    assert out["active"] == "fallback"


# 16b — kill-switch força 'none' mesmo em auto.
def test_kill_switch_forces_none():
    out = _run("const h=promotable(); return m.evaluatePolicy(h,'auto',{nowMs:100,killSwitch:true}).action;")
    assert out == "none"


# 17 — NB-10: telemetria só com hashes/booleanos/contagens, nunca conteúdo do DOM.
def test_drift_telemetry_no_content_NB10():
    out = _run(
        "const h=promotable(); const tel=m.driftTelemetry(h,{policy:'shadow'});"
        "const c=tel.candidates[0];"
        "return {keys:Object.keys(c), hashIsNotSelector: c.selectorHash!=='fallback' && c.selectorHash!=='primary', activeHash: tel.activeHash};"
    )
    allowed = {"selectorHash", "hit", "missCount", "confirmCount", "quarantine", "promoted"}
    assert set(out["keys"]) == allowed
    for forbidden in ("value", "lastValue", "number", "recentValues", "text"):
        assert forbidden not in out["keys"]
    assert out["hashIsNotSelector"] is True


# 18 — Guard-rail A2: estado sobrevive ao sono do service worker (round-trip lossless).
def test_serialize_roundtrip_persistence_A2():
    out = _run(
        "const h=promotable(); const rt=m.deserializeHealth(m.serializeHealth(h));"
        "return {identical: JSON.stringify(h)===JSON.stringify(rt), misses:rt.candidates.primary.consecutiveMisses, confirm:rt.candidates.fallback.confirmHits};"
    )
    assert out["identical"] is True
    assert out["misses"] >= 5
    assert out["confirm"] >= 3
