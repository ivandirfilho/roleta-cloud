// selector_health.js
// NB-07 Self-Heal de seletores (Sprint 2-plena) — núcleo PURO e determinístico.
// Decisão do debate (proponente/contrário/juiz, 19/06): entregar a lógica de
// promoção/reversão/telemetria como módulo puro testável, com promoção DEFAULT OFF
// e guard-rails contra o cenário A1 (promover timer/saldo/ficha como se fosse spin).
//
// Carregado via importScripts em background.js (service worker) e via require() no
// Node (harness de testes), espelhando o padrão UMD de provider_router.js.
//
// Princípios:
//  - Sem DOM, sem relógio implícito (o tempo entra por `nowMs`).
//  - Funções IMUTÁVEIS: retornam novo Health, nunca mutam a entrada.
//  - Estado 100% serializável (sobrevive ao sono do service worker MV3 — guard A2).
//  - `off` = byte-idêntico (promoção impossível fora de `auto`).

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  Object.assign(root, api);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const SELF_HEAL_DEFAULTS = {
    promoteAfterMisses: 5,   // N misses consecutivos do seletor ativo
    confirmHits: 3,          // hits válidos+semânticos do fallback (cumulativo)
    revertHits: 3,           // ticks ruins no novo ativo → reverte
    quarantineK: 3,          // streak consecutivo de confirmações antes de promover
    varianceWindow: 5,       // janela de valores recentes inspecionada
    minDistinctValues: 2,    // exige >=2 distintos na janela (anti-valor congelado)
    maxMonotonicRun: 3,      // rejeita corrida de inteiros consecutivos >= N (anti-timer)
    promotionTtlMs: 600000,  // 10 min → auto-revert ao primário
    recentRingSize: 8,       // tamanho do ring de leituras por candidato
  };

  function _opts(opts) {
    return Object.assign({}, SELF_HEAL_DEFAULTS, opts || {});
  }

  function _clone(health) {
    // Health é dado puro (números, strings, arrays, null) → JSON round-trip é seguro.
    return JSON.parse(JSON.stringify(health));
  }

  // (1) Gate de RANGE — espelha background.js:1732 (0..36). Não é suficiente p/ promover.
  function isValidRouletteNumber(v) {
    return typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 36;
  }

  // Detecta corrida de inteiros consecutivos (passo +1 ou -1) — assinatura de
  // timer/countdown. Roleta salta de forma irregular; timer anda 1 a 1.
  function _hasConsecutiveIntegerRun(window, maxRun) {
    let run = 1;
    let dir = 0;
    for (let i = 1; i < window.length; i++) {
      const d = window[i] - window[i - 1];
      if (d === 1 || d === -1) {
        if (d === dir) {
          run += 1;
        } else {
          dir = d;
          run = 2;
        }
        if (run >= maxRun) return true;
      } else {
        dir = 0;
        run = 1;
      }
    }
    return false;
  }

  // (2) Guard-rail A1: aceita só sequência "roleta-like" — varia e não é timer.
  function isSemanticallyValidTick(values, opts) {
    const o = _opts(opts);
    const w = (values || []).slice(-o.varianceWindow);
    if (w.length < 2) return false;                 // sem variação observável ainda
    const distinct = new Set(w).size;
    if (distinct < o.minDistinctValues) return false; // estático/congelado (saldo/ficha)
    if (_hasConsecutiveIntegerRun(w, o.maxMonotonicRun)) return false; // timer/countdown
    return true;
  }

  // (3) Classificação por-tick: combina range + variação + timer.
  function classifyDrift(value, recentValues, opts) {
    const o = _opts(opts);
    const inRange = isValidRouletteNumber(value);
    const window = (recentValues || []).concat(inRange ? [value] : []);
    const varies = new Set(window.slice(-o.varianceWindow)).size >= o.minDistinctValues;
    const timerLike = _hasConsecutiveIntegerRun(window.slice(-o.varianceWindow), o.maxMonotonicRun);
    const accept = inRange && isSemanticallyValidTick(window, o);
    return { inRange, varies, timerLike, accept };
  }

  // (11) Hash determinístico (FNV-1a 32-bit hex) — identidade do seletor p/ telemetria.
  function hashSelector(descriptor) {
    const s = String(descriptor == null ? '' : descriptor);
    let h = 0x811c9dc5;
    for (let i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
    }
    return ('0000000' + h.toString(16)).slice(-8);
  }

  // (4) Health vazio — serializável.
  function emptyHealth() {
    return {
      version: 1,
      active: null,
      previousActive: null,
      candidates: {},
      promotionTtlUntil: null,
      lastUpdateMs: 0,
    };
  }

  function _ensureCandidate(h, selectorId) {
    if (!h.candidates[selectorId]) {
      h.candidates[selectorId] = {
        hash: hashSelector(selectorId),
        consecutiveMisses: 0,
        confirmHits: 0,
        quarantineHits: 0,
        lastValue: null,
        recentValues: [],
        quarantine: false,
        quarantineStartMs: null,
        promotedAt: null,
      };
    }
    return h.candidates[selectorId];
  }

  // (5) recordTick — atualiza saúde a partir de UMA leitura. Imutável.
  function recordTick(health, tick, opts) {
    const o = _opts(opts);
    const h = _clone(health || emptyHealth());
    const selectorId = tick && tick.selectorId;
    const value = tick ? tick.value : null;
    const nowMs = tick && typeof tick.nowMs === 'number' ? tick.nowMs : h.lastUpdateMs;
    if (!selectorId) return h;

    if (h.active === null) h.active = selectorId; // primeiro seletor visto = primário/ativo
    const cand = _ensureCandidate(h, selectorId);

    const inRange = isValidRouletteNumber(value);
    if (inRange) {
      cand.recentValues.push(value);
      if (cand.recentValues.length > o.recentRingSize) {
        cand.recentValues = cand.recentValues.slice(-o.recentRingSize);
      }
      cand.lastValue = value;
    }
    const ok = inRange && isSemanticallyValidTick(cand.recentValues, o);

    if (selectorId === h.active) {
      if (ok) {
        cand.consecutiveMisses = 0;
      } else {
        cand.consecutiveMisses += 1;
      }
      if (cand.quarantine) {
        // novo ativo em probação: confirmações boas acumulam streak de quarentena
        cand.quarantineHits = ok ? cand.quarantineHits + 1 : 0;
      }
    } else {
      // candidato não-ativo: acumula confirmação só com leitura válida E semântica
      if (ok) {
        cand.confirmHits += 1;
        cand.quarantineHits += 1; // streak consecutivo
      } else {
        cand.quarantineHits = 0;  // quebra do streak (mantém confirmHits cumulativo)
      }
    }

    h.lastUpdateMs = nowMs;
    return h;
  }

  // (6) pickPromotion — decisão PURA de entrar em promoção (sem efeito).
  function pickPromotion(health, opts) {
    const o = _opts(opts);
    const active = health.active;
    const a = active ? health.candidates[active] : null;
    if (!a || a.consecutiveMisses < o.promoteAfterMisses) {
      return { shouldPromote: false, candidateId: null, reason: 'active-ok-or-insufficient-misses' };
    }
    let best = null;
    for (const id of Object.keys(health.candidates)) {
      if (id === active) continue;
      const c = health.candidates[id];
      const eligible =
        c.confirmHits >= o.confirmHits &&
        c.quarantineHits >= o.quarantineK &&
        isSemanticallyValidTick(c.recentValues, o);
      if (eligible && (!best || c.confirmHits > health.candidates[best].confirmHits)) {
        best = id;
      }
    }
    if (!best) {
      return { shouldPromote: false, candidateId: null, reason: 'no-confirmed-candidate' };
    }
    return { shouldPromote: true, candidateId: best, reason: 'guardrails-passed' };
  }

  // (7) applyPromotion — promove candidato, entra em quarentena, arma TTL. Reversível.
  function applyPromotion(health, candidateId, nowMs, opts) {
    const o = _opts(opts);
    const h = _clone(health);
    if (!h.candidates[candidateId] || candidateId === h.active) return h;
    h.previousActive = h.active;
    h.active = candidateId;
    const c = h.candidates[candidateId];
    c.quarantine = true;
    c.quarantineHits = 0;
    c.consecutiveMisses = 0;
    c.quarantineStartMs = nowMs;
    c.promotedAt = nowMs;
    h.promotionTtlUntil = nowMs + o.promotionTtlMs;
    return h;
  }

  // (8) shouldRevert — TTL expirou, novo ativo falhou, ou primário recuperou.
  function shouldRevert(health, nowMs, opts) {
    const o = _opts(opts);
    if (!health.previousActive) return { revert: false, reason: 'no-previous' };
    if (health.promotionTtlUntil != null && nowMs >= health.promotionTtlUntil) {
      return { revert: true, reason: 'ttl-expired' };
    }
    const a = health.candidates[health.active];
    if (a && a.quarantine && a.consecutiveMisses >= o.revertHits) {
      return { revert: true, reason: 'probation-failed' };
    }
    const prev = health.candidates[health.previousActive];
    if (prev && prev.confirmHits >= o.revertHits && isSemanticallyValidTick(prev.recentValues, o)) {
      return { revert: true, reason: 'primary-recovered' };
    }
    return { revert: false, reason: 'within-probation' };
  }

  // (9) applyRevert — restaura o ativo anterior, limpa quarentena/TTL.
  function applyRevert(health, nowMs) {
    const h = _clone(health);
    if (!h.previousActive) return h;
    const restored = h.previousActive;
    const failed = h.active;
    if (h.candidates[failed]) {
      h.candidates[failed].quarantine = false;
      h.candidates[failed].quarantineHits = 0;
      h.candidates[failed].promotedAt = null;
      h.candidates[failed].quarantineStartMs = null;
    }
    h.active = restored;
    h.previousActive = null;
    h.promotionTtlUntil = null;
    h.lastUpdateMs = typeof nowMs === 'number' ? nowMs : h.lastUpdateMs;
    return h;
  }

  // (12) driftTelemetry — NB-10: SÓ hashes/booleanos/contagens. Nunca conteúdo do DOM.
  function driftTelemetry(health, opts) {
    const o = opts || {};
    const policy = o.policy || 'off';
    const candidates = Object.keys(health.candidates).map((id) => {
      const c = health.candidates[id];
      return {
        selectorHash: c.hash,
        hit: c.consecutiveMisses === 0,
        missCount: c.consecutiveMisses,
        confirmCount: c.confirmHits,
        quarantine: !!c.quarantine,
        promoted: health.active === id && c.promotedAt != null,
      };
    });
    const activeHash = health.active && health.candidates[health.active]
      ? health.candidates[health.active].hash
      : null;
    return { activeHash, policy, candidates };
  }

  // (10) evaluatePolicy — redutor determinístico que HONRA a flag.
  //  off            → action sempre 'none', nextHealth byte-idêntico (nunca promove).
  //  shadow         → computa pickPromotion + telemetria, mas NÃO promove.
  //  auto           → pode 'promote'/'revert'.
  //  killSwitch=true → força 'none' independente da policy.
  function evaluatePolicy(health, policy, opts) {
    const o = _opts(opts);
    const killSwitch = !!(opts && opts.killSwitch);
    const nowMs = opts && typeof opts.nowMs === 'number' ? opts.nowMs : health.lastUpdateMs;
    const telemetry = driftTelemetry(health, { policy });

    if (killSwitch || policy === 'off' || policy == null) {
      return { action: 'none', telemetry, nextHealth: health };
    }

    if (policy === 'shadow') {
      // Observa (telemetria + decisão hipotética) sem nunca aplicar.
      return { action: 'none', telemetry, nextHealth: health };
    }

    if (policy === 'auto') {
      const rev = shouldRevert(health, nowMs, o);
      if (rev.revert) {
        const nextHealth = applyRevert(health, nowMs);
        return { action: 'revert', reason: rev.reason, telemetry: driftTelemetry(nextHealth, { policy }), nextHealth };
      }
      const pick = pickPromotion(health, o);
      if (pick.shouldPromote) {
        const nextHealth = applyPromotion(health, pick.candidateId, nowMs, o);
        return { action: 'promote', candidateId: pick.candidateId, telemetry: driftTelemetry(nextHealth, { policy }), nextHealth };
      }
      return { action: 'none', telemetry, nextHealth: health };
    }

    return { action: 'none', telemetry, nextHealth: health };
  }

  // (13) serializeHealth / deserializeHealth — round-trip lossless p/ chrome.storage (guard A2).
  function serializeHealth(health) {
    return JSON.stringify(health);
  }

  function deserializeHealth(serialized) {
    if (serialized == null) return emptyHealth();
    const obj = typeof serialized === 'string' ? JSON.parse(serialized) : _clone(serialized);
    return Object.assign(emptyHealth(), obj);
  }

  return {
    SELF_HEAL_DEFAULTS,
    isValidRouletteNumber,
    isSemanticallyValidTick,
    classifyDrift,
    hashSelector,
    emptyHealth,
    recordTick,
    pickPromotion,
    applyPromotion,
    shouldRevert,
    applyRevert,
    driftTelemetry,
    evaluatePolicy,
    serializeHealth,
    deserializeHealth,
  };
});
