'use strict';
// SPR-V3 · testes do ESTIMADOR (o coração do spike).
//
// O produto deste sprint é a honestidade do estimador. Estes testes existem para provar
// que ele ABSTÉM quando deve — não para provar que ele acerta. Acertar em cena sintética
// não prova nada sobre a mesa (ver lib/synthetic.js: evidence_class 'synthetic').

const test = require('node:test');
const assert = require('node:assert/strict');
const D = require('../lib/direction_core.js');
const P = require('../lib/pipeline.js');
const Syn = require('../lib/synthetic.js');
const U = require('../lib/unwrap.js');

function profilesFor(opts) {
  const seq = Syn.makeSequence(Object.assign({ count: 6, fps: 10, revPerS: 0.35 }, opts));
  const built = P.buildProfiles(seq.frames, seq.calibration);
  return { profiles: built.profiles, calib: seq.calibration, seq };
}

test('circularXCorr acha o deslocamento exato e o sinal certo', () => {
  const n = 360;
  const a = new Float64Array(n);
  for (let i = 0; i < n; i++) a[i] = Math.sin(2 * Math.PI * i / n) + 0.4 * Math.sin(6 * Math.PI * i / n);
  const shift = 25;
  const b = new Float64Array(n);
  for (let i = 0; i < n; i++) b[i] = a[(i - shift + n) % n];   // b = a deslocado de +25
  const corr = D.circularXCorr(a, b, 120);
  let best = 0;
  for (let i = 1; i < corr.length; i++) if (corr[i] > corr[best]) best = i;
  assert.equal(best - 120, shift);
  assert.ok(corr[best] > 0.99);
});

test('circularXCorr de um sinal com ele mesmo tem pico em lag 0', () => {
  const n = 180;
  const a = new Float64Array(n);
  for (let i = 0; i < n; i++) a[i] = Math.cos(4 * Math.PI * i / n);
  const corr = D.circularXCorr(a, a, 60);
  let best = 0;
  for (let i = 1; i < corr.length; i++) if (corr[i] > corr[best]) best = i;
  assert.equal(best - 60, 0);
});

test('CW sintético limpo é emitido como cw, com a magnitude certa', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  const r = D.analyzeWindow(profiles, calib);
  assert.deepEqual(r.guards, []);
  assert.equal(r.direction, 'cw');
  assert.equal(r.emitted, true);
  assert.ok(r.confidence >= D.DEFAULTS.emitFloor);
  // 0,35 rev/s = 126°/s
  assert.ok(Math.abs(r.degreesPerSecond - 126) < 6, `deg/s=${r.degreesPerSecond}`);
});

test('CCW sintético limpo é emitido como ccw', () => {
  const { profiles, calib } = profilesFor({ direction: 'ccw' });
  const r = D.analyzeWindow(profiles, calib);
  assert.deepEqual(r.guards, []);
  assert.equal(r.direction, 'ccw');
  assert.ok(r.degreesPerSecond < 0);
});

test('`mirrored` inverte o RÓTULO sem mexer na medida', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  const normal = D.analyzeWindow(profiles, calib);
  const mirrored = D.analyzeWindow(profiles, Object.assign({}, calib, { mirrored: true }));
  assert.equal(normal.direction, 'cw');
  assert.equal(mirrored.direction, 'ccw');
  assert.equal(normal.degreesPerSecond, mirrored.degreesPerSecond);
});

test('confidence é declarada HEURÍSTICA, não probabilidade', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  assert.equal(D.analyzeWindow(profiles, calib).confidenceKind, 'heuristic_quality_score');
});

test('SEM o zero verde o estimador ABSTÉM (é a defesa contra D4/D5)', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw', noGreen: true });
  const r = D.analyzeWindow(profiles, calib);
  assert.equal(r.direction, null);
  assert.equal(r.emitted, false);
  assert.ok(r.guards.includes('zero_landmark_missing'), JSON.stringify(r.guards));
  assert.ok(r.confidence <= D.DEFAULTS.guardedConfidenceCap);
});

test('sem verde a MARGEM DE ALIAS também cai (pente de 37 bolsos empata os picos)', () => {
  const { profiles } = profilesFor({ direction: 'cw', noGreen: true });
  const r = D.analyzeWindow(profiles, {});
  assert.ok(r.guards.includes('alias_margin_low'), JSON.stringify(r.guards));
  assert.ok(r.aliasMargin < D.DEFAULTS.aliasMarginMin);
});

test('cena PARADA nunca vira veredito', () => {
  const { profiles, calib } = profilesFor({ direction: 'static' });
  const r = D.analyzeWindow(profiles, calib);
  assert.equal(r.direction, null);
  assert.ok(r.guards.includes('low_energy'), JSON.stringify(r.guards));
  assert.ok(r.guards.includes('sign_inconsistent'));
});

test('luma fora de faixa (cena escura/estourada) abstém', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw', lowLuma: true });
  const r = D.analyzeWindow(profiles, calib);
  assert.equal(r.direction, null);
  assert.ok(r.guards.includes('luma_out_of_range'));
});

test('NCC de cena baixo abstém — e NCC NaN ("não sei") também', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  const low = profiles.map((p, i) => Object.assign({}, p, { ncc: i === 2 ? 0.31 : 0.99 }));
  assert.ok(D.analyzeWindow(low, calib).guards.includes('scene_ncc_low'));
  const nan = profiles.map((p) => Object.assign({}, p, { ncc: NaN }));
  const r = D.analyzeWindow(nan, calib);
  assert.ok(r.guards.includes('scene_ncc_low'));
  assert.equal(r.direction, null);
});

test('ROI saindo do quadro abstém', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  const bad = profiles.map((p, i) => Object.assign({}, p, { invalidFrac: i === 0 ? 0.4 : 0 }));
  assert.ok(D.analyzeWindow(bad, calib).guards.includes('roi_out_of_bounds'));
});

test('stride pequeno demais para o alias de ±1 bolso dispara `stride_too_small`', () => {
  // 10 fps com stride 1 ⇒ Δt=0,1 s ⇒ o rotor lento anda 7,2°, e o alias vizinho cai em
  // −2,5°: SINAL TROCADO. O guard existe para isso não passar despercebido.
  const { profiles, calib } = profilesFor({ direction: 'cw', count: 6 });
  const r = D.analyzeWindow(profiles, calib, { pairStride: 1 });
  assert.ok(r.guards.includes('stride_too_small'), JSON.stringify(r.guards));
  assert.equal(r.direction, null);
});

test('velocidade fora do prior físico do rotor abstém', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw', revPerS: 1.4 });
  const r = D.analyzeWindow(profiles, calib);
  assert.ok(r.guards.includes('magnitude_out_of_prior'), JSON.stringify(r.guards));
  assert.equal(r.direction, null);
});

test('janela curta demais: `insufficient_frames`, sem exceção', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw', count: 3 });
  const r = D.analyzeWindow(profiles, calib);
  assert.equal(r.direction, null);
  assert.ok(r.guards.includes('insufficient_frames'));
  assert.equal(D.analyzeWindow(null, calib).guards[0], 'insufficient_frames');
  assert.equal(D.analyzeWindow([], calib).direction, null);
});

test('menos de 3 pares dispara `too_few_pairs` (consistência que não existe não conta)', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw', count: 8 });
  const r = D.analyzeWindow(profiles.slice(0, 7), calib, { pairStride: 5, minFrames: 6 });
  assert.ok(r.guards.includes('too_few_pairs'), JSON.stringify(r.guards));
});

test('sem mediaTime o Δt cai para wall-clock — e isso é REGISTRADO como guard', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  const noMedia = profiles.map(p => Object.assign({}, p, { mediaTimeS: undefined, tMs: p.index * 100 }));
  const r = D.analyzeWindow(noMedia, calib);
  assert.equal(r.evidence.dtSource, 'wallClock');
  assert.ok(r.guards.includes('dt_from_wall_clock'));
  assert.equal(r.direction, null);
});

test('INVARIANTE: qualquer guard ⇒ confidence ≤0,5 E direction null', () => {
  const casos = [
    { direction: 'cw', noGreen: true },
    { direction: 'cw', lowLuma: true },
    { direction: 'static' },
    { direction: 'cw', revPerS: 1.4 },
    { direction: 'cw', occlusion: true }
  ];
  for (const c of casos) {
    const { profiles, calib } = profilesFor(c);
    const r = D.analyzeWindow(profiles, calib);
    if (r.guards.length > 0) {
      assert.equal(r.direction, null, JSON.stringify(c));
      assert.equal(r.emitted, false, JSON.stringify(c));
      assert.ok(r.confidence <= D.DEFAULTS.guardedConfidenceCap, JSON.stringify(c));
    }
  }
});

test('findZeroLandmark: margem de unicidade alta COM verde, ~0 SEM verde', () => {
  const calib = Syn.defaultCalibration();
  const comVerde = U.unwrapRotor(Syn.renderWheelFrame(0, {}), calib);
  const semVerde = U.unwrapRotor(Syn.renderWheelFrame(0, { noGreen: true }), calib);
  const a = D.findZeroLandmark(comVerde.chroma, 0.5, D.DEFAULTS);
  const b = D.findZeroLandmark(semVerde.chroma, 0.5, D.DEFAULTS);
  assert.ok(a.present, `margin=${a.margin}`);
  assert.ok(a.margin > 1.0, `margin=${a.margin}`);
  assert.ok(!b.present, `margin=${b.margin}`);
  assert.ok(b.margin < D.DEFAULTS.landmarkMinMargin);
});

test('a prominência por MAD sozinha NÃO discriminaria — por isso não é o gate', () => {
  // Regressão documentada: com fundo bimodal vermelho/preto o MAD é enorme e o verde
  // legítimo marca z≈3,9. Se alguém trocar a margem de unicidade por z, isto quebra.
  const calib = Syn.defaultCalibration();
  const comVerde = U.unwrapRotor(Syn.renderWheelFrame(0, {}), calib);
  const l = D.findZeroLandmark(comVerde.chroma, 0.5, D.DEFAULTS);
  assert.ok(l.z < 6, `z=${l.z} — se z fosse o gate, um limiar de 4 seria arbitrário`);
});

test('landmark que discorda da correlação dispara `zero_landmark_disagrees`', () => {
  // Move APENAS o setor verde, deixando o pente de 37 bolsos (que domina a correlação)
  // andando no sentido certo. É o caso que a correlação sozinha jamais pegaria: um reflexo
  // verde da mesa, ou um espelhamento parcial da ROI, faria exatamente isto.
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  const n = profiles[0].chroma.length;
  const half = 12;                                  // ~6° de cada lado do bump
  const perFrameBins = Math.round(12.6 / 0.5);      // 12,6°/frame a 10 fps e 0,35 rev/s

  const sabotado = profiles.map((p, i) => {
    const src = p.chroma;
    let from = 0;
    for (let k = 1; k < n; k++) if (src[k] > src[from]) from = k;
    const to = ((from - 2 * i * perFrameBins) % n + n) % n;   // vai para o lado errado
    const sorted = Array.from(src).sort((a, b) => a - b);
    const bg = sorted[Math.floor(sorted.length / 2)];
    const out = Float64Array.from(src);
    const bump = [];
    for (let d = -half; d <= half; d++) bump.push(src[(from + d + n) % n]);
    for (let d = -half; d <= half; d++) out[(from + d + n) % n] = bg;
    for (let d = -half; d <= half; d++) out[(to + d + n) % n] = bump[d + half];
    return Object.assign({}, p, { chroma: out });
  });

  const r = D.analyzeWindow(sabotado, calib);
  assert.ok(r.guards.includes('zero_landmark_disagrees'), JSON.stringify(r.guards));
  assert.equal(r.direction, null);
  assert.equal(r.emitted, false);
});

test('evidência traz os números que o RESULTADO.md precisa citar', () => {
  const { profiles, calib } = profilesFor({ direction: 'cw' });
  const r = D.analyzeWindow(profiles, calib);
  assert.equal(r.evidence.pairCount, 3);
  assert.equal(r.evidence.dtSource, 'mediaTime');
  assert.equal(r.evidence.lagsDeg.length, 3);
  assert.equal(r.evidence.landmarkMargin.length, 6);
  assert.ok(Math.abs(r.evidence.pockedPeriodDeg - 360 / 37) < 1e-9);
});
