'use strict';
// SPR-V3 · testes da transferência de captura (ACK, backpressure, RETOMADA).
//
// O que estes testes protegem: uma coleta de campo de 45 minutos cabe numa captura de
// ~100 MB. A versão anterior despejava tudo de uma vez, sem ack e sem retomada, para
// dentro de um popup que fecha ao primeiro clique fora dele. Perder a transferência é
// perder a coleta — e o operador só descobriria depois de a mesa já ter mudado.

const test = require('node:test');
const assert = require('node:assert/strict');
const X = require('../lib/export_stream.js');

function fakeFrames(n, stride) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const b = new Uint8Array(stride);
    b.fill(i % 251);
    out.push(b);
  }
  return out;
}

/**
 * Liga remetente e destinatário por uma FILA (como um port do Chrome, que é assíncrono).
 * Entregar sincronamente criaria recursão mútua post→ack→post e esconderia o
 * comportamento real do backpressure.
 * `dropAtBatch` corta a conexão ao enviar aquele lote.
 */
function pump(frames, meta, opts) {
  opts = opts || {};
  const assembler = opts.assembler ||
    X.createAssembler({ now: () => (opts.clock ? opts.clock.t : Date.now()) });
  let dead = false;
  let batches = 0;
  const toAssembler = [];
  const toSender = [];

  const sender = X.createSender({
    frames, meta,
    chunkFrames: opts.chunkFrames || 1,
    window: opts.window || 2,
    post: (m) => {
      if (dead) return;
      if (m.type === 'frames') {
        batches++;
        if (opts.dropAtBatch && batches === opts.dropAtBatch) { dead = true; return; }
      }
      toAssembler.push(m);
    }
  });

  sender.start(opts.from || 0);
  let guard = 0;
  while ((toAssembler.length || toSender.length) && guard++ < 100000) {
    while (toAssembler.length) {
      const replies = assembler.handle(toAssembler.shift());
      for (const r of replies) if (!dead) toSender.push(r);
    }
    while (toSender.length) {
      const r = toSender.shift();
      if (!dead) sender.onAck(r.to);
    }
  }
  return { assembler, sender, dead: () => dead, batches: () => batches };
}

test('transferência completa monta os bytes na ordem certa', () => {
  const frames = fakeFrames(12, 8);
  const r = pump(frames, { format: 'vision_spike_capture' });
  const p = r.assembler.progress();
  assert.equal(p.received, 12);
  assert.equal(p.expected, 12);
  assert.equal(p.complete, true);
  const out = r.assembler.assemble();
  assert.equal(out.frameCount, 12);
  assert.equal(out.bytes.length, 12 * 8);
  for (let i = 0; i < 12; i++) assert.equal(out.bytes[i * 8], i % 251);
});

test('BACKPRESSURE: o remetente não passa da janela sem ack', () => {
  const frames = fakeFrames(20, 4);
  let posted = 0;
  const sender = X.createSender({
    frames, meta: {}, chunkFrames: 1, window: 3,
    post: (m) => { if (m.type === 'frames') posted++; }   // ninguém confirma
  });
  sender.start(0);
  assert.equal(posted, 3, 'sem ack, no máximo `window` lotes ficam em voo');
  sender.onAck(0);
  assert.equal(posted, 4);
});

test('RETOMADA: conexão cai no meio e a transferência continua de onde parou', () => {
  const frames = fakeFrames(30, 16);
  const meta = { format: 'vision_spike_capture', frames: [] };

  // 1ª tentativa: morre no 6º lote
  const first = pump(frames, meta, { dropAtBatch: 6 });
  const parcial = first.assembler.progress();
  assert.ok(parcial.received > 0 && parcial.received < 30, `recebidos=${parcial.received}`);
  assert.equal(parcial.complete, false);
  const retomarDe = first.assembler.missingFrom();
  assert.ok(retomarDe !== null);

  // 2ª tentativa: MESMO assembler, novo remetente a partir do que falta
  const second = pump(frames, meta, { assembler: first.assembler, from: retomarDe });
  const final = second.assembler.progress();
  assert.equal(final.complete, true);
  assert.equal(final.received, 30);

  const out = second.assembler.assemble();
  assert.equal(out.frameCount, 30);
  for (let i = 0; i < 30; i++) assert.equal(out.bytes[i * 16], i % 251);
});

test('RETOMADA não duplica nem reordena frames já recebidos', () => {
  const frames = fakeFrames(15, 8);
  const first = pump(frames, {}, { dropAtBatch: 5 });
  const recebidosAntes = first.assembler.progress().received;
  // Retoma do ZERO de propósito: reenviar o que já chegou não pode corromper nada.
  const second = pump(frames, {}, { assembler: first.assembler, from: 0 });
  assert.equal(second.assembler.progress().received, 15);
  assert.ok(recebidosAntes <= 15);
  const out = second.assembler.assemble();
  for (let i = 0; i < 15; i++) assert.equal(out.bytes[i * 8], i % 251);
});

test('captura INCOMPLETA falha alto — não gera um arquivo pela metade', () => {
  const frames = fakeFrames(10, 8);
  const r = pump(frames, {}, { dropAtBatch: 3 });
  assert.throws(() => r.assembler.assemble(), /export incompleto/);
  assert.throws(() => X.createAssembler({}).assemble(), /export sem meta/);
});

test('STALL: o relógio é REARMADO a cada mensagem, inclusive depois do meta', () => {
  // O defeito anterior: o timeout era armado uma vez e, se o `meta` chegasse, nunca mais
  // era rearmado — uma transferência que morria no meio ficava pendurada para sempre,
  // sem erro e sem arquivo.
  const clock = { t: 1000 };
  const a = X.createAssembler({ stallMs: 5000, now: () => clock.t });
  assert.equal(a.isStalled(), false, 'sem mensagem nenhuma ainda não é stall');

  a.handle({ type: 'meta', meta: {}, frameCount: 3 });
  clock.t += 6000;
  assert.equal(a.isStalled(), true, 'parou logo após o meta ⇒ stall');

  a.handle({ type: 'frames', from: 0, to: 0, frames: [{ index: 0, data: new Uint8Array(4) }] });
  assert.equal(a.isStalled(), false, 'mensagem nova rearma o relógio');
  clock.t += 6000;
  assert.equal(a.isStalled(), true);
});

test('transferência completa não é considerada travada', () => {
  const clock = { t: 0 };
  const frames = fakeFrames(4, 4);
  const a = X.createAssembler({ stallMs: 100, now: () => clock.t });
  pump(frames, {}, { assembler: a });
  clock.t += 10000;
  assert.equal(a.isStalled(), false);
});

test('ORÇAMENTO: o teto de memória é consultado ANTES de alocar, não depois', () => {
  // A versão anterior gravava tudo e cortava o excedente — o corte devolvia memória que
  // já tinha sido alocada dentro do renderer de um terceiro, exatamente o custo que o
  // teto existia para não pagar.
  const frameBytes = 330 * 1024;
  const b = X.createByteBudget(1000 * 1024);
  let guardados = 0;
  for (let i = 0; i < 10; i++) {
    if (!b.fits(frameBytes)) break;
    b.add(frameBytes);
    guardados++;
  }
  assert.equal(guardados, 3, '3 frames cabem em 1000 KB; o 4º é recusado ANTES de alocar');
  assert.ok(b.used() <= b.maxBytes, 'o uso nunca passa do teto');
  assert.equal(b.remaining(), 1000 * 1024 - 3 * frameBytes);
});

test('orçamento zero/ausente significa SEM teto (não "nada cabe")', () => {
  const b = X.createByteBudget(0);
  assert.equal(b.fits(1e9), true);
  assert.equal(b.remaining(), Infinity);
});

test('frame com tamanho divergente é recusado na montagem', () => {
  const a = X.createAssembler({});
  a.handle({ type: 'meta', meta: {}, frameCount: 2 });
  a.handle({ type: 'frames', from: 0, to: 1, frames: [
    { index: 0, data: new Uint8Array(8) },
    { index: 1, data: new Uint8Array(9) }
  ] });
  a.handle({ type: 'end', frameCount: 2 });
  assert.throws(() => a.assemble(), /tamanho divergente/);
});
