// SPR-V3 · vision_spike/probe/fixture_video.js — driver da bancada.
'use strict';

const $ = (id) => document.getElementById(id);
const srcCanvas = $('src');
const srcCtx = srcCanvas.getContext('2d');
const vid = $('vid');
const calib = VSSynthetic.defaultCalibration();

let anim = null;
let meter = null;
let rvfcHandle = null;
let running = false;

function startSource() {
  const revPerS = parseFloat($('rev').value) || 0.35;
  const fps = parseFloat($('fps').value) || 10;
  const dir = $('dir').value;
  const sign = dir === 'ccw' ? -1 : (dir === 'static' ? 0 : 1);
  if (anim) clearInterval(anim);

  const t0 = performance.now();
  const draw = () => {
    const tS = (performance.now() - t0) / 1000;
    const frame = VSSynthetic.renderWheelFrame(sign * revPerS * 360 * tS, { scene: VSSynthetic.DEFAULT_SCENE });
    srcCtx.putImageData(new ImageData(frame.data, frame.width, frame.height), 0, 0);
  };
  draw();
  anim = setInterval(draw, 1000 / fps);

  if (!vid.srcObject) {
    // `captureStream` entrega um MediaStream — o MESMO tipo de `srcObject` que a probe E0
    // classifica como `mediastream`. Isso é útil para exercitar o classificador, e é
    // exatamente por isso que a probe reporta `webrtc_confirmed: null`: MediaStream é
    // compatível com WebRTC, mas não prova WebRTC (esta página é a contraprova viva).
    vid.srcObject = srcCanvas.captureStream(fps);
    vid.play().catch(() => { });
  }
}

$('startSrc').onclick = startSource;

$('e0').onclick = async () => {
  const t0 = performance.now();
  try {
    const bmp = await createImageBitmap(vid);
    const oc = new OffscreenCanvas(bmp.width, bmp.height);
    const c = oc.getContext('2d', { willReadFrequently: true });
    c.drawImage(bmp, 0, 0);
    const px = c.getImageData(0, 0, 1, 1);
    $('e0out').textContent = JSON.stringify(VSEvidence.envelope('E0', VSEvidence.CLASS.FIXTURE, {
      pixel_read_ok: true, tainted: false,
      bitmap: { width: bmp.width, height: bmp.height },
      sample_rgba: Array.from(px.data),
      delivery: vid.srcObject ? 'mediastream' : 'src',
      webrtc_confirmed: null,
      rvfc_supported: typeof vid.requestVideoFrameCallback === 'function',
      elapsed_ms: +(performance.now() - t0).toFixed(2)
    }), null, 2);
  } catch (e) {
    $('e0out').textContent = JSON.stringify(VSEvidence.envelope('E0', VSEvidence.CLASS.FIXTURE, {
      pixel_read_ok: false, tainted: e.name === 'SecurityError',
      error: { name: e.name, message: e.message }
    }), null, 2);
  }
};

$('e0bStart').onclick = () => {
  if (running) return;
  if (typeof vid.requestVideoFrameCallback !== 'function') {
    $('e0bout').textContent = 'requestVideoFrameCallback NAO suportado neste navegador — ' +
      'resultado negativo valido: sem rVFC o desenho do sensor cai.';
    return;
  }
  meter = VSRvfcMeter.createFrameRateMeter({ bucketMs: 1000 });
  running = true;
  const step = (now, md) => {
    meter.record({
      wallMs: performance.now(),
      mediaTime: md && md.mediaTime,
      presentedFrames: md && md.presentedFrames,
      visibilityState: document.visibilityState,
      hasFocus: document.hasFocus()
    });
    if (running) rvfcHandle = vid.requestVideoFrameCallback(step);
  };
  rvfcHandle = vid.requestVideoFrameCallback(step);
  const tick = setInterval(() => {
    if (!running) return clearInterval(tick);
    $('e0bout').textContent = JSON.stringify(meter.summary(), null, 2);
  }, 1000);
};

$('e0bStop').onclick = () => {
  running = false;
  if (rvfcHandle && vid.cancelVideoFrameCallback) vid.cancelVideoFrameCallback(rvfcHandle);
  if (meter) {
    $('e0bout').textContent = JSON.stringify(
      VSEvidence.envelope('E0b', VSEvidence.CLASS.FIXTURE, { summary: meter.summary() }), null, 2);
  }
};

// Custo NO RENDERER: é este número (não o do Node) que se compara ao alvo de 1-3 ms/frame
// do brief. Medimos só o unwrap + assinatura de cena, que é o que roda por FRAME; a
// correlação roda uma vez por MEDIÇÃO (1 por giro), e é medida à parte.
$('bench').onclick = async () => {
  const N = 120;
  const unwrapMs = [];
  let analyzeMs = null;
  const profiles = [];
  for (let i = 0; i < N; i++) {
    const bmp = await createImageBitmap(vid);
    const oc = new OffscreenCanvas(bmp.width, bmp.height);
    const c = oc.getContext('2d', { willReadFrequently: true });
    c.drawImage(bmp, 0, 0);
    const img = c.getImageData(0, 0, bmp.width, bmp.height);
    const frame = { width: img.width, height: img.height, data: img.data };
    const t0 = performance.now();
    const un = VSUnwrap.unwrapRotor(frame, calib);
    const sc = VSUnwrap.sceneSignature(frame, calib);
    unwrapMs.push(performance.now() - t0);
    if (profiles.length < 6 && un.ok && sc.ok) {
      profiles.push({
        tMs: performance.now(), mediaTimeS: i / 10,
        chroma: un.chroma, meanLuma: un.meanLuma,
        invalidFrac: Math.max(un.invalidFrac, sc.invalidFrac), ncc: 1
      });
    }
    bmp.close && bmp.close();
  }
  if (profiles.length === 6) {
    const t1 = performance.now();
    VSDirection.analyzeWindow(profiles, calib);
    analyzeMs = performance.now() - t1;
  }
  const s = unwrapMs.slice().sort((a, b) => a - b);
  const q = (p) => s[Math.min(s.length - 1, Math.round(p * (s.length - 1)))];
  $('benchout').textContent = JSON.stringify(VSEvidence.envelope('E1', VSEvidence.CLASS.FIXTURE, {
    frames: N,
    unwrap_ms_por_frame: { p50: +q(0.5).toFixed(3), p95: +q(0.95).toFixed(3), max: +s[s.length - 1].toFixed(3) },
    analise_ms_por_medicao: analyzeMs == null ? null : +analyzeMs.toFixed(3),
    alvo_do_brief_ms_por_frame: '1-3',
    nota: 'renderer desta bancada; a mesa real tem outra resolucao de video e outra carga de GPU/CPU.'
  }), null, 2);
};

startSource();
