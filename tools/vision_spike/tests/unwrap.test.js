'use strict';
// SPR-V3 · testes do UNWRAP elíptico e dos perfis angulares.
// Aqui se protege a resposta ao defeito D3: sem unwrap, o método mede TRANSLAÇÃO e não
// responde a pergunta. E se protege a convenção angular — se ela inverter em silêncio,
// o sensor passa a chamar CW de CCW e ninguém percebe até a mesa perder dinheiro.

const test = require('node:test');
const assert = require('node:assert/strict');
const U = require('../lib/unwrap.js');
const Syn = require('../lib/synthetic.js');

const calib = Syn.defaultCalibration();

test('CONVENÇÃO: θ crescente é HORÁRIO na tela (y para baixo)', () => {
  // Uma marca ABAIXO do centro (y maior) tem de aparecer perto de θ=90°, não de 270°.
  // Se esta asserção cair, o sensor passa a chamar CW de CCW — e nada mais no sistema
  // percebe, porque a alternância continua "perfeita" (§10.2.3-1).
  const c = { center: { x: 100, y: 100 }, a: 40, b: 40, phi: 0 };
  const frame = { width: 200, height: 200, data: new Uint8ClampedArray(200 * 200 * 4) };
  for (let y = 118; y <= 142; y++) {
    for (let x = 97; x <= 103; x++) {
      const i = (y * 200 + x) * 4;
      frame.data[i] = 255; frame.data[i + 1] = 255; frame.data[i + 2] = 255; frame.data[i + 3] = 255;
    }
  }
  const r = U.unwrapRotor(frame, c, { angles: 360, radii: 8, band: [0.6, 0.9] });
  assert.equal(r.ok, true);
  let best = 0;
  for (let i = 1; i < r.luma.length; i++) if (r.luma[i] > r.luma[best]) best = i;
  assert.ok(Math.abs(best - 90) < 12, `pico em ${best}° (esperado ~90°)`);
});

test('rotação do padrão vira DESLOCAMENTO do perfil, com o mesmo sinal', () => {
  const f0 = Syn.renderWheelFrame(0, {});
  const f1 = Syn.renderWheelFrame(30, {});
  const p0 = U.unwrapRotor(f0, calib);
  const p1 = U.unwrapRotor(f1, calib);
  const arg = (v) => { let b = 0; for (let i = 1; i < v.length; i++) if (v[i] > v[b]) b = i; return b; };
  const d = (arg(p1.chroma) - arg(p0.chroma)) * p0.degPerBin;
  assert.ok(Math.abs(d - 30) < 2, `deslocamento medido ${d}° (esperado 30°)`);
});

test('canal cromático destaca o zero verde acima de vermelho e preto', () => {
  const withGreen = U.unwrapRotor(Syn.renderWheelFrame(0, {}), calib);
  const withoutGreen = U.unwrapRotor(Syn.renderWheelFrame(0, { noGreen: true }), calib);
  const max = (v) => Math.max.apply(null, Array.from(v));
  assert.ok(max(withGreen.chroma) > 60, 'verde deveria dominar o croma');
  assert.ok(max(withoutGreen.chroma) < 20, 'sem verde o croma não deve ter pico');
});

test('ROI fora do quadro é CONTADA (invalidFrac), não preenchida com preto', () => {
  const small = { width: 60, height: 60, data: new Uint8ClampedArray(60 * 60 * 4) };
  const r = U.unwrapRotor(small, calib);
  assert.equal(r.ok, true);
  assert.ok(r.invalidFrac > 0.5, `invalidFrac=${r.invalidFrac}`);
});

test('assinatura de cena vem do anel ESTÁTICO: girar o rotor não a muda', () => {
  const a = U.sceneSignature(Syn.renderWheelFrame(0, {}), calib);
  const b = U.sceneSignature(Syn.renderWheelFrame(137, {}), calib);
  assert.equal(a.ok, true);
  const E = require('../lib/ellipse.js');
  assert.ok(E.ncc(a.signature, b.signature) > 0.99,
    'NCC do anel estático deveria ser ~1 com o rotor girado — senão o guard invalidaria cena legítima');
});

test('oclusão do ROTOR NÃO derruba a assinatura de cena (é outro guard que pega)', () => {
  const E = require('../lib/ellipse.js');
  const a = U.sceneSignature(Syn.renderWheelFrame(0, {}), calib);
  const b = U.sceneSignature(Syn.renderWheelFrame(0, { occlusion: true }), calib);
  assert.ok(E.ncc(a.signature, b.signature) > 0.9,
    'o NCC olha o anel estático; oclusão do rotor é pega por landmark/alias, não por cena');
});

test('assinatura de cena CAI quando a CENA muda (janela movida / layout trocado)', () => {
  const E = require('../lib/ellipse.js');
  const a = U.sceneSignature(Syn.renderWheelFrame(0, {}), calib);
  const b = U.sceneSignature(Syn.renderWheelFrame(0, { sceneOcclusion: true }), calib);
  assert.ok(E.ncc(a.signature, b.signature) < 0.6,
    'mudança de cena deveria derrubar o NCC abaixo do piso de 0,6');
});

test('roiLumaGrid devolve grade do tamanho pedido e reage a mudança', () => {
  const g0 = U.roiLumaGrid(Syn.renderWheelFrame(0, {}), calib, 12);
  const g1 = U.roiLumaGrid(Syn.renderWheelFrame(45, {}), calib, 12);
  assert.equal(g0.length, 144);
  const M = require('../lib/motion_trigger.js');
  assert.ok(M.meanAbsDiff(g0, g1) > 1, 'girar 45° deveria mover luma na grade');
  assert.equal(M.meanAbsDiff(g0, g0), 0);
});

test('trimmedMean descarta extremos (reflexo especular não sequestra o raio)', () => {
  const buf = [5, 5, 5, 5, 5, 5, 5, 255];
  const m = U._trimmedMean(buf.slice(), 8, 2);
  assert.ok(m < 6, `trimmedMean=${m}`);
});

test('entrada inválida devolve motivo, nunca exceção', () => {
  assert.equal(U.unwrapRotor(null, calib).reason, 'invalid_frame');
  assert.equal(U.unwrapRotor({ width: 4, height: 4, data: new Uint8ClampedArray(4) }, calib).reason, 'invalid_frame');
  assert.equal(U.unwrapRotor(Syn.renderWheelFrame(0, {}), { center: { x: 1, y: 1 }, a: 0, b: 0 }).reason, 'invalid_calibration');
});
