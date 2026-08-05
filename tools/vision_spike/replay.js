#!/usr/bin/env node
// SPR-V3 · vision_spike/replay.js — REPLAY OFFLINE do algoritmo (E1).
//
// Para que serve
// --------------
// Permitir iterar no estimador SEM mesa ao vivo. Roda o pipeline exato do sensor sobre uma
// sequência de frames GRAVADA (formato em FORMATO_CAPTURA.md) e emite, por janela,
// `{direction, confidence, guards}` — com ABSTENÇÃO sempre que um guard dispara.
//
// Uso
//   node replay.js --capture <dir>            # captura real (evidence_class do capture.json)
//   node replay.js --synthetic cw             # cenário-controle SINTÉTICO (não vale gate)
//   node replay.js --synthetic cw --case noGreen --count 300 --fps 10 --rev 0.35
//   node replay.js --capture <dir> --json     # saída legível por máquina
//
// ⚠️ `--synthetic` imprime, e grava no JSON, `eligible_for_go_gates: false`. Nenhum número
// vindo dele pode entrar na tabela de gates do RESULTADO.md.
'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const Pipeline = require('./lib/pipeline.js');
const Synthetic = require('./lib/synthetic.js');
const Evidence = require('./lib/evidence.js');
const Direction = require('./lib/direction_core.js');
const Meter = require('./lib/rvfc_meter.js');
const AlgoSha = require('./lib/algo_sha.js');

/**
 * SHA do ALGORITMO (não do repo): é este valor que o RESULTADO.md cita por coleta.
 * A receita vive em `lib/algo_sha.js` e é compartilhada com o service worker da extensão
 * de diagnóstico — duas receitas produziriam dois hashes e um aviso permanente de
 * divergência que todo mundo aprenderia a ignorar.
 */
function algorithmSha() {
  const bytes = AlgoSha.canonicalBytes((rel) => fs.readFileSync(path.join(__dirname, rel)));
  return crypto.createHash('sha256').update(bytes).digest('hex').slice(0, AlgoSha.SHA_LENGTH);
}

function parseArgs(argv) {
  const out = { json: false };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--json') out.json = true;
    else if (a === '--capture') out.capture = argv[++i];
    else if (a === '--synthetic') out.synthetic = argv[++i];
    else if (a === '--case') out.case = argv[++i];
    else if (a === '--count') out.count = parseInt(argv[++i], 10);
    else if (a === '--fps') out.fps = parseFloat(argv[++i]);
    else if (a === '--rev') out.rev = parseFloat(argv[++i]);
    else if (a === '--window') out.window = parseInt(argv[++i], 10);
    else if (a === '--stride') out.stride = parseInt(argv[++i], 10);
    else if (a === '--decimate') out.decimate = true;
    else if (a === '--bench') out.bench = true;
    else if (a === '--help' || a === '-h') out.help = true;
  }
  return out;
}

const SYNTHETIC_CASES = {
  clean: {},
  noise: { noise: 12 },
  blur: { blur: 1 },
  overlay: { staticOverlay: true },
  noGreen: { noGreen: true },
  lowLuma: { lowLuma: true },
  occlusion: { occlusion: true },
  mirror: { mirror: true }
};

function loadCapture(dir) {
  const metaPath = path.join(dir, 'capture.json');
  if (!fs.existsSync(metaPath)) {
    throw new Error('capture.json nao encontrado em ' + dir + ' (ver FORMATO_CAPTURA.md)');
  }
  const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
  if (meta.format !== 'vision_spike_capture') throw new Error('formato desconhecido: ' + meta.format);
  if (!Array.isArray(meta.frames) || !meta.frames.length) throw new Error('captura sem frames');
  const w = meta.video && meta.video.width;
  const h = meta.video && meta.video.height;
  if (!(w > 0 && h > 0)) throw new Error('capture.json sem video.width/height');

  const frames = meta.frames.map((f, i) => {
    const expected = w * h * 4;
    let buf;
    if (meta.data_file) {
      // Exportação do navegador: RGBA concatenado num único `frames.bin`, stride = w*h*4.
      const all = loadCapture._cache && loadCapture._cache.dir === dir
        ? loadCapture._cache.buf
        : fs.readFileSync(path.join(dir, meta.data_file));
      loadCapture._cache = { dir, buf: all };
      const off = (f.offset != null ? f.offset : i) * expected;
      if (off + expected > all.length) {
        throw new Error(`${meta.data_file}: frame ${i} fora do arquivo (offset ${off}, tamanho ${all.length})`);
      }
      buf = all.subarray(off, off + expected);
    } else {
      buf = fs.readFileSync(path.join(dir, f.file));
      if (buf.length !== expected) {
        throw new Error(`${f.file}: ${buf.length} bytes, esperado ${expected} (w*h*4)`);
      }
    }
    return {
      index: i,
      wallMs: f.wallMs,
      mediaTimeS: f.mediaTimeS,
      frame: { width: w, height: h, data: new Uint8ClampedArray(buf.buffer, buf.byteOffset, buf.length) }
    };
  });
  return { meta, frames };
}

function main() {
  const args = parseArgs(process.argv);
  if (args.help || (!args.capture && !args.synthetic)) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').slice(1, 20).join('\n'));
    process.exit(args.help ? 0 : 2);
  }

  const sha = algorithmSha();
  let frames, calibration, truth, evidenceClass, source, config;

  if (args.synthetic) {
    const caseName = args.case || 'clean';
    if (!SYNTHETIC_CASES[caseName]) {
      console.error('caso sintetico desconhecido: ' + caseName +
        ' (use: ' + Object.keys(SYNTHETIC_CASES).join(', ') + ')');
      process.exit(2);
    }
    const seq = Synthetic.makeSequence(Object.assign({
      direction: args.synthetic,
      count: args.count || 60,
      fps: args.fps || 10,
      revPerS: args.rev == null ? 0.35 : args.rev
    }, SYNTHETIC_CASES[caseName]));
    frames = seq.frames;
    calibration = seq.calibration;
    truth = args.synthetic === 'static' ? null : args.synthetic;
    evidenceClass = Evidence.CLASS.SYNTHETIC;
    source = `synthetic:${args.synthetic}:${caseName}`;
  } else {
    const cap = loadCapture(args.capture);
    frames = cap.frames;
    calibration = cap.meta.calibration;
    truth = (cap.meta.truth && cap.meta.truth.direction) || null;
    evidenceClass = cap.meta.evidence_class || Evidence.CLASS.FIELD;
    source = args.capture;
    config = cap.meta.config;
    if (cap.meta.algorithm_sha && cap.meta.algorithm_sha !== sha) {
      console.warn(`⚠️  algorithm_sha da captura (${cap.meta.algorithm_sha}) != atual (${sha}).` +
        ' O resultado NAO é comparável ao registrado no RESULTADO.md.');
    }
  }

  const options = {
    truthDirection: truth,
    windowSize: args.window || Pipeline.DEFAULT_WINDOW,
    direction: Object.assign({}, config || {}, args.stride ? { pairStride: args.stride } : {})
  };

  // Captura gravada na taxa NATIVA do stream (25-30 fps) precisa ser decimada até a
  // cadência segura, senão `stride_too_small` dispara em toda janela e a cobertura sai 0.
  let decimation = null;
  if (args.decimate) {
    const target = Direction.recommendedFrameIntervalS(options.direction);
    const dec = Meter.createDecimator({ targetIntervalS: target });
    const before = frames.length;
    frames = frames.filter((f) => dec.accept(isFinite(f.mediaTimeS) ? f.mediaTimeS : f.wallMs / 1000));
    frames = frames.map((f, i) => Object.assign({}, f, { index: i }));
    decimation = { target_interval_s: +target.toFixed(4), before, after: frames.length };
    console.log(`decimado: ${before} → ${frames.length} frames (alvo ${(target * 1000).toFixed(0)} ms entre frames)`);
  }

  const t0 = process.hrtime.bigint();
  const result = Pipeline.run(frames, calibration, options);
  const elapsedMs = Number(process.hrtime.bigint() - t0) / 1e6;

  // `--bench`: p50/p95/máx por frame e por medição. As MÉDIAS do `pipeline.run` escondem
  // a cauda, e é a cauda que estoura orçamento de renderer.
  let bench = null;
  if (args.bench) {
    const built = Pipeline.buildProfiles(frames.slice(0, 3), calibration, options); // aquece o JIT
    void built;
    const perFrame = [];
    for (const f of frames) {
      const s = process.hrtime.bigint();
      Pipeline.buildProfiles([f], calibration, options);
      perFrame.push(Number(process.hrtime.bigint() - s) / 1e6);
    }
    const all = Pipeline.buildProfiles(frames, calibration, options).profiles;
    const perWindow = [];
    for (let i = options.windowSize - 1; i < all.length; i++) {
      const w = all.slice(i - options.windowSize + 1, i + 1);
      const s = process.hrtime.bigint();
      require('./lib/direction_core.js').analyzeWindow(w, calibration, options.direction);
      perWindow.push(Number(process.hrtime.bigint() - s) / 1e6);
    }
    const q = (arr, p) => {
      const s = arr.slice().sort((a, b) => a - b);
      return +s[Math.min(s.length - 1, Math.round(p * (s.length - 1)))].toFixed(3);
    };
    bench = {
      unwrap_ms_por_frame: { p50: q(perFrame, 0.5), p95: q(perFrame, 0.95), max: q(perFrame, 1) },
      analise_ms_por_medicao: perWindow.length
        ? { p50: q(perWindow, 0.5), p95: q(perWindow, 0.95), max: q(perWindow, 1) } : null,
      runtime: 'node ' + process.version + ' (NAO é o renderer do iframe)'
    };
  }

  const report = Evidence.envelope('E1', evidenceClass, {
    source,
    algorithm_sha: sha,
    truth_direction: truth,
    window_size: options.windowSize,
    pair_stride: (options.direction && options.direction.pairStride) || Direction.DEFAULTS.pairStride,
    scene_reference: result.sceneRefSource,
    warnings: result.warnings,
    decimation,
    bench,
    summary: result.summary,
    cost: {
      total_ms: +elapsedMs.toFixed(2),
      unwrap_ms_per_frame: result.cost.unwrapMsPerFrame == null ? null : +result.cost.unwrapMsPerFrame.toFixed(3),
      analyze_ms_per_window: result.cost.analyzeMsPerWindow == null ? null : +result.cost.analyzeMsPerWindow.toFixed(3),
      note: 'custo em Node sobre buffers em memoria — NAO é o custo no renderer do iframe (ver ORCAMENTO.md). ' +
        'O unwrap roda por FRAME; a correlação roda por MEDIÇÃO (1 por giro no sensor real).'
    },
    windows: result.windows.map(w => ({
      closing_frame: w.closingFrameIndex,
      direction: w.direction,
      confidence: +w.confidence.toFixed(4),
      guards: w.guards,
      deg_per_s: +(w.degreesPerSecond || 0).toFixed(2),
      alias_margin: +(w.aliasMargin || 0).toFixed(3)
    }))
  });

  if (args.json) {
    process.stdout.write(JSON.stringify(report, null, 2) + '\n');
    return;
  }

  const s = result.summary;
  console.log('─'.repeat(72));
  console.log(`SPR-V3 replay offline · fonte: ${source}`);
  console.log(`evidence_class: ${report.evidence_class}   eligible_for_go_gates: ${report.eligible_for_go_gates}`);
  if (!report.eligible_for_go_gates) {
    console.log('⚠️  NADA daqui pode preencher a tabela de gates do RESULTADO.md.');
  }
  console.log(`algorithm_sha: ${sha}   janela: ${options.windowSize} frames   stride: ${report.payload.pair_stride}`);
  console.log(`referencia de cena: ${result.sceneRefSource}`);
  result.warnings.forEach(w => console.log(`⚠️  ${w}`));
  console.log('─'.repeat(72));
  console.log(`frames_processed   : ${s.frames_processed} (aquecimento: ${s.warmup_frames})`);
  console.log(`windows_evaluated  : ${s.windows_evaluated}`);
  console.log(`emitidos           : ${s.emitted}`);
  console.log(`abstencoes         : ${s.abstained}` +
    (s.abstencao ? ` (${(s.abstencao.valor * 100).toFixed(1)}% de ${s.abstencao.denominador})` : ''));
  if (s.sinal) {
    console.log(`sinal              : ${s.sinal.numerador}/${s.sinal.denominador} = ` +
      `${(s.sinal.valor * 100).toFixed(2)}%   (teto da captura: ` +
      `${(s.sinal_teto_da_captura.valor * 100).toFixed(2)}%)`);
    if (s.sinal_teto_da_captura.valor < 0.98) {
      console.log('⚠️  captura curta demais para o gate de 98%: são necessários >= 250 frames.');
    }
  }
  if (s.acuracia_replay) {
    console.log(`acuracia (emitidos): ${s.acuracia_replay.numerador}/${s.acuracia_replay.denominador} = ` +
      `${(s.acuracia_replay.valor * 100).toFixed(2)}%`);
  }
  const guards = Object.keys(s.guards);
  console.log(`guards             : ${guards.length ? guards.map(g => `${g}=${s.guards[g]}`).join('  ') : '(nenhum)'}`);
  console.log(`custo              : unwrap ${report.payload.cost.unwrap_ms_per_frame} ms/frame · ` +
    `analise ${report.payload.cost.analyze_ms_per_window} ms/janela (media; Node, NAO é o renderer)`);
  if (bench) {
    console.log(`  p50/p95/max unwrap : ${bench.unwrap_ms_por_frame.p50} / ${bench.unwrap_ms_por_frame.p95} / ${bench.unwrap_ms_por_frame.max} ms`);
    if (bench.analise_ms_por_medicao) {
      console.log(`  p50/p95/max analise: ${bench.analise_ms_por_medicao.p50} / ${bench.analise_ms_por_medicao.p95} / ${bench.analise_ms_por_medicao.max} ms`);
    }
  }
  console.log('─'.repeat(72));
}

if (require.main === module) {
  try {
    main();
  } catch (e) {
    console.error('replay falhou: ' + e.message);
    process.exit(1);
  }
}

module.exports = { algorithmSha, loadCapture, SYNTHETIC_CASES };
