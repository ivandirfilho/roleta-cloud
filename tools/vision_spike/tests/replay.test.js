'use strict';
// SPR-V3 · testes do REPLAY OFFLINE (E1) e da aritmética dos GATES.
//
// Estes testes protegem o que mais importa politicamente no sprint: que um número do
// spike não possa ser lido como número de campo, e que toda taxa venha com denominador.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const P = require('../lib/pipeline.js');
const Syn = require('../lib/synthetic.js');
const Ev = require('../lib/evidence.js');
const Replay = require('../replay.js');

test('replay emite {direction, confidence, guards} por janela', () => {
  const seq = Syn.makeSequence({ direction: 'cw', count: 12, fps: 10, revPerS: 0.35 });
  const r = P.run(seq.frames, seq.calibration, { truthDirection: 'cw' });
  assert.equal(r.windows.length, 12 - P.DEFAULT_WINDOW + 1);
  for (const w of r.windows) {
    assert.ok(['cw', 'ccw', null].includes(w.direction));
    assert.equal(typeof w.confidence, 'number');
    assert.ok(Array.isArray(w.guards));
    if (w.guards.length > 0) assert.equal(w.direction, null);   // abstenção obrigatória
  }
});

test('toda taxa do sumário vem com numerador E denominador', () => {
  const seq = Syn.makeSequence({ direction: 'cw', count: 20, fps: 10 });
  const s = P.run(seq.frames, seq.calibration, { truthDirection: 'cw' }).summary;
  for (const k of ['sinal', 'acuracia_replay', 'abstencao', 'sinal_teto_da_captura']) {
    if (s[k] === null) continue;
    assert.ok(Number.isFinite(s[k].numerador), k);
    assert.ok(Number.isFinite(s[k].denominador), k);
    assert.ok(Math.abs(s[k].valor - s[k].numerador / s[k].denominador) < 1e-12, k);
  }
  assert.equal(s.frames_processed, 20);
  assert.equal(s.warmup_frames, P.DEFAULT_WINDOW - 1);
  assert.equal(s.windows_evaluated, 20 - P.DEFAULT_WINDOW + 1);
});

test('o denominador do `sinal` é FRAMES PROCESSADOS — captura curta não fecha o gate', () => {
  // O teto aritmético de uma captura de 40 frames é 35/40 = 87,5%: o gate de 98% é
  // INALCANÇÁVEL por construção. Isso é proposital — impede "98%" de 30 frames.
  const seq = Syn.makeSequence({ direction: 'cw', count: 40, fps: 10 });
  const s = P.run(seq.frames, seq.calibration, { truthDirection: 'cw' }).summary;
  assert.equal(s.sinal.denominador, 40);
  assert.ok(s.sinal_teto_da_captura.valor < 0.98);
  // 250 frames é o mínimo para o teto passar de 98% com janela 6.
  assert.ok((250 - P.DEFAULT_WINDOW + 1) / 250 >= 0.98);
  assert.ok((240 - P.DEFAULT_WINDOW + 1) / 240 < 0.98);
});

test('acurácia usa TODOS os emitidos (não os "melhores")', () => {
  const seq = Syn.makeSequence({ direction: 'cw', count: 14, fps: 10 });
  const r = P.run(seq.frames, seq.calibration, { truthDirection: 'cw' });
  const emitidos = r.windows.filter(w => w.emitted).length;
  assert.equal(r.summary.acuracia_replay.denominador, emitidos);
  assert.equal(r.summary.correct + r.summary.wrong, emitidos);
});

test('sem verdade anotada NÃO se inventa acurácia', () => {
  const seq = Syn.makeSequence({ direction: 'cw', count: 12, fps: 10 });
  const s = P.run(seq.frames, seq.calibration, {}).summary;
  assert.equal(s.sinal, null);
  assert.equal(s.acuracia_replay, null);
  assert.equal(s.correct, null);
});

test('referência de cena vinda do 1º frame é DENUNCIADA como modo de teste', () => {
  const seq = Syn.makeSequence({ direction: 'cw', count: 8, fps: 10 });
  const r = P.run(seq.frames, seq.calibration, {});
  assert.equal(r.sceneRefSource, 'first_frame');
  assert.ok(r.warnings.includes('scene_reference_from_first_frame_not_calibration'));
});

test('FAIL-CLOSED: sem `sceneSignature` na calibração o anti-cena NÃO é desligado em silêncio', () => {
  // O coletor usa `failClosedScene: true`. Sem isso ele caía no primeiro frame, comparava
  // a cena com ela mesma, o guard de NCC nunca disparava — e o veredito PARECIA totalmente
  // guardado. "Não sei" tem de virar abstenção, não aprovação.
  const seq = Syn.makeSequence({ direction: 'cw', count: 8, fps: 10 });
  const semCalib = Object.assign({}, seq.calibration);
  delete semCalib.sceneSignature;

  const r = P.run(seq.frames, semCalib, { failClosedScene: true, truthDirection: 'cw' });
  assert.equal(r.sceneRefSource, 'missing_calibration');
  assert.ok(r.warnings.includes('scene_reference_missing_calibration_fail_closed'));
  assert.equal(r.summary.emitted, 0, 'sem referência de cena NADA pode ser emitido');
  for (const w of r.windows) {
    assert.equal(w.direction, null);
    assert.ok(w.guards.includes('scene_ncc_low'), JSON.stringify(w.guards));
    assert.equal(w.sceneReference, 'missing_calibration');
  }
});

test('todo veredito diz CONTRA O QUE a cena foi comparada', () => {
  const U = require('../lib/unwrap.js');
  const seq = Syn.makeSequence({ direction: 'cw', count: 8, fps: 10 });

  const semRef = P.run(seq.frames, seq.calibration, {});
  assert.ok(semRef.windows.every((w) => w.sceneReference === 'first_frame'));

  const sig = U.sceneSignature(seq.frames[0].frame, seq.calibration);
  const calib = Object.assign({}, seq.calibration, { sceneSignature: Array.from(sig.signature) });
  const comRef = P.run(seq.frames, calib, {});
  assert.ok(comRef.windows.every((w) => w.sceneReference === 'calibration'));
});

test('com assinatura de cena da CALIBRAÇÃO o guard de NCC volta a existir', () => {
  const U = require('../lib/unwrap.js');
  const base = Syn.makeSequence({ direction: 'cw', count: 8, fps: 10 });
  const sig = U.sceneSignature(base.frames[0].frame, base.calibration);
  const calib = Object.assign({}, base.calibration, { sceneSignature: Array.from(sig.signature) });

  const igual = P.run(base.frames, calib, {});
  assert.equal(igual.sceneRefSource, 'calibration');
  assert.ok(!igual.windows[0].guards.includes('scene_ncc_low'));

  const outra = Syn.makeSequence({ direction: 'cw', count: 8, fps: 10, sceneOcclusion: true });
  const mudou = P.run(outra.frames, calib, {});
  assert.ok(mudou.windows[0].guards.includes('scene_ncc_low'), JSON.stringify(mudou.windows[0].guards));
  assert.equal(mudou.windows[0].direction, null);
});

test('custo é reportado separado: unwrap por FRAME, análise por MEDIÇÃO', () => {
  const seq = Syn.makeSequence({ direction: 'cw', count: 10, fps: 10 });
  const r = P.run(seq.frames, seq.calibration, {});
  assert.ok(r.cost.unwrapMsPerFrame >= 0);
  assert.ok(r.cost.analyzeMsPerWindow >= 0);
});

test('envelope de evidência: só `field` é elegível aos gates', () => {
  assert.equal(Ev.envelope('E0', Ev.CLASS.FIELD, {}).eligible_for_go_gates, true);
  assert.equal(Ev.envelope('E0', Ev.CLASS.FIXTURE, {}).eligible_for_go_gates, false);
  assert.equal(Ev.envelope('E1', Ev.CLASS.SYNTHETIC, {}).eligible_for_go_gates, false);
  assert.throws(() => Ev.envelope('E0', 'inventada', {}), /evidence_class invalido/);
});

test('sequência sintética se declara inelegível aos gates', () => {
  const seq = Syn.makeSequence({ direction: 'cw', count: 6 });
  assert.equal(seq.evidenceClass, 'synthetic');
  assert.equal(seq.eligibleForGoGates, false);
});

test('gerador sintético é DETERMINÍSTICO (replay reproduzível)', () => {
  const a = Syn.makeSequence({ direction: 'cw', count: 3, noise: 8 });
  const b = Syn.makeSequence({ direction: 'cw', count: 3, noise: 8 });
  assert.deepEqual(Array.from(a.frames[2].frame.data.slice(0, 400)),
    Array.from(b.frames[2].frame.data.slice(0, 400)));
});

test('REGRESSÃO: feed a 12/24/25/30/60 fps — sem decimação abstém; com decimação, emite', () => {
  // O bug que isto trava: `captureBurst` gravava 6 frames CONSECUTIVOS na taxa nativa.
  // A 25 fps a rajada inteira dura 200 ms e o guard `stride_too_small` (que exige
  // Δt_par ≥ 270 ms) dispara SEMPRE. Em campo isso daria cobertura 0/N — um NO-GO que
  // seria defeito de ferramental, não propriedade do mundo.
  //
  // 12, 24 e 60 fps são o SEGUNDO bug: com o decimador aceitando a 90% do alvo, o
  // intervalo aceito (83 ms) passava no decimador e reprovava no guard (precisa de 90 ms).
  // O limiar dos dois tem de ser o MESMO número.
  const D = require('../lib/direction_core.js');
  const Meter = require('../lib/rvfc_meter.js');

  for (const fps of [12, 24, 25, 30, 60]) {
    const seq = Syn.makeSequence({ direction: 'cw', count: Math.round(fps * 3), fps, revPerS: 0.35 });

    const cru = P.run(seq.frames, seq.calibration, { truthDirection: 'cw' });
    assert.equal(cru.summary.emitted, 0, `fps=${fps} sem decimação deveria abster tudo`);
    assert.ok(cru.summary.guards.stride_too_small > 0, `fps=${fps}`);

    const dec = Meter.createDecimator({ targetIntervalS: D.recommendedFrameIntervalS() });
    const decimados = seq.frames
      .filter((f) => dec.accept(f.mediaTimeS))
      .map((f, i) => Object.assign({}, f, { index: i }));
    const bom = P.run(decimados, seq.calibration, { truthDirection: 'cw' });
    assert.ok(bom.summary.emitted > 0, `fps=${fps} com decimação deveria emitir`);
    assert.equal(bom.summary.wrong, 0, `fps=${fps}`);
    assert.equal(bom.summary.guards.stride_too_small, undefined,
      `fps=${fps}: decimador e guard têm de concordar`);
  }
});

test('REGRESSÃO: com JITTER de chegada, a decimação continua satisfazendo o guard', () => {
  // Um stream real não entrega em grade perfeita. Se o decimador aceitasse "quase" no
  // alvo, o jitter empurraria pares para baixo do limiar e a cobertura cairia em campo
  // sem explicação nenhuma nos vereditos.
  const D = require('../lib/direction_core.js');
  const Meter = require('../lib/rvfc_meter.js');

  for (const fps of [12, 25, 30, 60]) {
    for (const jitterFrac of [0.2, 0.45]) {
      const seq = Syn.makeSequence({
        direction: 'ccw', count: Math.round(fps * 3), fps, revPerS: 0.30, jitterFrac
      });
      const dec = Meter.createDecimator({ targetIntervalS: D.recommendedFrameIntervalS() });
      const decimados = seq.frames
        .filter((f) => dec.accept(f.mediaTimeS))
        .map((f, i) => Object.assign({}, f, { index: i }));
      const r = P.run(decimados, seq.calibration, { truthDirection: 'ccw' });
      assert.equal(r.summary.guards.stride_too_small, undefined,
        `fps=${fps} jitter=${jitterFrac}`);
      assert.ok(r.summary.emitted > 0, `fps=${fps} jitter=${jitterFrac} deveria emitir`);
      assert.equal(r.summary.wrong, 0, `fps=${fps} jitter=${jitterFrac}`);
    }
  }
});

test('INVARIANTE: todo gap aceito pelo decimador satisfaz o guard `stride_too_small`', () => {
  const D = require('../lib/direction_core.js');
  const Meter = require('../lib/rvfc_meter.js');
  const target = D.recommendedFrameIntervalS();
  const stride = D.DEFAULTS.pairStride;
  const dec = Meter.createDecimator({ targetIntervalS: target });

  const aceitos = [];
  for (let i = 0; i < 400; i++) {
    const t = i / 60 + (i % 7) * 0.0013;         // 60 fps com jitter determinístico
    if (dec.accept(t)) aceitos.push(t);
  }
  for (let i = stride; i < aceitos.length; i++) {
    const dtPar = aceitos[i] - aceitos[i - stride];
    const minExpectedDeg = D.DEFAULTS.rotorRevPerSecMin * 360 * dtPar;
    assert.ok(minExpectedDeg >= D.DEFAULTS.minAliasSafetyDeg,
      `par ${i}: ${minExpectedDeg} < ${D.DEFAULTS.minAliasSafetyDeg}`);
  }
});

test('algorithm_sha usa UMA receita compartilhada (Node e service worker)', () => {
  const AlgoSha = require('../lib/algo_sha.js');
  const crypto = require('node:crypto');
  const bytes = AlgoSha.canonicalBytes((rel) =>
    fs.readFileSync(path.join(__dirname, '..', rel)));
  const esperado = crypto.createHash('sha256').update(bytes).digest('hex')
    .slice(0, AlgoSha.SHA_LENGTH);
  assert.equal(Replay.algorithmSha(), esperado);
  assert.equal(AlgoSha.ALGORITHM_FILES.length, 4);
});

test('a receita do sha inclui o CAMINHO, não só o conteúdo (ordem importa)', () => {
  const AlgoSha = require('../lib/algo_sha.js');
  const a = AlgoSha.canonicalBytes(() => new Uint8Array([1, 2, 3]));
  const b = AlgoSha._concatBytes([new Uint8Array([1, 2, 3])]);
  assert.ok(a.length > b.length * 4, 'os caminhos precisam estar no buffer canônico');
});

test('loadCapture lê o formato `data_file` exportado pelo navegador', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vs-cap-'));
  try {
    const seq = Syn.makeSequence({ direction: 'ccw', count: 8, fps: 10 });
    const w = seq.frames[0].frame.width, h = seq.frames[0].frame.height;
    const stride = w * h * 4;
    const buf = Buffer.alloc(stride * seq.frames.length);
    seq.frames.forEach((f, i) => Buffer.from(f.frame.data.buffer).copy(buf, i * stride));
    fs.writeFileSync(path.join(dir, 'frames.bin'), buf);
    fs.writeFileSync(path.join(dir, 'capture.json'), JSON.stringify({
      format: 'vision_spike_capture',
      version: 1,
      evidence_class: 'fixture',
      data_file: 'frames.bin',
      video: { width: w, height: h },
      calibration: seq.calibration,
      truth: { direction: 'ccw' },
      frames: seq.frames.map((f, i) => ({ file: null, offset: i, wallMs: f.wallMs, mediaTimeS: f.mediaTimeS }))
    }));

    const cap = Replay.loadCapture(dir);
    assert.equal(cap.frames.length, 8);
    const r = P.run(cap.frames, cap.meta.calibration, { truthDirection: 'ccw' });
    assert.equal(r.summary.wrong, 0);
    assert.ok(r.summary.emitted > 0);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('EOL: LF e CRLF do MESMO fonte produzem o MESMO algorithm_sha', () => {
  // Regressão do achado HIGH: com `core.autocrlf=true` (padrão do Git no Windows) o blob é
  // LF e a cópia de trabalho é CRLF. O mesmo commit dava um sha no Windows e outro no
  // Linux/CI — um identificador de algoritmo que muda com o sistema operacional não
  // identifica algoritmo nenhum, e o aviso de divergência do replay viraria ruído.
  const AlgoSha = require('../lib/algo_sha.js');
  const crypto = require('node:crypto');
  const lf = 'function f() {\n  return 1;\n}\n';
  const crlf = lf.replace(/\n/g, '\r\n');
  const enc = (s) => new Uint8Array(Buffer.from(s, 'utf8'));

  const shaOf = (src) => crypto.createHash('sha256')
    .update(AlgoSha.canonicalBytes(() => enc(src))).digest('hex').slice(0, 16);

  assert.equal(shaOf(lf), shaOf(crlf));
  // E a normalização não pode ser "apagar todo CR": um CR solto é byte de conteúdo.
  assert.notEqual(shaOf(lf), shaOf('function f() {\rreturn 1;\r}'));
});

test('normalizeEol converte só CRLF, preserva CR solto e LF isolado', () => {
  const { normalizeEol } = require('../lib/algo_sha.js');
  assert.deepEqual(Array.from(normalizeEol(new Uint8Array([65, 13, 10, 66]))), [65, 10, 66]);
  assert.deepEqual(Array.from(normalizeEol(new Uint8Array([65, 13, 66]))), [65, 13, 66]);
  assert.deepEqual(Array.from(normalizeEol(new Uint8Array([65, 10, 66]))), [65, 10, 66]);
  assert.deepEqual(Array.from(normalizeEol(new Uint8Array([13, 10, 13, 10]))), [10, 10]);
});

test('algorithmSha do repo é o mesmo com o arquivo em LF ou CRLF em disco', () => {
  // Prova end-to-end: reescreve os bytes reais dos 4 arquivos nos dois EOL e compara.
  const AlgoSha = require('../lib/algo_sha.js');
  const crypto = require('node:crypto');
  const raw = {};
  for (const rel of AlgoSha.ALGORITHM_FILES) {
    raw[rel] = fs.readFileSync(path.join(__dirname, '..', rel));
  }
  const toLf = (b) => new Uint8Array(Buffer.from(b.toString('utf8').replace(/\r\n/g, '\n'), 'utf8'));
  const toCrlf = (b) => new Uint8Array(
    Buffer.from(b.toString('utf8').replace(/\r\n/g, '\n').replace(/\n/g, '\r\n'), 'utf8'));
  const sha = (conv) => crypto.createHash('sha256')
    .update(AlgoSha.canonicalBytes((rel) => conv(raw[rel]))).digest('hex').slice(0, 16);

  assert.equal(sha(toLf), sha(toCrlf));
  assert.equal(sha(toLf), Replay.algorithmSha());
});

test('algorithmSha é estável e tem o formato que o RESULTADO.md cita', () => {
  const sha = Replay.algorithmSha();
  assert.match(sha, /^[0-9a-f]{16}$/);
  assert.equal(sha, Replay.algorithmSha());
});

test('captura corrompida falha ALTO, não silenciosamente', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vs-cap-'));
  try {
    fs.writeFileSync(path.join(dir, 'frames.bin'), Buffer.alloc(16));
    fs.writeFileSync(path.join(dir, 'capture.json'), JSON.stringify({
      format: 'vision_spike_capture', version: 1, data_file: 'frames.bin',
      video: { width: 320, height: 260 }, calibration: Syn.defaultCalibration(),
      frames: [{ offset: 0, wallMs: 0, mediaTimeS: 0 }]
    }));
    assert.throws(() => Replay.loadCapture(dir), /fora do arquivo/);
    assert.throws(() => Replay.loadCapture(path.join(dir, 'nao-existe')), /capture.json nao encontrado/);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
