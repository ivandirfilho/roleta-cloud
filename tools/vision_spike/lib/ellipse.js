// SPR-V3 · vision_spike/lib/ellipse.js — ajuste de ELIPSE e assinatura de cena.
//
// Por que elipse (e não círculo/Hough)
// -----------------------------------
// A roda da mesa é filmada em vista OBLÍQUA: o círculo dos bolsos projeta uma ELIPSE.
// Hough é caro e quebra com oclusão/overlay. Aqui o operador clica o CENTRO e >=4 pontos
// da borda e resolvemos a cônica centrada por mínimos quadrados:
//
//     A·u² + B·u·v + C·v² = 1        (u,v = ponto − centro, normalizados)
//
// Honestidade do ajuste (a crítica que derrubou a v1 deste módulo): com 3 pontos a solução
// é EXATA mesmo com cliques ruins — não há resíduo para desconfiar. Por isso:
//   • MIN_POINTS = 4 (recomendado 6-8, um por quadrante);
//   • coordenadas normalizadas antes do ajuste (condicionamento);
//   • mínimos quadrados por QR de Householder (não equações normais, que elevam κ ao quadrado);
//   • Q = [[A, B/2],[B/2, C]] precisa ser POSITIVA DEFINIDA (A>0, C>0, AC−B²/4>0) — o
//     discriminante sozinho aceita cônica degenerada em ruído;
//   • devolvemos resíduo RMS, condição estimada e maior lacuna angular: quem consome
//     DECIDE abstenção; este módulo nunca "salva" uma calibração ruim.
//
// UMD: `require()` no `node --test` e `<script>`/`importScripts` na extensão de diagnóstico.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSEllipse = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Mínimo de pontos de borda. 3 dá solução exata (resíduo 0 sempre) ⇒ inútil como prova.
  var MIN_POINTS = 4;
  // Acima disto o ajuste é numericamente suspeito (cliques quase colineares).
  var MAX_CONDITION = 1e6;
  // Resíduo RMS relativo (adimensional, na escala normalizada) acima do qual o centro
  // clicado provavelmente está errado.
  var MAX_RESIDUAL_RMS = 0.05;
  // Maior lacuna angular tolerada entre pontos consecutivos. >180° significa que todos os
  // cliques caíram em meia elipse: o outro semi-eixo é extrapolação, não medida.
  var MAX_ANGULAR_GAP_DEG = 180;

  function isFiniteNumber(x) { return typeof x === 'number' && isFinite(x); }

  function validPoint(p) {
    return !!p && isFiniteNumber(p.x) && isFiniteNumber(p.y);
  }

  // ---------------------------------------------------------------------------
  // QR de Householder para mínimos quadrados (m×3). Devolve x e os |R_ii| para a
  // estimativa de condição.
  // ---------------------------------------------------------------------------
  function lstsq3(rows, rhs) {
    var m = rows.length;
    var n = 3;
    var A = [];
    var b = rhs.slice();
    var i, j, k;
    for (i = 0; i < m; i++) A.push(rows[i].slice());

    for (k = 0; k < n; k++) {
      var norm = 0;
      for (i = k; i < m; i++) norm += A[i][k] * A[i][k];
      norm = Math.sqrt(norm);
      if (norm === 0) return null;                      // coluna nula ⇒ posto deficiente
      var alpha = A[k][k] > 0 ? -norm : norm;
      var v = new Array(m).fill(0);
      v[k] = A[k][k] - alpha;
      for (i = k + 1; i < m; i++) v[i] = A[i][k];
      var vtv = 0;
      for (i = k; i < m; i++) vtv += v[i] * v[i];
      if (vtv === 0) continue;
      for (j = k; j < n; j++) {                          // aplica H = I − 2vvᵀ/vᵀv em A
        var s = 0;
        for (i = k; i < m; i++) s += v[i] * A[i][j];
        s = (2 * s) / vtv;
        for (i = k; i < m; i++) A[i][j] -= s * v[i];
      }
      var sb = 0;                                        // ...e em b
      for (i = k; i < m; i++) sb += v[i] * b[i];
      sb = (2 * sb) / vtv;
      for (i = k; i < m; i++) b[i] -= sb * v[i];
    }

    var diag = [Math.abs(A[0][0]), Math.abs(A[1][1]), Math.abs(A[2][2])];
    var x = [0, 0, 0];
    for (k = n - 1; k >= 0; k--) {                       // substituição regressiva
      var acc = b[k];
      for (j = k + 1; j < n; j++) acc -= A[k][j] * x[j];
      if (A[k][k] === 0) return null;
      x[k] = acc / A[k][k];
    }
    return { x: x, diag: diag };
  }

  // Autovalores/autovetores da 2×2 simétrica [[a, b],[b, c]] (forma fechada).
  function eig2(a, b, c) {
    var tr = a + c;
    var det = a * c - b * b;
    var disc = Math.sqrt(Math.max(0, (tr * tr) / 4 - det));
    var l1 = tr / 2 + disc;     // maior
    var l2 = tr / 2 - disc;     // menor
    // Ângulo do autovetor de l1 (eixo do MENOR raio, pois raio = 1/sqrt(λ)).
    var theta = 0.5 * Math.atan2(2 * b, a - c);
    return { lMax: l1, lMin: l2, thetaMax: theta };
  }

  function angularGapDeg(center, points) {
    var angs = points.map(function (p) {
      var d = Math.atan2(p.y - center.y, p.x - center.x) * 180 / Math.PI;
      return d < 0 ? d + 360 : d;
    }).sort(function (a, b) { return a - b; });
    var gap = 0;
    for (var i = 0; i < angs.length; i++) {
      var nxt = (i === angs.length - 1) ? angs[0] + 360 : angs[i + 1];
      gap = Math.max(gap, nxt - angs[i]);
    }
    return gap;
  }

  /**
   * Ajusta a elipse com CENTRO FIXO (clicado pelo operador).
   *
   * @param {{x:number,y:number}} center  centro em pixels do VÍDEO (não da tela)
   * @param {Array<{x:number,y:number}>} points  >= MIN_POINTS pontos da borda
   * @returns {{ok:boolean, reason?:string, a:number, b:number, phi:number,
   *             residualRms:number, condition:number, angularGapDeg:number,
   *             warnings:string[]}}
   *   a = semi-eixo MAIOR, b = semi-eixo MENOR, phi = rotação (rad) do semi-eixo maior,
   *   no sistema de imagem (x→direita, y→BAIXO).
   */
  function fitEllipseFixedCenter(center, points, opts) {
    opts = opts || {};
    if (!validPoint(center)) return { ok: false, reason: 'invalid_center', warnings: [] };
    if (!Array.isArray(points)) return { ok: false, reason: 'invalid_points', warnings: [] };
    var pts = points.filter(validPoint);
    var minPoints = opts.minPoints || MIN_POINTS;
    if (pts.length < minPoints) {
      return { ok: false, reason: 'too_few_points', have: pts.length, need: minPoints, warnings: [] };
    }

    // Normalização isotrópica: escala = raio médio. Sem isso os termos u², uv, v² têm
    // ordens de grandeza diferentes e a condição explode.
    var s = 0, i;
    for (i = 0; i < pts.length; i++) {
      s += Math.hypot(pts[i].x - center.x, pts[i].y - center.y);
    }
    s = s / pts.length;
    if (!(s > 0) || !isFinite(s)) return { ok: false, reason: 'degenerate_scale', warnings: [] };

    var rows = [], rhs = [];
    for (i = 0; i < pts.length; i++) {
      var u = (pts[i].x - center.x) / s;
      var v = (pts[i].y - center.y) / s;
      rows.push([u * u, u * v, v * v]);
      rhs.push(1);
    }

    var sol = lstsq3(rows, rhs);
    if (!sol) return { ok: false, reason: 'rank_deficient', warnings: [] };
    var A = sol.x[0], B = sol.x[1], C = sol.x[2];

    // Q positiva definida ⇔ cônica é ELIPSE (e não hipérbole/parábola degenerada).
    var qDet = A * C - (B * B) / 4;
    if (!(A > 0) || !(C > 0) || !(qDet > 0) || !isFinite(qDet)) {
      return { ok: false, reason: 'not_an_ellipse', A: A, B: B, C: C, warnings: [] };
    }

    var e = eig2(A, B / 2, C);
    if (!(e.lMin > 0) || !isFinite(e.lMax)) {
      return { ok: false, reason: 'not_an_ellipse', warnings: [] };
    }
    var aMajor = s / Math.sqrt(e.lMin);
    var bMinor = s / Math.sqrt(e.lMax);
    // Autovetor de lMax é o eixo MENOR ⇒ o maior está a +90°.
    var phi = e.thetaMax + Math.PI / 2;
    while (phi >= Math.PI) phi -= Math.PI;
    while (phi < 0) phi += Math.PI;

    var res = 0;
    for (i = 0; i < rows.length; i++) {
      var f = A * rows[i][0] + B * rows[i][1] + C * rows[i][2] - 1;
      res += f * f;
    }
    var residualRms = Math.sqrt(res / rows.length);

    var dmin = Math.min(sol.diag[0], sol.diag[1], sol.diag[2]);
    var dmax = Math.max(sol.diag[0], sol.diag[1], sol.diag[2]);
    var condition = dmin > 0 ? dmax / dmin : Infinity;
    var gap = angularGapDeg(center, pts);

    var warnings = [];
    if (!(condition <= (opts.maxCondition || MAX_CONDITION))) warnings.push('ill_conditioned');
    if (residualRms > (opts.maxResidualRms || MAX_RESIDUAL_RMS)) warnings.push('residual_high');
    if (gap > (opts.maxAngularGapDeg || MAX_ANGULAR_GAP_DEG)) warnings.push('poor_angular_coverage');
    if (pts.length < 6) warnings.push('few_points');

    return {
      ok: true,
      center: { x: center.x, y: center.y },
      a: aMajor,
      b: bMinor,
      phi: phi,
      axisRatio: bMinor / aMajor,
      residualRms: residualRms,
      condition: condition,
      angularGapDeg: gap,
      pointCount: pts.length,
      warnings: warnings
    };
  }

  /**
   * NCC (normalized cross-correlation) entre dois vetores de mesmo tamanho.
   * Devolve NaN quando qualquer lado é constante (variância zero) — o chamador deve
   * tratar NaN como "não sei", NUNCA como 1.
   */
  function ncc(a, b) {
    if (!a || !b || a.length !== b.length || a.length === 0) return NaN;
    var n = a.length, i, ma = 0, mb = 0;
    for (i = 0; i < n; i++) { ma += a[i]; mb += b[i]; }
    ma /= n; mb /= n;
    var num = 0, da = 0, db = 0;
    for (i = 0; i < n; i++) {
      var xa = a[i] - ma, xb = b[i] - mb;
      num += xa * xb; da += xa * xa; db += xb * xb;
    }
    if (da <= 0 || db <= 0) return NaN;
    return num / Math.sqrt(da * db);
  }

  return {
    MIN_POINTS: MIN_POINTS,
    MAX_CONDITION: MAX_CONDITION,
    MAX_RESIDUAL_RMS: MAX_RESIDUAL_RMS,
    MAX_ANGULAR_GAP_DEG: MAX_ANGULAR_GAP_DEG,
    fitEllipseFixedCenter: fitEllipseFixedCenter,
    ncc: ncc,
    _lstsq3: lstsq3,
    _eig2: eig2,
    _angularGapDeg: angularGapDeg
  };
}));
