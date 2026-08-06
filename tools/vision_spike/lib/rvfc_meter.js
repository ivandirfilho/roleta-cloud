// SPR-V3 · vision_spike/lib/rvfc_meter.js — instrumento da probe E0b (COBERTURA).
//
// Pergunta que este medidor existe para responder (e que ninguém pode PRESUMIR):
// o `<video>` continua entregando frames com a aba OCULTA e com a janela MINIMIZADA?
// `captureVisibleTab` é cego nessas condições — mas o `<video>` pode não ser.
// (§10.6-2: o aceite formal da cobertura medida é decisão HUMANA.)
//
// Disciplina de relógio (a que a crítica cobrou):
//   • `mediaTime` (do `metadata` do rVFC) é a régua do STREAM — usado para deslocamento;
//   • wall-clock (`performance.now`) é a régua da MÁQUINA — usado só para callbacks/s;
//   • `presentedFrames` detecta frames que o compositor apresentou mas o callback perdeu.
// Misturar as três é como o spike produziria um número bonito e errado.
//
// Módulo PURO: nos testes os timestamps são sintéticos; no navegador vêm do rVFC.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSRvfcMeter = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var DEFAULTS = {
    bucketMs: 1000,
    maxBuckets: 7200,       // 2h de soak a 1 bucket/s
    maxIntervals: 7200,     // ring: `summary()` roda a cada 2s e ordena esta lista
    gapFactor: 3            // gap = intervalo > 3× a mediana observada
  };

  /**
   * @param {Object} opts
   * @returns {{record:Function, summary:Function, series:Function, reset:Function}}
   */
  function createFrameRateMeter(opts) {
    var cfg = Object.assign({}, DEFAULTS, opts || {});
    var buckets = [];          // {t0, count, visible, hidden, focused, blurred}
    var first = null, last = null;
    var intervals = [];
    var gaps = [];
    var presentedFirst = null, presentedLast = null;
    var mediaFirst = null, mediaLast = null;
    var dropped = 0;
    var total = 0;
    // Fases do protocolo E0b. Registradas por MARCA EXPLÍCITA, não inferidas das amostras:
    // se o player parar de entregar frames com a janela minimizada, NÃO chega amostra
    // nenhuma — e uma fase silenciosa inferida de amostras simplesmente não existiria.
    // O resultado "0 callbacks em 180 s" é o achado mais importante que este instrumento
    // pode produzir; ele não pode virar `null`/fase ausente.
    var phases = [];           // {name, startedAtMs, endedAtMs, callbacks, mediaStartS, mediaEndS}
    var currentPhase = null;

    function markPhase(name, wallMs) {
      if (!isFinite(wallMs)) wallMs = (typeof performance !== 'undefined' && performance.now)
        ? performance.now() : Date.now();
      if (currentPhase) currentPhase.endedAtMs = wallMs;
      currentPhase = {
        name: String(name || 'unnamed'),
        startedAtMs: wallMs,
        endedAtMs: null,
        callbacks: 0,
        mediaStartS: null,
        mediaEndS: null
      };
      phases.push(currentPhase);
      return currentPhase;
    }

    function bucketFor(wallMs) {
      var t0 = Math.floor(wallMs / cfg.bucketMs) * cfg.bucketMs;
      var b = buckets.length ? buckets[buckets.length - 1] : null;
      if (!b || b.t0 !== t0) {
        b = { t0: t0, count: 0, visible: 0, hidden: 0, focused: 0, blurred: 0 };
        buckets.push(b);
        if (buckets.length > cfg.maxBuckets) buckets.shift();
      }
      return b;
    }

    /**
     * @param {Object} s  `{wallMs, mediaTime?, presentedFrames?, visibilityState?, hasFocus?}`
     */
    function record(s) {
      if (!s || !isFinite(s.wallMs)) return;
      total++;
      if (first === null) first = s.wallMs;
      if (last !== null) {
        var dt = s.wallMs - last;
        // Ring: sem teto, um soak de 2h a 30 fps guarda 216 mil intervalos e cada
        // `summary()` (a cada 2s) ordena a lista inteira — o medidor passaria a perturbar
        // a medição que ele existe para fazer.
        if (dt > 0) {
          intervals.push(dt);
          if (intervals.length > cfg.maxIntervals) intervals.shift();
        }
      }
      last = s.wallMs;

      var b = bucketFor(s.wallMs);
      b.count++;
      if (s.visibilityState === 'hidden') b.hidden++; else b.visible++;
      if (s.hasFocus === false) b.blurred++; else b.focused++;

      if (isFinite(s.mediaTime)) {
        if (mediaFirst === null) mediaFirst = s.mediaTime;
        mediaLast = s.mediaTime;
        if (currentPhase) {
          if (currentPhase.mediaStartS === null) currentPhase.mediaStartS = s.mediaTime;
          currentPhase.mediaEndS = s.mediaTime;
        }
      }
      if (currentPhase) currentPhase.callbacks++;
      if (isFinite(s.presentedFrames)) {
        if (presentedFirst === null) presentedFirst = s.presentedFrames;
        else if (s.presentedFrames - presentedLast > 1) {
          dropped += (s.presentedFrames - presentedLast - 1);
        }
        presentedLast = s.presentedFrames;
      }
    }

    function medianOf(a) {
      if (!a.length) return NaN;
      var s = a.slice().sort(function (x, y) { return x - y; });
      var m = s.length >> 1;
      return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
    }

    function summary(nowMs) {
      var medInt = medianOf(intervals);
      gaps = [];
      for (var i = 0; i < intervals.length; i++) {
        if (isFinite(medInt) && intervals[i] > cfg.gapFactor * medInt) gaps.push(intervals[i]);
      }
      var spanS = (first !== null && last !== null) ? (last - first) / 1000 : 0;
      var counts = buckets.map(function (b) { return b.count; });
      var hiddenBuckets = buckets.filter(function (b) { return b.hidden > b.visible; });
      var visibleBuckets = buckets.filter(function (b) { return b.visible >= b.hidden; });

      function stat(list) {
        if (!list.length) return { buckets: 0, fpsMean: null, fpsMin: null, fpsMax: null };
        var c = list.map(function (b) { return b.count; });
        var sum = c.reduce(function (a, b) { return a + b; }, 0);
        return {
          buckets: list.length,
          fpsMean: sum / list.length,
          fpsMin: Math.min.apply(null, c),
          fpsMax: Math.max.apply(null, c)
        };
      }

      return {
        callbacks: total,
        spanSeconds: spanS,
        // callbacks/s no relógio da MÁQUINA (só isto usa wall-clock)
        callbacksPerSecond: spanS > 0 ? total / spanS : null,
        medianIntervalMs: medInt,
        gapCount: gaps.length,
        longestGapMs: gaps.length ? Math.max.apply(null, gaps) : 0,
        // avanço do STREAM (só isto usa mediaTime)
        mediaTimeAdvancedS: (mediaFirst !== null && mediaLast !== null) ? mediaLast - mediaFirst : null,
        presentedFrames: (presentedFirst !== null && presentedLast !== null)
          ? presentedLast - presentedFirst : null,
        // callbacks perdidos entre apresentações consecutivas do compositor
        missedPresentedFrames: dropped,
        buckets: counts.length,
        byVisibility: { visible: stat(visibleBuckets), hidden: stat(hiddenBuckets) },
        byPhase: phaseSummary(nowMs)
      };
    }

    /**
     * Uma linha por fase do protocolo, SEMPRE — inclusive as silenciosas.
     * `callbacksPerSecond: 0` com `durationSeconds: 180` é um resultado; `null` seria a
     * ausência de um. É essa distinção que separa "o player parou" de "ninguém mediu".
     */
    function phaseSummary(nowMs) {
      if (!isFinite(nowMs)) {
        nowMs = (typeof performance !== 'undefined' && performance.now)
          ? performance.now() : Date.now();
      }
      return phases.map(function (p) {
        var end = p.endedAtMs === null ? nowMs : p.endedAtMs;
        var durS = Math.max(0, (end - p.startedAtMs) / 1000);
        return {
          name: p.name,
          startedAtMs: p.startedAtMs,
          endedAtMs: p.endedAtMs,
          open: p.endedAtMs === null,
          durationSeconds: durS,
          callbacks: p.callbacks,
          callbacksPerSecond: durS > 0 ? p.callbacks / durS : (p.callbacks > 0 ? null : 0),
          mediaTimeAdvancedS: (p.mediaStartS !== null && p.mediaEndS !== null)
            ? p.mediaEndS - p.mediaStartS : 0,
          silent: p.callbacks === 0
        };
      });
    }

    function series() {
      return buckets.map(function (b) {
        return { t0: b.t0, count: b.count, hidden: b.hidden, visible: b.visible, blurred: b.blurred };
      });
    }

    function reset() {
      buckets = []; first = null; last = null; intervals = []; gaps = [];
      presentedFirst = presentedLast = mediaFirst = mediaLast = null;
      dropped = 0; total = 0; phases = []; currentPhase = null;
    }

    return {
      record: record, summary: summary, series: series, reset: reset,
      markPhase: markPhase, phases: function () { return phaseSummary(); },
      config: cfg
    };
  }

  /**
   * DECIMADOR de cadência — a peça que impede o coletor de abster 100% num feed rápido.
   *
   * O `requestVideoFrameCallback` entrega na taxa NATIVA do stream (25-30 fps numa mesa
   * ao vivo). Gravar 6 frames consecutivos daí dá ~200 ms de janela total, e o guard
   * `stride_too_small` (que exige Δt_par ≥ 270 ms) dispara SEMPRE. O resultado seria
   * cobertura 0/N em campo — um NO-GO que é defeito de ferramental, não do mundo.
   *
   * Este decimador aceita um frame só quando ele está a `targetIntervalS` do último
   * aceito, medido preferencialmente em `mediaTime` (a régua do stream).
   *
   * ⚠️ `tolerance` **é 1.0 e não deve ser reduzida**. A versão anterior aceitava a 90% do
   * alvo, o que parecia inofensivo e não era: o guard `stride_too_small` exige **100%** do
   * intervalo, então feeds de 12, 24 e 60 fps caíam num ponto em que o decimador aceitava
   * (dt = 83 ms ≥ 90 % de 90 ms) e o guard reprovava (83 < 90) — cobertura 0/N de novo,
   * exatamente o defeito que o decimador existe para consertar. O limiar do decimador e o
   * do guard têm de ser **o mesmo número**.
   *
   * @param {{targetIntervalS:number, tolerance?:number}} opts
   */
  function createDecimator(opts) {
    var target = (opts && opts.targetIntervalS) || 0.1;
    var tol = (opts && opts.tolerance != null) ? opts.tolerance : 1.0;
    var minGap = target * tol;
    var lastT = null;
    var seen = 0, accepted = 0;

    /** @param {number} t  tempo em SEGUNDOS (mediaTime de preferência) */
    function accept(t) {
      seen++;
      if (!isFinite(t)) return false;
      if (lastT !== null && (t - lastT) < minGap) return false;
      lastT = t;
      accepted++;
      return true;
    }

    return {
      accept: accept,
      targetIntervalS: target,
      minGapS: minGap,
      stats: function () { return { seen: seen, accepted: accepted }; },
      reset: function () { lastT = null; seen = 0; accepted = 0; }
    };
  }

  return { DEFAULTS: DEFAULTS, createFrameRateMeter: createFrameRateMeter, createDecimator: createDecimator };
}));
