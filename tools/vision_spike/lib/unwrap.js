// SPR-V3 · vision_spike/lib/unwrap.js — unwrap ELÍPTICO e perfis angulares.
//
// O que este módulo resolve
// -------------------------
// Correlação de fase 2D mede TRANSLAÇÃO, não rotação (defeito D3 da auditoria). Para
// transformar rotação em translação é preciso "desenrolar" a coroa dos bolsos em torno do
// centro: cada ângulo vira uma coluna, cada raio vira uma linha. Rodar o rotor passa a ser
// DESLOCAR o vetor angular — e aí uma correlação 1D circular responde a pergunta certa.
//
// Convenção angular (declarada, não implícita)
// -------------------------------------------
// Coordenadas de IMAGEM: x → direita, y → BAIXO. Amostramos
//     p(θ, ρ) = centro + R(φ) · (ρ·a·cos θ, ρ·b·sin θ)
// Com y para baixo, **θ crescente percorre a elipse no sentido HORÁRIO NA TELA**.
// Logo um lag de correlação POSITIVO (o perfil migra para θ maior) = HORÁRIO NA TELA.
// "Na tela" ≠ "físico": se o feed estiver espelhado, `calibration.mirrored = true` inverte
// o rótulo. Quem arbitra o rótulo físico é a anotação humana do V3-B (gate H2) — este
// módulo mede deslocamento, não decreta CW/CCW do mundo.
//
// Bandas radiais (ρ é relativo à elipse calibrada)
// -----------------------------------------------
// A calibração traça a borda EXTERNA do disco de bolsos (o ROTOR). Portanto:
//   • ROTOR_BAND  ρ∈[0,55; 0,95] — a coroa dos bolsos, que GIRA (é o sinal);
//   • SCENE_BAND  ρ∈[1,15; 1,45] — aro/mesa em volta, que NÃO gira (é a assinatura de cena
//     para o NCC). Medir NCC sobre o rotor invalidaria toda cena legítima em movimento.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSUnwrap = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var ANGLES = 720;              // 0,5° por bin
  var RADII = 16;
  var ROTOR_BAND = [0.55, 0.95];
  var SCENE_BAND = [1.15, 1.45];
  var SCENE_ANGLES = 180;        // assinatura de cena: 2° por bin já basta para NCC
  var DEG_PER_BIN = 360 / ANGLES;

  function isFrame(f) {
    return !!f && f.data && f.width > 0 && f.height > 0 &&
      f.data.length >= f.width * f.height * 4;
  }

  // Amostragem bilinear em RGBA. Devolve null fora da imagem (o chamador CONTA os nulos:
  // ROI saindo do quadro é guard, não é "pixel preto").
  function sampleBilinear(frame, x, y, out) {
    var w = frame.width, h = frame.height, d = frame.data;
    if (!(x >= 0) || !(y >= 0) || x > w - 1 || y > h - 1) return null;
    var x0 = Math.floor(x), y0 = Math.floor(y);
    var x1 = x0 + 1 > w - 1 ? x0 : x0 + 1;
    var y1 = y0 + 1 > h - 1 ? y0 : y0 + 1;
    var fx = x - x0, fy = y - y0;
    var i00 = (y0 * w + x0) * 4, i10 = (y0 * w + x1) * 4;
    var i01 = (y1 * w + x0) * 4, i11 = (y1 * w + x1) * 4;
    for (var c = 0; c < 3; c++) {
      var top = d[i00 + c] * (1 - fx) + d[i10 + c] * fx;
      var bot = d[i01 + c] * (1 - fx) + d[i11 + c] * fx;
      out[c] = top * (1 - fy) + bot * fy;
    }
    return out;
  }

  function luma(r, g, b) { return 0.299 * r + 0.587 * g + 0.114 * b; }
  // Canal cromático: destaca o VERDE do zero (setor único em 37) e derruba a periodicidade
  // vermelho/preto dos bolsos — a mitigação prescrita para o aliasing de padrão (D4).
  // NÃO é garantia: `direction_core` mede a força do landmark e abstém se ele sumir.
  function chroma(r, g, b) { return g - (r + b) / 2; }

  // Média aparada (descarta os `trim` menores e maiores dos 16 raios): imune a reflexo
  // especular e a um bolso ocluído. Ordena IN PLACE por inserção num buffer reusado —
  // 720 `slice().sort()` por frame custavam mais que todo o resto do unwrap.
  function trimmedMean(buf, n, trim) {
    for (var i = 1; i < n; i++) {          // insertion sort (n<=16: mais rápido que sort())
      var v = buf[i], j = i - 1;
      while (j >= 0 && buf[j] > v) { buf[j + 1] = buf[j]; j--; }
      buf[j + 1] = v;
    }
    var lo = Math.min(trim, Math.floor((n - 1) / 2));
    var hi = n - lo;
    var s = 0, c = 0;
    for (var k = lo; k < hi; k++) { s += buf[k]; c++; }
    return c > 0 ? s / c : NaN;
  }

  function bandSampler(frame, calib, band, angles, radii, trim) {
    var cx = calib.center.x, cy = calib.center.y;
    var a = calib.a, b = calib.b, phi = calib.phi || 0;
    var cosP = Math.cos(phi), sinP = Math.sin(phi);
    var outChroma = new Float64Array(angles);
    var outLuma = new Float64Array(angles);
    var px = [0, 0, 0];
    var bufC = new Float64Array(radii);
    var bufL = new Float64Array(radii);
    var invalid = 0, total = 0, lumaSum = 0, lumaCount = 0;

    for (var i = 0; i < angles; i++) {
      var th = (i / angles) * 2 * Math.PI;
      var ct = Math.cos(th), st = Math.sin(th);
      var nC = 0, nL = 0;
      for (var j = 0; j < radii; j++) {
        var rho = band[0] + (band[1] - band[0]) * (radii === 1 ? 0.5 : j / (radii - 1));
        var ex = rho * a * ct, ey = rho * b * st;
        var x = cx + ex * cosP - ey * sinP;
        var y = cy + ex * sinP + ey * cosP;
        total++;
        if (!sampleBilinear(frame, x, y, px)) { invalid++; continue; }
        bufC[nC++] = chroma(px[0], px[1], px[2]);
        var lv = luma(px[0], px[1], px[2]);
        bufL[nL++] = lv;
        lumaSum += lv; lumaCount++;
      }
      outChroma[i] = nC > 0 ? trimmedMean(bufC, nC, trim) : NaN;
      outLuma[i] = nL > 0 ? trimmedMean(bufL, nL, trim) : NaN;
    }

    return {
      chroma: outChroma,
      luma: outLuma,
      invalidFrac: total > 0 ? invalid / total : 1,
      meanLuma: lumaCount > 0 ? lumaSum / lumaCount : NaN
    };
  }

  /**
   * Unwrap elíptico da coroa do ROTOR.
   * @returns {{ok:boolean, reason?:string, chroma:Float64Array, luma:Float64Array,
   *            meanLuma:number, invalidFrac:number, angles:number, degPerBin:number}}
   */
  function unwrapRotor(frame, calib, opts) {
    opts = opts || {};
    if (!isFrame(frame)) return { ok: false, reason: 'invalid_frame' };
    if (!calib || !calib.center || !(calib.a > 0) || !(calib.b > 0)) {
      return { ok: false, reason: 'invalid_calibration' };
    }
    var angles = opts.angles || ANGLES;
    var radii = opts.radii || RADII;
    var band = opts.band || calib.rotorBand || ROTOR_BAND;
    var r = bandSampler(frame, calib, band, angles, radii, opts.trim == null ? 2 : opts.trim);
    return {
      ok: true,
      chroma: r.chroma,
      luma: r.luma,
      meanLuma: r.meanLuma,
      invalidFrac: r.invalidFrac,
      angles: angles,
      degPerBin: 360 / angles
    };
  }

  /**
   * Assinatura da CENA (anel estático fora do rotor) para o guard de NCC.
   * Usar o rotor aqui invalidaria toda cena legítima — ele gira por definição.
   */
  function sceneSignature(frame, calib, opts) {
    opts = opts || {};
    if (!isFrame(frame)) return { ok: false, reason: 'invalid_frame' };
    if (!calib || !calib.center || !(calib.a > 0) || !(calib.b > 0)) {
      return { ok: false, reason: 'invalid_calibration' };
    }
    var angles = opts.angles || SCENE_ANGLES;
    var band = opts.band || calib.sceneBand || SCENE_BAND;
    var r = bandSampler(frame, calib, band, angles, opts.radii || 8, opts.trim == null ? 1 : opts.trim);
    return {
      ok: true,
      signature: r.luma,
      invalidFrac: r.invalidFrac,
      meanLuma: r.meanLuma,
      angles: angles
    };
  }

  /**
   * Vetor de luma grosseiro da ROI, para o TRIGGER de movimento a ~1 FPS.
   * O trigger e o sensor são o MESMO pixel: zero seletor de DOM novo para apodrecer.
   */
  function roiLumaGrid(frame, calib, size) {
    size = size || 12;
    if (!isFrame(frame)) return null;
    var out = new Float64Array(size * size);
    var px = [0, 0, 0];
    var cx = calib.center.x, cy = calib.center.y;
    var a = calib.a, b = calib.b, phi = calib.phi || 0;
    var cosP = Math.cos(phi), sinP = Math.sin(phi);
    for (var gy = 0; gy < size; gy++) {
      for (var gx = 0; gx < size; gx++) {
        var u = ((gx + 0.5) / size) * 2 - 1;      // −1..1 na caixa da elipse
        var v = ((gy + 0.5) / size) * 2 - 1;
        var ex = u * a, ey = v * b;
        var x = cx + ex * cosP - ey * sinP;
        var y = cy + ex * sinP + ey * cosP;
        out[gy * size + gx] = sampleBilinear(frame, x, y, px)
          ? luma(px[0], px[1], px[2]) : NaN;
      }
    }
    return out;
  }

  return {
    ANGLES: ANGLES,
    RADII: RADII,
    ROTOR_BAND: ROTOR_BAND,
    SCENE_BAND: SCENE_BAND,
    SCENE_ANGLES: SCENE_ANGLES,
    DEG_PER_BIN: DEG_PER_BIN,
    unwrapRotor: unwrapRotor,
    sceneSignature: sceneSignature,
    roiLumaGrid: roiLumaGrid,
    _sampleBilinear: sampleBilinear,
    _luma: luma,
    _chroma: chroma,
    _trimmedMean: trimmedMean
  };
}));
