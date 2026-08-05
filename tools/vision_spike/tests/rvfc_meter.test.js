'use strict';
// SPR-V3 · testes do medidor de COBERTURA (E0b) e do TRIGGER de movimento.
// Timestamps sintéticos: no navegador vêm do rVFC, aqui vêm do teste. É assim que se
// entrega um instrumento testado SEM mesa ao vivo (a medição em campo é V3-B).

const test = require('node:test');
const assert = require('node:assert/strict');
const R = require('../lib/rvfc_meter.js');
const M = require('../lib/motion_trigger.js');

test('conta callbacks/s em wall-clock e avanço do stream em mediaTime (réguas separadas)', () => {
  const m = R.createFrameRateMeter({ bucketMs: 1000 });
  for (let i = 0; i < 30; i++) {
    m.record({ wallMs: i * 100, mediaTime: i * 0.1, presentedFrames: 1000 + i, visibilityState: 'visible' });
  }
  const s = m.summary();
  assert.equal(s.callbacks, 30);
  assert.ok(Math.abs(s.callbacksPerSecond - 10) < 0.5, `fps=${s.callbacksPerSecond}`);
  assert.ok(Math.abs(s.mediaTimeAdvancedS - 2.9) < 1e-6);
  assert.equal(s.presentedFrames, 29);
  assert.equal(s.missedPresentedFrames, 0);
  assert.equal(s.medianIntervalMs, 100);
});

test('separa buckets VISÍVEIS de OCULTOS — é este contraste que o V3-B precisa', () => {
  const m = R.createFrameRateMeter({ bucketMs: 1000 });
  for (let i = 0; i < 10; i++) m.record({ wallMs: i * 100, mediaTime: i * 0.1, visibilityState: 'visible' });
  for (let i = 0; i < 2; i++) m.record({ wallMs: 1000 + i * 500, mediaTime: 1 + i * 0.5, visibilityState: 'hidden' });
  const s = m.summary();
  assert.equal(s.byVisibility.visible.buckets, 1);
  assert.equal(s.byVisibility.hidden.buckets, 1);
  assert.equal(s.byVisibility.visible.fpsMean, 10);
  assert.equal(s.byVisibility.hidden.fpsMean, 2);
});

test('detecta GAP (o player parou de entregar) sem confundir com jitter', () => {
  const m = R.createFrameRateMeter({ bucketMs: 1000, gapFactor: 3 });
  let t = 0;
  for (let i = 0; i < 20; i++) { m.record({ wallMs: t, mediaTime: t / 1000 }); t += 100 + (i % 3) * 5; }
  t += 4000;                                  // 4 s de silêncio
  for (let i = 0; i < 5; i++) { m.record({ wallMs: t, mediaTime: t / 1000 }); t += 100; }
  const s = m.summary();
  assert.equal(s.gapCount, 1);
  assert.ok(s.longestGapMs >= 4000);
});

test('conta frames que o compositor apresentou mas o callback perdeu', () => {
  const m = R.createFrameRateMeter({});
  m.record({ wallMs: 0, presentedFrames: 100 });
  m.record({ wallMs: 100, presentedFrames: 101 });
  m.record({ wallMs: 200, presentedFrames: 108 });   // 6 perdidos
  assert.equal(m.summary().missedPresentedFrames, 6);
});

test('amostra inválida é ignorada, não corrompe a série', () => {
  const m = R.createFrameRateMeter({});
  m.record(null); m.record({}); m.record({ wallMs: NaN });
  assert.equal(m.summary().callbacks, 0);
  m.record({ wallMs: 0 }); m.record({ wallMs: 100 });
  assert.equal(m.summary().callbacks, 2);
  m.reset();
  assert.equal(m.summary().callbacks, 0);
});

test('trigger: respeita ~1 FPS e não dispara no aquecimento', () => {
  const t = M.createMotionTrigger({ threshold: 4, minIntervalMs: 900 });
  const quiet = new Float64Array(16).fill(50);
  assert.equal(t.push(quiet, 0).reason, 'warmup');
  assert.equal(t.push(quiet, 100).reason, 'too_soon');
  assert.equal(t.push(quiet, 1000).reason, 'quiet');
});

test('trigger: dispara com movimento e entra em refratário', () => {
  const t = M.createMotionTrigger({ threshold: 4, minIntervalMs: 900, refractoryMs: 8000 });
  const a = new Float64Array(16).fill(50);
  const b = new Float64Array(16).fill(90);
  t.push(a, 0);
  t.push(a, 1000);
  const fired = t.push(b, 2000);
  assert.equal(fired.fired, true);
  assert.equal(fired.reason, 'motion');
  const again = t.push(a, 3000);
  assert.equal(again.fired, false);
  assert.equal(again.reason, 'refractory');
});

test('trigger: precisa de amostras quietas para rearmar (não metralha por giro)', () => {
  const t = M.createMotionTrigger({ threshold: 4, minIntervalMs: 900, refractoryMs: 1000, quietFramesToArm: 2 });
  const a = new Float64Array(16).fill(50);
  const b = new Float64Array(16).fill(90);
  t.push(a, 0); t.push(a, 1000);
  assert.equal(t.push(b, 2000).fired, true);
  // Voltar de b para a também é MOVIMENTO — não conta como quieta.
  assert.equal(t.push(a, 4000).reason, 'not_armed');
  assert.equal(t.push(a, 5000).reason, 'quiet');       // 1ª quieta de verdade
  const aindaNao = t.push(b, 6000);
  assert.equal(aindaNao.fired, false);
  assert.equal(aindaNao.reason, 'not_armed');          // falta a 2ª quieta
  t.push(b, 7000); t.push(b, 8000);                    // duas quietas em b
  assert.equal(t.push(a, 9000).fired, true);
});

test('meanAbsDiff ignora NaN e recusa tamanhos diferentes', () => {
  assert.equal(M.meanAbsDiff([1, 2, 3], [1, 2, 3]), 0);
  assert.equal(M.meanAbsDiff([1, NaN, 3], [1, 99, 5]), 1);
  assert.ok(Number.isNaN(M.meanAbsDiff([1, 2], [1, 2, 3])));
  assert.ok(Number.isNaN(M.meanAbsDiff(null, [1])));
});

test('`intervals` é um RING — o soak de 2h não vira sort quadrático', () => {
  const m = R.createFrameRateMeter({ bucketMs: 1000, maxIntervals: 50 });
  for (let i = 0; i < 500; i++) m.record({ wallMs: i * 33 });
  const s = m.summary();
  assert.equal(s.callbacks, 500);
  assert.equal(s.medianIntervalMs, 33);   // ainda correto com o ring
});

test('decimador: intervalo recomendado sai da ARITMÉTICA do guard, não de um palpite', () => {
  const D = require('../lib/direction_core.js');
  // minAliasSafetyDeg / (rev_min × 360) / stride = 19,4595 / 72 / 3
  assert.ok(Math.abs(D.recommendedFrameIntervalS() - 0.09009) < 1e-4);
  assert.ok(Math.abs(D.recommendedFrameIntervalS({ pairStride: 1 }) - 0.27027) < 1e-4);
});

test('decimador reduz 30 fps nativos à cadência segura (~11 fps efetivos)', () => {
  const D = require('../lib/direction_core.js');
  const dec = R.createDecimator({ targetIntervalS: D.recommendedFrameIntervalS() });
  const aceitos = [];
  for (let i = 0; i < 60; i++) {
    const t = i / 30;
    if (dec.accept(t)) aceitos.push(t);
  }
  assert.equal(dec.stats().seen, 60);
  assert.ok(aceitos.length >= 18 && aceitos.length <= 21, `aceitos=${aceitos.length}`);
  for (let i = 1; i < aceitos.length; i++) {
    assert.ok(aceitos[i] - aceitos[i - 1] >= dec.minGapS - 1e-9);
  }
});

test('decimador NÃO descarta um feed que já roda na cadência alvo', () => {
  const D = require('../lib/direction_core.js');
  const dec = R.createDecimator({ targetIntervalS: D.recommendedFrameIntervalS() });
  let n = 0;
  for (let i = 0; i < 30; i++) if (dec.accept(i / 10)) n++;   // 10 fps
  assert.equal(n, 30);
});

test('decimador ignora timestamps inválidos em vez de travar a cadência', () => {
  const dec = R.createDecimator({ targetIntervalS: 0.1 });
  assert.equal(dec.accept(NaN), false);
  assert.equal(dec.accept(undefined), false);
  assert.equal(dec.accept(0), true);
  assert.equal(dec.accept(0.01), false);
  assert.equal(dec.accept(0.2), true);
});
