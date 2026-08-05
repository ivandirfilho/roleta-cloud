'use strict';
// SPR-V3 · testes do ajuste de ELIPSE.
// O que estes testes protegem: a calibração é a única coisa entre o algoritmo e o lixo.
// Uma elipse "ajustada" com resíduo silencioso vira um sensor que erra sempre igual — o
// pior modo de falha possível (§10.2.3-1: ROI espelhada erra CONSISTENTEMENTE e a
// alternância no banco fica perfeita, então DIR22 não vê nada).

const test = require('node:test');
const assert = require('node:assert/strict');
const E = require('../lib/ellipse.js');

function pointsOnEllipse(center, a, b, phi, n, jitter, rnd) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const t = (i / n) * 2 * Math.PI;
    const ex = a * Math.cos(t), ey = b * Math.sin(t);
    const j = jitter ? (rnd() - 0.5) * 2 * jitter : 0;
    pts.push({
      x: center.x + ex * Math.cos(phi) - ey * Math.sin(phi) + j,
      y: center.y + ex * Math.sin(phi) + ey * Math.cos(phi) + j
    });
  }
  return pts;
}

test('recupera semi-eixos e rotação de uma elipse exata', () => {
  const c = { x: 160, y: 130 };
  const r = E.fitEllipseFixedCenter(c, pointsOnEllipse(c, 90, 60, 0.3, 8));
  assert.equal(r.ok, true);
  assert.ok(Math.abs(r.a - 90) < 0.5, `a=${r.a}`);
  assert.ok(Math.abs(r.b - 60) < 0.5, `b=${r.b}`);
  assert.ok(Math.abs(r.phi - 0.3) < 0.01, `phi=${r.phi}`);
  assert.ok(r.residualRms < 1e-6);
  assert.deepEqual(r.warnings.filter(w => w !== 'few_points'), []);
});

test('CÍRCULO é caso particular: a≈b e phi indiferente', () => {
  const c = { x: 100, y: 100 };
  const r = E.fitEllipseFixedCenter(c, pointsOnEllipse(c, 50, 50, 0, 6));
  assert.equal(r.ok, true);
  assert.ok(Math.abs(r.a - 50) < 0.2 && Math.abs(r.b - 50) < 0.2);
  assert.ok(Math.abs(r.axisRatio - 1) < 0.01);
});

test('3 pontos são RECUSADOS — a solução exata esconde cliques ruins', () => {
  const c = { x: 100, y: 100 };
  const r = E.fitEllipseFixedCenter(c, pointsOnEllipse(c, 50, 30, 0, 3));
  assert.equal(r.ok, false);
  assert.equal(r.reason, 'too_few_points');
  assert.equal(r.need, 4);
});

test('4 pontos passam, mas com aviso `few_points` (redundância mínima)', () => {
  const c = { x: 100, y: 100 };
  const r = E.fitEllipseFixedCenter(c, pointsOnEllipse(c, 50, 30, 0.1, 4));
  assert.equal(r.ok, true);
  assert.ok(r.warnings.includes('few_points'));
});

test('CENTRO errado eleva o resíduo e dispara `residual_high`', () => {
  const c = { x: 160, y: 130 };
  const pts = pointsOnEllipse(c, 90, 60, 0.2, 8);
  const r = E.fitEllipseFixedCenter({ x: c.x + 18, y: c.y - 14 }, pts);
  // Ou o ajuste nem fecha elipse, ou fecha com resíduo alto: os dois são recusa honesta.
  if (r.ok) assert.ok(r.warnings.includes('residual_high'), JSON.stringify(r.warnings));
  else assert.equal(r.reason, 'not_an_ellipse');
});

test('cliques todos no mesmo semicírculo disparam `poor_angular_coverage`', () => {
  const c = { x: 160, y: 130 };
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const t = (i / 6) * Math.PI * 0.7;          // só ~126° de cobertura
    pts.push({ x: c.x + 90 * Math.cos(t), y: c.y + 60 * Math.sin(t) });
  }
  const r = E.fitEllipseFixedCenter(c, pts);
  if (r.ok) assert.ok(r.warnings.includes('poor_angular_coverage'), JSON.stringify(r.warnings));
  else assert.ok(['not_an_ellipse', 'rank_deficient'].includes(r.reason));
});

test('pontos colineares NÃO viram elipse', () => {
  const c = { x: 100, y: 100 };
  const pts = [{ x: 140, y: 100 }, { x: 130, y: 100 }, { x: 120, y: 100 }, { x: 110, y: 100 }, { x: 60, y: 100 }];
  const r = E.fitEllipseFixedCenter(c, pts);
  assert.equal(r.ok, false);
  assert.ok(['not_an_ellipse', 'rank_deficient'].includes(r.reason), r.reason);
});

test('ruído de clique (±2 px) mantém o ajuste dentro de 3% com 8 pontos', () => {
  let seed = 42;
  const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
  const c = { x: 160, y: 130 };
  const r = E.fitEllipseFixedCenter(c, pointsOnEllipse(c, 90, 60, 0.25, 8, 2, rnd));
  assert.equal(r.ok, true);
  assert.ok(Math.abs(r.a - 90) / 90 < 0.03, `a=${r.a}`);
  assert.ok(Math.abs(r.b - 60) / 60 < 0.03, `b=${r.b}`);
});

test('entradas inválidas devolvem motivo, nunca exceção', () => {
  assert.equal(E.fitEllipseFixedCenter(null, []).reason, 'invalid_center');
  assert.equal(E.fitEllipseFixedCenter({ x: 0, y: 0 }, null).reason, 'invalid_points');
  assert.equal(E.fitEllipseFixedCenter({ x: 0, y: NaN }, []).reason, 'invalid_center');
  const degenerate = E.fitEllipseFixedCenter({ x: 5, y: 5 },
    [{ x: 5, y: 5 }, { x: 5, y: 5 }, { x: 5, y: 5 }, { x: 5, y: 5 }]);
  assert.equal(degenerate.ok, false);
  assert.equal(degenerate.reason, 'degenerate_scale');
});

test('ncc: identidade=1, oposto=-1, constante=NaN ("não sei", nunca 1)', () => {
  const a = [1, 2, 3, 4, 5, 4, 3, 2];
  assert.ok(Math.abs(E.ncc(a, a) - 1) < 1e-12);
  assert.ok(Math.abs(E.ncc(a, a.map(v => -v)) + 1) < 1e-12);
  assert.ok(Number.isNaN(E.ncc(a, [1, 1, 1, 1, 1, 1, 1, 1])));
  assert.ok(Number.isNaN(E.ncc(a, [1, 2, 3])));
  assert.ok(Number.isNaN(E.ncc(null, a)));
});

test('ncc é invariante a ganho e offset (mudança de brilho não invalida cena)', () => {
  const a = [10, 20, 35, 12, 60, 15, 22, 41];
  const b = a.map(v => v * 1.7 + 30);
  assert.ok(Math.abs(E.ncc(a, b) - 1) < 1e-12);
});
