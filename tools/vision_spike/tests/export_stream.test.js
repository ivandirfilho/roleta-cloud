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
    // Uint8ClampedArray é o tipo REAL que vem de `getImageData().data`.
    const b = new Uint8ClampedArray(stride);
    b.fill(i % 251);
    out.push(b);
  }
  return out;
}

/**
 * Liga remetente e destinatário por uma FILA **atravessando JSON**, que é o que o
 * `chrome.runtime.Port` faz de verdade. Entregar o objeto em memória (como os testes da
 * rodada anterior faziam) esconde a regressão mais cara possível: uma typed array crua
 * chega do outro lado do port como `{"0":12,…}`, sem `.length`.
 * `dropAtBatch` corta a conexão ao enviar aquele lote.
 */
function pump(frames, meta, opts) {
  opts = opts || {};
  const assembler = opts.assembler ||
    X.createAssembler({ now: () => (opts.clock ? opts.clock.t : Date.now()) });
  const wire = opts.wire || ((m) => JSON.parse(JSON.stringify(m)));
  let dead = false;
  let batches = 0;
  let protocolError = null;
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
        if (opts.corruptBatch === batches && opts.corrupt) m = opts.corrupt(m);
      }
      toAssembler.push(wire(m));     // ← a travessia do JSON
    }
  });

  sender.start(opts.from || 0);
  let guard = 0;
  while ((toAssembler.length || toSender.length) && guard++ < 100000) {
    while (toAssembler.length) {
      let replies = [];
      try {
        replies = assembler.handle(toAssembler.shift());
      } catch (e) {
        protocolError = e;
        dead = true;
        toAssembler.length = 0;
        break;
      }
      for (const r of replies) if (!dead) toSender.push(r);
    }
    while (toSender.length) {
      const r = toSender.shift();
      if (!dead) sender.onAck(r.to);
    }
  }
  return { assembler, sender, dead: () => dead, batches: () => batches, protocolError: () => protocolError };
}

test('TRANSPORT BOUNDARY: bytes sobrevivem intactos à serialização JSON do port', () => {
  // Cada byte de 0 a 255, mais padrões que quebram base64 mal implementado.
  const frames = [];
  const a = new Uint8ClampedArray(256);
  for (let i = 0; i < 256; i++) a[i] = i;
  frames.push(a);
  frames.push(new Uint8ClampedArray([0, 0, 0]));
  frames.push(new Uint8ClampedArray([255, 255, 255]));
  frames.push(new Uint8ClampedArray(256).fill(7));
  // todos com o mesmo stride, senão a montagem recusa (e é o que ela deve fazer)
  const stride = 256;
  const norm = frames.map((f) => { const b = new Uint8ClampedArray(stride); b.set(f.subarray(0, stride)); return b; });

  const r = pump(norm, { format: 'vision_spike_capture' });
  assert.equal(r.protocolError(), null);
  assert.equal(r.assembler.progress().complete, true);
  const out = r.assembler.assemble();
  assert.equal(out.stride, stride);
  assert.equal(out.bytes.length, stride * norm.length);
  for (let f = 0; f < norm.length; f++) {
    for (let i = 0; i < stride; i++) {
      assert.equal(out.bytes[f * stride + i], norm[f][i], `frame ${f} byte ${i}`);
    }
  }
});

test('TRANSPORT BOUNDARY: base64 ida e volta é exato para 0..255 e para restos 1 e 2', () => {
  for (const n of [0, 1, 2, 3, 4, 5, 255, 256, 1000]) {
    const src = new Uint8Array(n);
    for (let i = 0; i < n; i++) src[i] = (i * 37 + 11) & 0xFF;
    const back = X.fromBase64(X.toBase64(src));
    assert.equal(back.length, n, `n=${n}`);
    for (let i = 0; i < n; i++) assert.equal(back[i], src[i], `n=${n} i=${i}`);
  }
});

test('TRANSPORT BOUNDARY · RECUPERAÇÃO: lote corrompido → retransmissão válida limpa a recusa', () => {
  // O beco que isto conserta: `rejected` era append-only. A retomada entregava o frame
  // certo, mas a recusa antiga continuava lá — `complete` nunca virava `true` e
  // `assemble()` recusava PARA SEMPRE, enquanto a interface seguia oferecendo "Retomar".
  // O operador clicaria num botão que nunca resolve.
  const frames = fakeFrames(12, 32);
  const meta = { format: 'vision_spike_capture', frames: [] };

  // 1ª tentativa: o 4º lote chega com o base64 corrompido (índice preservado).
  const first = pump(frames, meta, {
    corruptBatch: 4,
    corrupt: (m) => ({
      ...m,
      frames: m.frames.map((f) => ({ ...f, b64: f.b64.slice(0, -4) + '@@@@' }))
    })
  });
  const p1 = first.assembler.progress();
  assert.equal(p1.rejected, 1, JSON.stringify(p1.rejectedDetail));
  assert.equal(p1.recoverable, true, 'recusa com índice conhecido é recuperável');
  assert.equal(p1.complete, false);
  const retomarDe = first.assembler.missingFrom();
  assert.equal(retomarDe, 3, 'a retomada parte do frame recusado');

  // 2ª tentativa: mesmo assembler, dados válidos a partir do índice recusado.
  const second = pump(frames, meta, { assembler: first.assembler, from: retomarDe });
  const p2 = second.assembler.progress();
  assert.equal(p2.rejected, 0, 'a retransmissão válida APAGA a recusa');
  assert.equal(p2.complete, true);
  assert.equal(p2.missingFrom, null);

  const out = second.assembler.assemble();
  assert.equal(out.frameCount, 12);
  assert.equal(out.bytes.length, 12 * 32);
  for (let f = 0; f < 12; f++) {
    for (let i = 0; i < 32; i++) {
      assert.equal(out.bytes[f * 32 + i], frames[f][i], `frame ${f} byte ${i}`);
    }
  }
});

test('recusa SEM índice atribuível não é recuperável — a UI tem de mandar recomeçar', () => {
  const a = X.createAssembler({});
  a.handle({ type: 'meta', wire: X.WIRE, meta: {}, frameCount: 2 });
  // Lote malformado: sem `index`, não há o que reenviar.
  a.handle({ type: 'frames', wire: X.WIRE, from: 0, to: 0, frames: [{ b64: 'AAAA', length: 3 }] });
  const p = a.progress();
  assert.equal(p.rejected, 1);
  assert.equal(p.recoverable, false, 'sem índice, retomar não resolve');
  assert.equal(p.rejectedDetail[0].index, null);
  assert.throws(() => a.assemble(), /recusado/);
});

test('a mesma recusa repetida não infla o contador (e some de uma vez)', () => {
  const a = X.createAssembler({});
  a.handle({ type: 'meta', wire: X.WIRE, meta: {}, frameCount: 1 });
  const ruim = { type: 'frames', wire: X.WIRE, from: 0, to: 0, frames: [{ index: 0, b64: '@@@@', length: 3 }] };
  a.handle(ruim);
  a.handle(ruim);
  a.handle(ruim);
  assert.equal(a.progress().rejected, 1, 'recusa e por INDICE, nao uma lista que so cresce');

  const bom = new Uint8Array([1, 2, 3]);
  a.handle({
    type: 'frames', wire: X.WIRE, from: 0, to: 0,
    frames: [{ index: 0, b64: X.toBase64(bom), length: 3 }]
  });
  a.handle({ type: 'end', frameCount: 1 });
  assert.equal(a.progress().rejected, 0);
  assert.equal(a.progress().complete, true);
  assert.deepEqual(Array.from(a.assemble().bytes), [1, 2, 3]);
});

test('base64 recusa entrada inválida em vez de devolver lixo', () => {
  assert.throws(() => X.fromBase64('abc$'), /base64 invalido/);
  assert.throws(() => X.fromBase64(null), /nao e string/);
  assert.throws(() => X.fromBase64('ab c'), /base64 invalido/);   // espaço
  assert.throws(() => X.fromBase64('ab\u0000c'), /base64 invalido/);
});

test('base64 recusa caractere UNICODE fora da tabela (charCode > 255)', () => {
  // O defeito: `B64_LOOKUP` tem 256 posições; `charCodeAt` de um caractere não-Latin-1
  // devolve >255, o índice fora do TypedArray devolve `undefined`, e `undefined < 0` é
  // `false`. A checagem ingênua deixava `'\u0100'` passar como se fosse válido — ele
  // virava 0 na conta de bits e o frame decodificava LIXO em silêncio.
  for (const ch of ['\u0100', '\u00FF', '\u20AC', '\uFFFD', '😀']) {
    assert.throws(() => X.fromBase64('AA' + ch + 'A'), /base64 invalido/,
      `deveria recusar ${JSON.stringify(ch)}`);
  }
  // E não é só lançar: o caso concreto do relatório NÃO pode decodificar nada.
  assert.throws(() => X.fromBase64('AA\u0100A'), /charCode 256/);
});

test('um frame com Unicode no b64 é RECUSADO, não decodificado como lixo', () => {
  const a = X.createAssembler({});
  a.handle({ type: 'meta', wire: X.WIRE, meta: {}, frameCount: 1 });
  const acks = a.handle({
    type: 'frames', wire: X.WIRE, from: 0, to: 0,
    frames: [{ index: 0, b64: 'AA\u0100A', length: 3 }]
  });
  assert.deepEqual(acks, [], 'lixo nao pode ser confirmado');
  assert.equal(a.progress().rejected, 1);
  assert.equal(a.progress().recoverable, true);
  a.handle({ type: 'end', frameCount: 1 });
  assert.equal(a.progress().complete, false);
});

test('REGRESSÃO: typed array crua (wire antigo) vira objeto sem length no JSON e FALHA ALTO', () => {
  // Esta é a regressão exata: `{type:'frames', frames:[{index, data: <Uint8ClampedArray>}]}`
  // atravessando JSON vira `data: {"0":12,…}` — objeto SEM `.length`. Antes disso passar
  // batido, `assemble()` calculava stride `undefined`, criava `Uint8Array(NaN)` (= 0) e
  // devolvia 0 byte SEM lançar: o operador salvava um `frames.bin` vazio com a interface
  // dizendo "300 frames, completo".
  const bruto = new Uint8ClampedArray([1, 2, 3, 4]);
  const msgAntiga = JSON.parse(JSON.stringify({
    type: 'frames', from: 0, to: 0, frames: [{ index: 0, data: bruto }]
  }));
  assert.equal(typeof msgAntiga.frames[0].data, 'object');
  assert.equal(msgAntiga.frames[0].data.length, undefined, 'o JSON realmente come o .length');

  const a = X.createAssembler({});
  a.handle({ type: 'meta', meta: {}, frameCount: 1 });
  const acks = a.handle(msgAntiga);
  assert.deepEqual(acks, [], 'frame invalido NAO pode ser confirmado');
  const p = a.progress();
  assert.equal(p.received, 0);
  assert.equal(p.rejected, 1);
  assert.match(p.rejectedDetail[0].reason, /b64/);

  a.handle({ type: 'end', frameCount: 1 });
  assert.equal(a.progress().complete, false, 'nunca pode se declarar completo');
  assert.throws(() => a.assemble(), /recusado/);
});

test('REGRESSÃO: montagem NUNCA produz arquivo de 0 byte se dizendo completo', () => {
  // 1) sem frame nenhum
  const vazio = X.createAssembler({});
  vazio.handle({ type: 'meta', meta: {}, frameCount: 0 });
  vazio.handle({ type: 'end', frameCount: 0 });
  assert.equal(vazio.progress().complete, false);
  assert.throws(() => vazio.assemble(), /0 frames/);

  // 2) frame declarado com length 0
  const zero = X.createAssembler({});
  zero.handle({ type: 'meta', meta: {}, frameCount: 1 });
  const acks = zero.handle({
    type: 'frames', wire: X.WIRE, from: 0, to: 0,
    frames: [{ index: 0, b64: '', length: 0 }]
  });
  assert.deepEqual(acks, []);
  zero.handle({ type: 'end', frameCount: 1 });
  assert.equal(zero.progress().complete, false);
  assert.throws(() => zero.assemble(), /recusado|incompleto/);
});

test('length declarado que não bate com o decodificado é RECUSADO', () => {
  const a = X.createAssembler({});
  a.handle({ type: 'meta', meta: {}, frameCount: 1 });
  const b64 = X.toBase64(new Uint8Array([1, 2, 3, 4]));
  const acks = a.handle({ type: 'frames', wire: X.WIRE, from: 0, to: 0, frames: [{ index: 0, b64, length: 99 }] });
  assert.deepEqual(acks, []);
  assert.match(a.progress().rejectedDetail[0].reason, /declarado 99/);
});

test('wire desconhecido falha alto (não tenta adivinhar o formato)', () => {
  const a = X.createAssembler({});
  assert.throws(() => a.handle({ type: 'meta', wire: 'protobuf', meta: {}, frameCount: 1 }),
    /wire desconhecido/);
});

test('o remetente recusa frame que não é typed array', () => {
  assert.throws(() => X.createSender({
    frames: [[1, 2, 3]], meta: {}, post: () => { }
  }).start(0), /nao e Uint8Array/);
});

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

  a.handle({ type: 'meta', wire: X.WIRE, meta: {}, frameCount: 3 });
  clock.t += 6000;
  assert.equal(a.isStalled(), true, 'parou logo após o meta ⇒ stall');

  a.handle({
    type: 'frames', wire: X.WIRE, from: 0, to: 0,
    frames: [{ index: 0, b64: X.toBase64(new Uint8Array(4)), length: 4 }]
  });
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
  a.handle({ type: 'meta', wire: X.WIRE, meta: {}, frameCount: 2 });
  a.handle({
    type: 'frames', wire: X.WIRE, from: 0, to: 1,
    frames: [
      { index: 0, b64: X.toBase64(new Uint8Array(8)), length: 8 },
      { index: 1, b64: X.toBase64(new Uint8Array(9)), length: 9 }
    ]
  });
  a.handle({ type: 'end', frameCount: 2 });
  assert.throws(() => a.assemble(), /tamanho divergente/);
});

test('custo do wire base64: medido, não presumido', () => {
  // 330 KB é a ordem de grandeza de um frame de ROI real (320×260×4 = 333 KB).
  const bytes = new Uint8Array(330 * 1024);
  for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 31) & 0xFF;
  const t0 = process.hrtime.bigint();
  const b64 = X.toBase64(bytes);
  const t1 = process.hrtime.bigint();
  const back = X.fromBase64(b64);
  const t2 = process.hrtime.bigint();

  assert.equal(back.length, bytes.length);
  // Overhead de 4/3 — contra ~3,5× de um array de números serializado em JSON.
  const overhead = b64.length / bytes.length;
  assert.ok(overhead > 1.33 && overhead < 1.35, `overhead=${overhead}`);
  const jsonArrayLen = JSON.stringify(Array.from(bytes.subarray(0, 4096))).length / 4096;
  assert.ok(jsonArrayLen > overhead * 2,
    `array em JSON custa ${jsonArrayLen}×, base64 custa ${overhead}× — base64 tem de ser bem menor`);

  const encMs = Number(t1 - t0) / 1e6;
  const decMs = Number(t2 - t1) / 1e6;
  // Teto folgado: o ponto é travar uma regressão de ordem de grandeza, não cronometrar a
  // máquina de CI. Uma captura de 300 frames paga isto 300 vezes, uma vez só, offline.
  assert.ok(encMs < 250, `encode ${encMs} ms`);
  assert.ok(decMs < 250, `decode ${decMs} ms`);
});
