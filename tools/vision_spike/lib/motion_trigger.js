// SPR-V3 · vision_spike/lib/motion_trigger.js — trigger de movimento a ~1 FPS NA ROI.
//
// Por que assim (§10.2.2-4)
// -------------------------
// O desenho original (`MutationObserver` no status da rodada) está ERRADO por construção:
// `content.js` de produção roda só no TOP FRAME e o status vive DENTRO do iframe. Além de
// redundante — o poll de 2s já entrega a transição OPEN→CLOSED com ±2 s de graça.
// O trigger correto é medir movimento na PRÓPRIA ROI do vídeo: **o trigger e o sensor são o
// mesmo pixel**, então não existe seletor novo de DOM para apodrecer quando a Evolution
// mudar o layout.
//
// Este módulo é PURO: recebe um vetor de luma grosseiro (ver `unwrap.roiLumaGrid`) e o
// relógio; não conhece `<video>`, nem `chrome.*`.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSMotionTrigger = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var DEFAULTS = {
    threshold: 4.0,        // diferença média absoluta de luma (0-255) que conta como movimento
    minIntervalMs: 900,    // ~1 FPS
    refractoryMs: 8000,    // não redispara no meio da mesma medição
    quietFramesToArm: 2    // precisa de 2 amostras quietas antes de armar de novo
  };

  function meanAbsDiff(a, b) {
    if (!a || !b || a.length !== b.length) return NaN;
    var s = 0, c = 0;
    for (var i = 0; i < a.length; i++) {
      if (!isFinite(a[i]) || !isFinite(b[i])) continue;
      s += Math.abs(a[i] - b[i]); c++;
    }
    return c > 0 ? s / c : NaN;
  }

  function createMotionTrigger(opts) {
    var cfg = Object.assign({}, DEFAULTS, opts || {});
    var prev = null;
    var prevT = null;
    var lastFireT = null;
    var quiet = cfg.quietFramesToArm;   // começa armado
    var samples = 0;

    /**
     * @param {Float64Array|Array} lumaGrid  luma grosseiro da ROI
     * @param {number} nowMs
     * @returns {{fired:boolean, reason:string, score:number}}
     */
    function push(lumaGrid, nowMs) {
      var res = { fired: false, reason: 'ok', score: NaN, armed: quiet >= cfg.quietFramesToArm };
      if (!lumaGrid) { res.reason = 'no_sample'; return res; }
      if (prevT !== null && (nowMs - prevT) < cfg.minIntervalMs) {
        res.reason = 'too_soon'; return res;
      }
      samples++;
      var score = prev ? meanAbsDiff(prev, lumaGrid) : NaN;
      prev = lumaGrid.slice ? lumaGrid.slice(0) : Array.prototype.slice.call(lumaGrid);
      prevT = nowMs;
      res.score = score;
      if (!isFinite(score)) { res.reason = 'warmup'; return res; }

      if (score < cfg.threshold) {
        if (quiet < cfg.quietFramesToArm) quiet++;
        res.reason = 'quiet';
        res.armed = quiet >= cfg.quietFramesToArm;
        return res;
      }
      if (lastFireT !== null && (nowMs - lastFireT) < cfg.refractoryMs) {
        res.reason = 'refractory'; return res;
      }
      if (quiet < cfg.quietFramesToArm) { res.reason = 'not_armed'; return res; }

      quiet = 0;
      lastFireT = nowMs;
      res.fired = true;
      res.reason = 'motion';
      return res;
    }

    function state() {
      return { samples: samples, armed: quiet >= cfg.quietFramesToArm, lastFireT: lastFireT };
    }

    function reset() { prev = null; prevT = null; lastFireT = null; quiet = cfg.quietFramesToArm; samples = 0; }

    return { push: push, state: state, reset: reset, config: cfg };
  }

  return { DEFAULTS: DEFAULTS, createMotionTrigger: createMotionTrigger, meanAbsDiff: meanAbsDiff };
}));
