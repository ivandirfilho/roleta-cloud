// SPR-V3 · vision_spike/lib/direction_core.js — estimador de sentido do ROTOR.
//
// O produto deste sprint é a HONESTIDADE do estimador, não o veredito. Por isso este
// módulo abstém com facilidade e nunca "palpita".
//
// Defeitos que ele existe para não repetir (auditoria §10.2.1)
// -----------------------------------------------------------
// D2  A bolinha (1-3 rev/s) sofre aliasing brutal ⇒ medimos o ROTOR (0,2-0,5 rev/s).
// D3  Correlação 2D mede translação ⇒ operamos sobre o perfil ANGULAR já desenrolado.
// D4  37 bolsos ≈ pente a cada 9,73° ⇒ a correlação trava em múltiplos do período.
// D5  "Confidence por consistência entre pares" é DESONESTA: aliasing é erro SISTEMÁTICO,
//     os pares erram JUNTOS e concordam entre si. Consistência entra como guard, jamais
//     como prova.
//
// Três defesas independentes contra D4/D5 (nenhuma sozinha basta)
// --------------------------------------------------------------
// 1. **Margem de alias**: enumeramos TODOS os máximos locais em ±120° e comparamos o pico
//    contra o melhor concorrente. Pico empatado ⇒ `alias_margin_low` ⇒ abstenção.
// 2. **Landmark do zero verde** (evidência INDEPENDENTE da correlação): o setor verde é
//    único em 37. Sua posição é rastreada por frame; o deslocamento do landmark tem de
//    concordar com o lag da correlação dentro de `landmarkTolDeg` — que é deliberadamente
//    MENOR que o período do bolso (9,73°), senão um alias de ±1 bolso passaria.
//    Landmark ausente/fraco ⇒ `zero_landmark_missing`. Discordante ⇒ `zero_landmark_disagrees`.
// 3. **Passo temporal seguro**: se o prior físico admitir deslocamento < 2 períodos de
//    bolso no Δt do par, um alias de ±1 bolso pode INVERTER O SINAL. Isso é aritmética,
//    não opinião: a 10 fps com stride 1 (Δt=0,1 s) o rotor anda 7,2-18° e o alias vizinho
//    cai em −2,5° — sinal trocado. Guard `stride_too_small` obriga aumentar o stride.
//
// `confidence` é um ESCORE HEURÍSTICO de qualidade da medida, **não** uma probabilidade
// calibrada. Nada neste arquivo autoriza chamá-la de "97% de chance de estar certo".
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSDirection = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var POCKET_COUNT = 37;
  var POCKET_PERIOD_DEG = 360 / POCKET_COUNT;   // 9,7297...

  var DEFAULTS = {
    maxLagDeg: 120,            // janela de busca (±120°) — o brief
    emitFloor: 0.70,           // piso de emissão da fusão
    guardedConfidenceCap: 0.50,// "qualquer guard ⇒ confidence ≤0,5"
    minFrames: 6,              // 6 frames com stride 3 = 3 pares
    minPairs: 3,               // "consistência entre 3 pares" — com 1 par ela não existe
    pairStride: 3,             // ver `stride_too_small`
    rotorRevPerSecMin: 0.20,
    rotorRevPerSecMax: 0.50,
    priorToleranceFactor: 1.6, // folga sobre o prior antes de acusar magnitude
    minDtS: 0.01,              // por unidade de stride
    maxDtS: 0.25,              // por unidade de stride
    lumaMin: 20,
    lumaMax: 245,
    minSceneNcc: 0.60,
    maxInvalidFrac: 0.02,
    minHpStd: 0.30,            // energia mínima após high-pass (unidades de croma)
    aliasMarginMin: 0.25,
    aliasExcludeBins: 6,       // ±3° em torno do pico ao procurar o concorrente
    landmarkTolDeg: 8.0,       // < 9,73° de propósito
    landmarkMinMargin: 0.50,   // ver `findZeroLandmark`
    landmarkSmoothBins: 9,     // ~meio bolso: tira textura, preserva o setor verde
    minAliasSafetyDeg: 2 * POCKET_PERIOD_DEG
  };

  /**
   * Intervalo mínimo ENTRE FRAMES ACEITOS para que o guard `stride_too_small` não seja
   * inevitável. Sai direto da aritmética do guard:
   *
   *     Δt_do_par = stride × intervalo   e   Δt_do_par ≥ minAliasSafetyDeg / (rev_min × 360)
   *
   * Com os defaults: 19,46° / 72°/s / 3 = 90,09 ms — e devolvemos esse mínimo com uma
   * **margem de 2%** (91,9 ms), porque o guard compara `>=` sobre floats calculados por
   * caminhos diferentes: aceitar exatamente no limite deixa a decisão na mão do último bit
   * da mantissa. ~11 fps efetivos.
   *
   * Um feed a 12, 24, 25, 30 ou 60 fps precisa ser DECIMADO até essa cadência: gravar 6
   * frames consecutivos de um stream de 30 fps dá 167 ms de janela e o estimador abstém
   * sempre — o coletor mediria zero e o campo leria isso como "o mundo não coopera".
   */
  function minimumFrameIntervalS(options) {
    var cfg = Object.assign({}, DEFAULTS, options || {});
    var stride = Math.max(1, cfg.pairStride | 0);
    return cfg.minAliasSafetyDeg / (cfg.rotorRevPerSecMin * 360) / stride;
  }

  var FRAME_INTERVAL_SAFETY = 1.02;

  function recommendedFrameIntervalS(options) {
    return minimumFrameIntervalS(options) * FRAME_INTERVAL_SAFETY;
  }

  function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

  function median(arr) {
    var a = Array.prototype.slice.call(arr).filter(function (v) { return isFinite(v); });
    if (!a.length) return NaN;
    a.sort(function (x, y) { return x - y; });
    var m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  }

  function mad(arr, med) {
    var a = [];
    for (var i = 0; i < arr.length; i++) if (isFinite(arr[i])) a.push(Math.abs(arr[i] - med));
    if (!a.length) return NaN;
    a.sort(function (x, y) { return x - y; });
    var m = a.length >> 1;
    return (a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2) * 1.4826;
  }

  function smoothCircular(v, k) {
    var n = v.length;
    var out = new Float64Array(n);
    var half = Math.max(0, Math.floor(k / 2));
    for (var i = 0; i < n; i++) {
      var s = 0, c = 0;
      for (var d = -half; d <= half; d++) {
        var x = v[(i + d + n) % n];
        if (isFinite(x)) { s += x; c++; }
      }
      out[i] = c ? s / c : NaN;
    }
    return out;
  }

  function hasNaN(v) {
    for (var i = 0; i < v.length; i++) if (!isFinite(v[i])) return true;
    return false;
  }

  /**
   * Correlação CIRCULAR 1D normalizada, limitada a ±maxLag bins.
   * corr[lag] alto ⇒ `b` é `a` deslocado de `+lag` bins (θ crescente = horário na tela).
   */
  function circularXCorr(a, b, maxLag) {
    var n = a.length;
    var ma = 0, mb = 0, i;
    for (i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
    ma /= n; mb /= n;
    var na = 0, nb = 0;
    for (i = 0; i < n; i++) { na += (a[i] - ma) * (a[i] - ma); nb += (b[i] - mb) * (b[i] - mb); }
    var denom = Math.sqrt(na * nb);
    var out = new Float64Array(2 * maxLag + 1);
    for (var lag = -maxLag; lag <= maxLag; lag++) {
      var s = 0;
      for (i = 0; i < n; i++) s += (a[i] - ma) * (b[(i + lag % n + n) % n] - mb);
      out[lag + maxLag] = denom > 0 ? s / denom : 0;
    }
    return out;
  }

  // Interpolação parabólica de sub-bin em torno do índice do pico.
  function refinePeak(corr, idx) {
    if (idx <= 0 || idx >= corr.length - 1) return idx;
    var y0 = corr[idx - 1], y1 = corr[idx], y2 = corr[idx + 1];
    var d = (y0 - 2 * y1 + y2);
    if (d === 0) return idx;
    var delta = 0.5 * (y0 - y2) / d;
    if (!isFinite(delta) || Math.abs(delta) > 1) return idx;
    return idx + delta;
  }

  function localMaxima(corr) {
    var out = [];
    var n = corr.length;
    for (var i = 1; i < n - 1; i++) {
      if (corr[i] >= corr[i - 1] && corr[i] > corr[i + 1]) out.push(i);
    }
    return out;
  }

  function argmax(v) {
    var bi = 0;
    for (var i = 1; i < v.length; i++) if (v[i] > v[bi]) bi = i;
    return bi;
  }

  function wrapDegSigned(d) {
    while (d > 180) d -= 360;
    while (d <= -180) d += 360;
    return d;
  }

  function percentile(sorted, p) {
    if (!sorted.length) return NaN;
    var i = Math.min(sorted.length - 1, Math.max(0, Math.round(p * (sorted.length - 1))));
    return sorted[i];
  }

  /**
   * Landmark do ZERO VERDE — evidência INDEPENDENTE da correlação.
   *
   * A pergunta certa não é "o verde é brilhante?" e sim **"existe um setor ÚNICO?"** — é a
   * unicidade que quebra a ambiguidade de 37 dobras. Por isso a métrica é uma MARGEM DE
   * UNICIDADE, não uma prominência contra a mediana:
   *
   *     margem = (pico − melhor outro máximo local a mais de 1 bolso de distância)
   *              ────────────────────────────────────────────────────────────────
   *                             (p90 − p10 do próprio perfil)
   *
   * Prominência por MAD FALHA aqui e o spike descobriu isso na bancada: com o fundo bimodal
   * vermelho/preto o MAD é enorme e o verde legítimo marca z≈3,9 — indistinguível de ruído.
   * A margem de unicidade dá ≈1,4 com verde e ≈0 sem verde. Sem esse número, `direction_core`
   * estaria confiando num detector que não detecta.
   */
  function findZeroLandmark(chromaProfile, degPerBin, cfg) {
    cfg = Object.assign({}, DEFAULTS, cfg || {});
    var sm = smoothCircular(chromaProfile, cfg.landmarkSmoothBins);
    var idx = argmax(sm);
    var pocketBins = Math.max(1, Math.round(POCKET_PERIOD_DEG / degPerBin));
    var n = sm.length;

    var best = -Infinity;
    var lm = localMaxima(sm);
    for (var i = 0; i < lm.length; i++) {
      var d = Math.abs(lm[i] - idx);
      d = Math.min(d, n - d);                       // distância circular
      if (d <= pocketBins) continue;                // vizinhança do próprio pico
      if (sm[lm[i]] > best) best = sm[lm[i]];
    }

    var sorted = Array.prototype.slice.call(sm).filter(isFinite).sort(function (a, b) { return a - b; });
    var spread = percentile(sorted, 0.90) - percentile(sorted, 0.10);
    var margin = (spread > 0 && isFinite(best)) ? (sm[idx] - best) / spread : NaN;

    var med = median(sm);
    var sd = mad(sm, med);
    var z = (sd > 0 && isFinite(sd)) ? (sm[idx] - med) / sd : NaN;

    return {
      deg: idx * degPerBin,
      index: idx,
      margin: margin,
      z: z,                                          // informativo, NÃO é o gate
      spread: spread,
      present: isFinite(margin) && margin >= cfg.landmarkMinMargin
    };
  }

  function highPassWindow(profiles) {
    var t = profiles.length, n = profiles[0].length, i, k;
    var mean = new Float64Array(n);
    for (k = 0; k < n; k++) {
      var s = 0;
      for (i = 0; i < t; i++) s += profiles[i][k];
      mean[k] = s / t;
    }
    var out = [];
    for (i = 0; i < t; i++) {
      var row = new Float64Array(n);
      for (k = 0; k < n; k++) row[k] = profiles[i][k] - mean[k];
      out.push(row);
    }
    return out;
  }

  function stdOf(v) {
    var n = v.length, s = 0, i;
    for (i = 0; i < n; i++) s += v[i];
    var m = s / n, q = 0;
    for (i = 0; i < n; i++) q += (v[i] - m) * (v[i] - m);
    return Math.sqrt(q / n);
  }

  /**
   * Analisa uma JANELA de frames já desenrolados.
   *
   * @param {Array} frames  itens `{mediaTimeS?, tMs, chroma, meanLuma, invalidFrac, ncc}`
   * @param {Object} calib  `{degPerBin?, mirrored?}`
   * @param {Object} options sobrescreve DEFAULTS
   * @returns {Object} `{direction, confidence, guards, ...evidência}` — `direction` é
   *                   SEMPRE `null` quando há guard ou confidence < piso.
   */
  function analyzeWindow(frames, calib, options) {
    var cfg = Object.assign({}, DEFAULTS, options || {});
    calib = calib || {};
    var degPerBin = calib.degPerBin || 0.5;
    var guards = [];
    var evidence = {
      frames: Array.isArray(frames) ? frames.length : 0,
      degPerBin: degPerBin,
      pairStride: cfg.pairStride,
      pockedPeriodDeg: POCKET_PERIOD_DEG,
      dtSource: null
    };

    function abstain(extra) {
      return Object.assign({
        direction: null,
        emitted: false,
        confidence: 0,
        guards: guards.slice(),
        evidence: evidence
      }, extra || {});
    }

    if (!Array.isArray(frames) || frames.length < cfg.minFrames) {
      guards.push('insufficient_frames');
      return abstain();
    }

    // --- guards por frame (cena) -------------------------------------------------
    var i;
    for (i = 0; i < frames.length; i++) {
      var f = frames[i];
      if (!f || !f.chroma || !f.chroma.length) { guards.push('sample_invalid'); return abstain(); }
      if (hasNaN(f.chroma)) { guards.push('sample_invalid'); break; }
      if (!(f.meanLuma >= cfg.lumaMin && f.meanLuma <= cfg.lumaMax)) {
        if (guards.indexOf('luma_out_of_range') < 0) guards.push('luma_out_of_range');
      }
      if (!(f.invalidFrac <= cfg.maxInvalidFrac)) {
        if (guards.indexOf('roi_out_of_bounds') < 0) guards.push('roi_out_of_bounds');
      }
      // NCC NaN = "não sei" ⇒ guard. Nunca tratar ausência de prova como prova.
      if (!(f.ncc >= cfg.minSceneNcc)) {
        if (guards.indexOf('scene_ncc_low') < 0) guards.push('scene_ncc_low');
      }
    }

    // --- Δt: mediaTime é a régua; wall-clock é telemetria -------------------------
    var useMedia = frames.every(function (f) { return isFinite(f.mediaTimeS); });
    evidence.dtSource = useMedia ? 'mediaTime' : 'wallClock';
    if (!useMedia && guards.indexOf('dt_from_wall_clock') < 0) guards.push('dt_from_wall_clock');
    function tOf(f) { return useMedia ? f.mediaTimeS : (f.tMs / 1000); }

    // --- pares ------------------------------------------------------------------
    var stride = Math.max(1, cfg.pairStride | 0);
    var pairs = [];
    for (i = 0; i + stride < frames.length; i++) pairs.push([i, i + stride]);
    if (pairs.length < 1) { guards.push('insufficient_frames'); return abstain(); }
    if (pairs.length > 3) pairs = pairs.slice(0, 3);      // 3 pares, como o desenho manda
    if (pairs.length < cfg.minPairs) {
      // Com menos de 3 pares a "consistência entre pares" não é fraca: ela não EXISTE.
      if (guards.indexOf('too_few_pairs') < 0) guards.push('too_few_pairs');
    }
    evidence.pairCount = pairs.length;

    // --- high-pass temporal: mata overlay ESTÁTICO (e o pente estático junto) ----
    var hp = highPassWindow(frames.map(function (f) { return f.chroma; }));
    var energies = hp.map(stdOf);
    evidence.hpStd = energies;
    if (!energies.every(function (s) { return s >= cfg.minHpStd; })) {
      if (guards.indexOf('low_energy') < 0) guards.push('low_energy');
    }

    var maxLagBins = Math.round(cfg.maxLagDeg / degPerBin);
    var priorMinDegPerS = cfg.rotorRevPerSecMin * 360 / cfg.priorToleranceFactor;
    var priorMaxDegPerS = cfg.rotorRevPerSecMax * 360 * cfg.priorToleranceFactor;

    var lagsDeg = [], degPerSec = [], peaks = [], margins = [], dts = [];
    for (var p = 0; p < pairs.length; p++) {
      var ia = pairs[p][0], ib = pairs[p][1];
      var dt = tOf(frames[ib]) - tOf(frames[ia]);
      dts.push(dt);
      if (!(dt >= cfg.minDtS * stride && dt <= cfg.maxDtS * stride)) {
        if (guards.indexOf('frame_gap') < 0) guards.push('frame_gap');
      }
      var corr = circularXCorr(hp[ia], hp[ib], maxLagBins);
      var pk = argmax(corr);
      var refined = refinePeak(corr, pk);
      var lagDeg = (refined - maxLagBins) * degPerBin;

      // concorrente: melhor máximo local FORA da vizinhança do pico (em ±120° inteiro —
      // não restringimos ao prior, senão o prior "salvaria" uma medida ambígua).
      var best = -Infinity;
      var lm = localMaxima(corr);
      for (var q = 0; q < lm.length; q++) {
        if (Math.abs(lm[q] - pk) <= cfg.aliasExcludeBins) continue;
        if (corr[lm[q]] > best) best = corr[lm[q]];
      }
      var peakVal = corr[pk];
      var margin = (peakVal > 0 && isFinite(best))
        ? clamp01((peakVal - best) / Math.abs(peakVal))
        : (isFinite(best) ? 0 : 1);

      lagsDeg.push(lagDeg);
      degPerSec.push(dt !== 0 ? lagDeg / dt : NaN);
      peaks.push(peakVal);
      margins.push(margin);
    }
    evidence.lagsDeg = lagsDeg;
    evidence.degPerSec = degPerSec;
    evidence.peakCorr = peaks;
    evidence.aliasMargins = margins;
    evidence.dts = dts;

    var aliasMargin = Math.min.apply(null, margins);
    if (!(aliasMargin >= cfg.aliasMarginMin)) {
      if (guards.indexOf('alias_margin_low') < 0) guards.push('alias_margin_low');
    }

    // --- passo temporal seguro contra alias de ±1 bolso --------------------------
    var meanDt = dts.reduce(function (a, b) { return a + b; }, 0) / dts.length;
    var minExpectedDeg = cfg.rotorRevPerSecMin * 360 * meanDt;
    evidence.minExpectedDeg = minExpectedDeg;
    if (!(minExpectedDeg >= cfg.minAliasSafetyDeg)) {
      if (guards.indexOf('stride_too_small') < 0) guards.push('stride_too_small');
    }

    // --- sinal consistente entre os 3 pares (guard, NUNCA prova) ----------------
    var signs = lagsDeg.map(function (d) { return d > 0 ? 1 : (d < 0 ? -1 : 0); });
    var sign = signs[0];
    if (sign === 0 || !signs.every(function (s) { return s === sign; })) {
      if (guards.indexOf('sign_inconsistent') < 0) guards.push('sign_inconsistent');
    }

    // --- prior de magnitude ------------------------------------------------------
    var absSpeeds = degPerSec.map(Math.abs);
    var meanSpeed = absSpeeds.reduce(function (a, b) { return a + b; }, 0) / absSpeeds.length;
    evidence.meanAbsDegPerSec = meanSpeed;
    if (!(meanSpeed >= priorMinDegPerS && meanSpeed <= priorMaxDegPerS)) {
      if (guards.indexOf('magnitude_out_of_prior') < 0) guards.push('magnitude_out_of_prior');
    }

    // --- landmark do zero verde: evidência INDEPENDENTE --------------------------
    var lms = frames.map(function (f) { return findZeroLandmark(f.chroma, degPerBin, cfg); });
    evidence.landmarkMargin = lms.map(function (l) { return l.margin; });
    evidence.landmarkZ = lms.map(function (l) { return l.z; });
    if (!lms.every(function (l) { return l.present; })) {
      if (guards.indexOf('zero_landmark_missing') < 0) guards.push('zero_landmark_missing');
    }
    var lmShifts = pairs.map(function (pr) {
      return wrapDegSigned(lms[pr[1]].deg - lms[pr[0]].deg);
    });
    evidence.landmarkShiftsDeg = lmShifts;
    var lmDiffs = lmShifts.map(function (s, k) { return Math.abs(wrapDegSigned(s - lagsDeg[k])); });
    evidence.landmarkDisagreementDeg = lmDiffs;
    var worstLmDiff = Math.max.apply(null, lmDiffs);
    if (!(worstLmDiff <= cfg.landmarkTolDeg)) {
      if (guards.indexOf('zero_landmark_disagrees') < 0) guards.push('zero_landmark_disagrees');
    }

    // --- confidence HEURÍSTICA ---------------------------------------------------
    var peakQuality = clamp01(Math.min.apply(null, peaks));
    var marginScore = clamp01(aliasMargin / 0.5);
    var lmScore = clamp01(1 - worstLmDiff / cfg.landmarkTolDeg);
    var confidence = clamp01(0.35 * peakQuality + 0.35 * marginScore + 0.30 * lmScore);
    if (guards.length > 0) confidence = Math.min(confidence, cfg.guardedConfidenceCap);

    var label = null;
    if (guards.length === 0 && confidence >= cfg.emitFloor) {
      // θ crescente = horário NA TELA (ver unwrap.js). `mirrored` inverte o rótulo.
      label = sign > 0 ? 'cw' : 'ccw';
      if (calib.mirrored === true) label = (label === 'cw') ? 'ccw' : 'cw';
    }

    return {
      direction: label,                 // null em QUALQUER abstenção
      emitted: label !== null,
      confidence: confidence,
      guards: guards.slice(),
      degreesPerSecond: sign * meanSpeed,
      aliasMargin: aliasMargin,
      landmarkWorstDisagreementDeg: worstLmDiff,
      confidenceKind: 'heuristic_quality_score',   // NÃO é probabilidade calibrada
      evidence: evidence
    };
  }

  return {
    DEFAULTS: DEFAULTS,
    POCKET_COUNT: POCKET_COUNT,
    POCKET_PERIOD_DEG: POCKET_PERIOD_DEG,
    analyzeWindow: analyzeWindow,
    circularXCorr: circularXCorr,
    recommendedFrameIntervalS: recommendedFrameIntervalS,
    minimumFrameIntervalS: minimumFrameIntervalS,
    FRAME_INTERVAL_SAFETY: FRAME_INTERVAL_SAFETY,
    findZeroLandmark: findZeroLandmark,
    highPassWindow: highPassWindow,
    _localMaxima: localMaxima,
    _refinePeak: refinePeak,
    _smoothCircular: smoothCircular,
    _median: median,
    _mad: mad,
    _wrapDegSigned: wrapDegSigned
  };
}));
