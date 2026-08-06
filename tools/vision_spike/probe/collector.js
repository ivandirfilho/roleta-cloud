// SPR-V3 · vision_spike/probe/collector.js — COLETOR DE CAMPO (V3-B) e sensor de bancada.
//
// ⚠️ ZERO AUTORIDADE — leia antes de mexer ⚠️
// Este arquivo NUNCA fala com o servidor do Roleta Cloud, NUNCA emite `direction_event`,
// NUNCA toca `direcao`, `seed_parity`, `spin_seq`, timeline, decisão ou stake. Ele grava
// veredito + guards em `chrome.storage.local` e, opcionalmente, mantém a captura EM
// MEMÓRIA para o operador baixar no próprio disco. **Frames nunca saem da máquina**:
// não há upload, não há fetch, não há WebSocket aqui. Se você adicionar um, saiu do sprint.
//
// Fluxo (o desenho aprovado, §10.2.2-4):
//   probe de movimento a ~1 FPS NA PRÓPRIA ROI  →  grava 6 frames por rVFC  →  unwrap
//   elíptico  →  correlação + guards  →  veredito OU abstenção.
// O trigger e o sensor são o MESMO pixel: nenhum seletor de DOM novo para apodrecer.
// A confirmação por OPEN→CLOSED vem do poll de 2 s que a extensão de PRODUÇÃO já faz —
// aqui ela entra como anotação do operador, não como import (o spike não importa produção).
(function () {
  'use strict';

  var POLICY_KEY = 'vsProbePolicy';
  var CALIB_KEY = 'vsCalibration';
  var VERDICTS_KEY = 'vsVerdicts';
  var CLASS_KEY = 'vsEvidenceClass';
  var SHA_KEY = 'vsAlgorithmSha';
  var MAX_VERDICTS = 500;
  var CAPTURE_FRAMES = 6;          // 6 frames + stride 3 = 3 pares
  var TRIGGER_PERIOD_MS = 1000;    // ~1 FPS
  var BURST_TIMEOUT_MS = 4000;     // rVFC pode simplesmente PARAR (aba oculta) — ver measure()
  var RECORD_DEFAULT_FRAMES = 300; // >=250 é o mínimo para o gate de sinal (ver FORMATO_CAPTURA.md)
  var RECORD_MAX_BYTES = 350 * 1024 * 1024;

  var state = {
    running: false,
    calibration: null,
    trigger: null,
    timer: null,
    busy: false,
    lastCapture: null,             // {meta, frames:[Uint8ClampedArray]} — só em memória
    keepCapture: false,
    recording: null,               // {target, frames:[], meta, bytes, resolve}
    evidenceClass: 'fixture',      // declarado pelo operador no popup; NUNCA promovido aqui
    algorithmSha: null,
    stats: { triggers: 0, measurements: 0, emitted: 0, abstained: 0 }
  };

  function pickVideo() {
    var vids = Array.prototype.slice.call(document.querySelectorAll('video'));
    if (!vids.length) return null;
    return vids.reduce(function (a, b) {
      return (b.videoWidth * b.videoHeight) > (a.videoWidth * a.videoHeight) ? b : a;
    }, vids[0]);
  }

  // Caixa mínima que contém a SCENE_BAND inteira (senão o NCC de cena sai do quadro).
  function roiBox(calib, vw, vh) {
    var outer = (calib.sceneBand ? calib.sceneBand[1] : 1.45) + 0.02;
    var cp = Math.cos(calib.phi || 0), sp = Math.sin(calib.phi || 0);
    var hx = outer * Math.hypot(calib.a * cp, calib.b * sp);
    var hy = outer * Math.hypot(calib.a * sp, calib.b * cp);
    var x0 = Math.max(0, Math.floor(calib.center.x - hx) - 2);
    var y0 = Math.max(0, Math.floor(calib.center.y - hy) - 2);
    var x1 = Math.min(vw, Math.ceil(calib.center.x + hx) + 2);
    var y1 = Math.min(vh, Math.ceil(calib.center.y + hy) + 2);
    return { x: x0, y: y0, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0) };
  }

  var _canvas = null, _ctx = null;
  function ensureCanvas(w, h) {
    if (!_canvas || _canvas.width !== w || _canvas.height !== h) {
      _canvas = new OffscreenCanvas(w, h);
      _ctx = _canvas.getContext('2d', { willReadFrequently: true });
    }
    return _ctx;
  }

  /** Lê a ROI do frame corrente. Devolve null em SecurityError (taint) — sem palpite. */
  function grabRoi(video, calib) {
    var vw = video.videoWidth, vh = video.videoHeight;
    if (!(vw > 0 && vh > 0)) return null;
    var box = roiBox(calib, vw, vh);
    try {
      var ctx = ensureCanvas(box.w, box.h);
      ctx.drawImage(video, box.x, box.y, box.w, box.h, 0, 0, box.w, box.h);
      var img = ctx.getImageData(0, 0, box.w, box.h);
      return {
        frame: { width: box.w, height: box.h, data: img.data },
        box: box,
        // calibração transladada para as coordenadas LOCAIS do recorte
        calib: Object.assign({}, calib, {
          center: { x: calib.center.x - box.x, y: calib.center.y - box.y }
        })
      };
    } catch (e) {
      return { error: { name: e && e.name, message: e && e.message }, tainted: e && e.name === 'SecurityError' };
    }
  }

  // Grava `count` frames DECIMADOS até a cadência segura (ver `createDecimator`), com
  // timeout e ORÇAMENTO DE MEMÓRIA CUMULATIVO: paramos de alocar quando o teto é atingido,
  // em vez de encher a memória e cortar depois — cortar depois já pagou o custo inteiro,
  // que é exatamente o que se queria evitar num renderer de terceiro.
  function captureBurst(video, calib, count, timeoutMs, maxBytes) {
    count = count || CAPTURE_FRAMES;
    timeoutMs = timeoutMs || BURST_TIMEOUT_MS;
    return new Promise(function (resolve) {
      if (typeof video.requestVideoFrameCallback !== 'function') {
        return resolve({ error: { name: 'rvfc_unsupported' }, frames: [] });
      }
      var frames = [];
      var settled = false;
      var budget = globalThis.VSExportStream.createByteBudget(maxBytes || 0);
      var t0 = performance.now();
      var dec = globalThis.VSRvfcMeter.createDecimator({
        targetIntervalS: globalThis.VSDirection.recommendedFrameIntervalS()
      });
      var timer = setTimeout(function () {
        if (settled) return;
        settled = true;
        resolve({ error: { name: 'rvfc_timeout' }, frames: frames, bytes: budget.used(), decimator: dec.stats() });
      }, timeoutMs);

      function done(r) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(Object.assign({ bytes: budget.used(), decimator: dec.stats() }, r));
      }

      function step(now, meta) {
        if (settled) return;
        var wallS = (performance.now() - t0) / 1000;
        var tS = (meta && isFinite(meta.mediaTime)) ? meta.mediaTime : wallS;
        if (!dec.accept(tS)) {
          video.requestVideoFrameCallback(step);
          return;
        }
        var g = grabRoi(video, calib);
        if (!g || g.error) return done({ error: (g && g.error) || { name: 'grab_failed' }, frames: frames });
        // Consulta o teto ANTES de guardar: quando o próximo frame não cabe, para.
        // Guardar e cortar depois já teria pago o custo inteiro.
        if (!budget.fits(g.frame.data.length)) {
          return done({ error: { name: 'memory_budget' }, frames: frames });
        }
        budget.add(g.frame.data.length);
        frames.push({
          index: frames.length,
          wallMs: performance.now() - t0,
          mediaTimeS: meta && meta.mediaTime,
          presentedFrames: meta && meta.presentedFrames,
          visibilityState: document.visibilityState,
          frame: g.frame,
          box: g.box,
          calib: g.calib
        });
        if (frames.length >= count) return done({ frames: frames });
        video.requestVideoFrameCallback(step);
      }
      video.requestVideoFrameCallback(step);
    });
  }

  function analyze(frames, calib) {
    var D = globalThis.VSDirection, U = globalThis.VSUnwrap, E = globalThis.VSEllipse;
    // FAIL-CLOSED: sem assinatura de cena na CALIBRAÇÃO não existe referência legítima.
    // Cair no primeiro frame aqui compararia a cena com ela mesma — o guard de NCC nunca
    // dispararia e o veredito *pareceria* totalmente guardado. Sem referência ⇒ ncc NaN
    // ⇒ `scene_ncc_low` ⇒ abstenção.
    var sceneRef = calib.sceneSignature ? Float64Array.from(calib.sceneSignature) : null;
    var profiles = frames.map(function (it) {
      var un = U.unwrapRotor(it.frame, it.calib);
      var sc = U.sceneSignature(it.frame, it.calib);
      if (!un.ok || !sc.ok) {
        return { chroma: new Float64Array(0), meanLuma: NaN, invalidFrac: 1, ncc: NaN };
      }
      return {
        tMs: it.wallMs,
        mediaTimeS: it.mediaTimeS,
        chroma: un.chroma,
        meanLuma: un.meanLuma,
        invalidFrac: Math.max(un.invalidFrac, sc.invalidFrac),
        ncc: sceneRef ? E.ncc(sceneRef, sc.signature) : NaN
      };
    });
    var res = D.analyzeWindow(profiles, calib);
    res.sceneReference = sceneRef ? 'calibration' : 'missing_calibration';
    return res;
  }

  function pushVerdict(rec) {
    chrome.storage.local.get(VERDICTS_KEY, function (o) {
      var list = (o && o[VERDICTS_KEY]) || [];
      list.push(rec);
      if (list.length > MAX_VERDICTS) list = list.slice(-MAX_VERDICTS);
      var patch = {}; patch[VERDICTS_KEY] = list;
      chrome.storage.local.set(patch);
    });
  }

  // Monta o `capture.json` do FORMATO_CAPTURA.md. A classe de evidência vem do que o
  // OPERADOR declarou no popup — nunca de um literal no código. Hardcodear `field` aqui
  // faria uma captura de bancada entrar no RESULTADO.md parecendo evidência de campo,
  // driblando o rebaixamento do service worker.
  function captureMeta(frames) {
    var cls = state.evidenceClass || 'fixture';
    return {
      format: 'vision_spike_capture',
      version: 1,
      evidence_class: cls,
      eligible_for_go_gates: cls === 'field',
      created_at: new Date().toISOString(),
      algorithm_sha: state.algorithmSha || null,
      config: {
        pairStride: globalThis.VSDirection.DEFAULTS.pairStride,
        emitFloor: globalThis.VSDirection.DEFAULTS.emitFloor,
        targetFrameIntervalS: globalThis.VSDirection.recommendedFrameIntervalS()
      },
      sensor_version: 'v3a-1',
      video: { width: frames[0].frame.width, height: frames[0].frame.height },
      calibration: frames[0].calib,
      truth: { direction: null, annotated_by: null, round_id: null },
      frames: frames.map(function (f, i) {
        return {
          file: null, offset: i, wallMs: f.wallMs, mediaTimeS: f.mediaTimeS,
          visibilityState: f.visibilityState
        };
      })
    };
  }

  function measure(reason) {
    if (state.busy || !state.running) return { ok: false, reason: state.busy ? 'busy' : 'not_running' };
    var video = pickVideo();
    if (!video) return { ok: false, reason: 'no_video_in_frame' };
    if (!state.calibration) return { ok: false, reason: 'no_calibration' };
    state.busy = true;
    state.stats.measurements++;
    captureBurst(video, state.calibration).then(function (r) {
      if (r.error || r.frames.length < CAPTURE_FRAMES) {
        pushVerdict({
          ts: Date.now(), reason: reason, direction: null, confidence: 0,
          guards: ['capture_failed:' + ((r.error && r.error.name) || 'short_burst')],
          frames: r.frames.length,
          evidence_class: state.evidenceClass, sensor_version: 'v3a-1',
          operator_direction: null, round_id: null
        });
        return;
      }
      var res = analyze(r.frames, state.calibration);
      if (res.direction) state.stats.emitted++; else state.stats.abstained++;
      if (state.keepCapture) {
        state.lastCapture = {
          meta: captureMeta(r.frames),
          frames: r.frames.map(function (f) { return f.frame.data; })
        };
      }
      pushVerdict({
        ts: Date.now(),
        reason: reason,
        direction: res.direction,          // null em QUALQUER abstenção
        confidence: res.confidence,
        confidence_kind: res.confidenceKind,
        guards: res.guards,
        scene_reference: res.sceneReference,   // 'calibration' | 'missing_calibration'
        deg_per_s: res.degreesPerSecond,
        alias_margin: res.aliasMargin,
        landmark_worst_deg: res.landmarkWorstDisagreementDeg,
        frames: r.frames.length,
        decimator: r.decimator,
        visibility: r.frames[0] && r.frames[0].visibilityState,
        evidence_class: state.evidenceClass,
        sensor_version: 'v3a-1',
        // Campos que SÓ o humano preenche (V3-B). Nascem null de propósito.
        operator_direction: null,
        round_id: null
      });
    }).catch(function (e) {
      pushVerdict({
        ts: Date.now(), reason: reason, direction: null, confidence: 0,
        guards: ['measure_crashed:' + (e && e.name)],
        evidence_class: state.evidenceClass, sensor_version: 'v3a-1'
      });
    }).finally(function () { state.busy = false; });
    return { ok: true, started: true };
  }

  /**
   * GRAVAÇÃO CONTÍNUA para o replay (E1). Uma medição tem 6 frames; o gate de sinal exige
   * captura de **≥250 frames** (`FORMATO_CAPTURA.md`). Sem este modo, o caminho documentado
   * produziria capturas de 6 frames, cujo teto aritmético é 16,7% — gate inalcançável com
   * a própria instrumentação.
   */
  function record(count) {
    count = Math.max(1, count || RECORD_DEFAULT_FRAMES);
    if (state.busy) return { ok: false, reason: 'busy' };
    var video = pickVideo();
    if (!video) return { ok: false, reason: 'no_video_in_frame' };
    if (!state.calibration) return { ok: false, reason: 'no_calibration' };
    state.busy = true;
    // Sem timeout curto: a gravação é longa por natureza (300 frames a ~11 fps ≈ 28 s).
    captureBurst(video, state.calibration, count, Math.max(20000, count * 400), RECORD_MAX_BYTES)
      .then(function (r) {
        if (!r.frames.length) return;
        var meta = captureMeta(r.frames);
        meta.record = {
          requested: count,
          obtained: r.frames.length,
          bytes: r.bytes,
          stopped_by: r.error ? r.error.name : null,
          budget_bytes: RECORD_MAX_BYTES,
          decimator: r.decimator
        };
        state.lastCapture = { meta: meta, frames: r.frames.map(function (f) { return f.frame.data; }) };
      })
      .finally(function () { state.busy = false; });
    return { ok: true, recording: count, budgetBytes: RECORD_MAX_BYTES };
  }

  function tick() {
    if (!state.running) return;
    var video = pickVideo();
    if (!video || !state.calibration) return;
    var g = grabRoi(video, state.calibration);
    if (!g || g.error) return;
    var grid = globalThis.VSUnwrap.roiLumaGrid(g.frame, g.calib, 12);
    var t = state.trigger.push(grid, performance.now());
    if (t.fired) { state.stats.triggers++; measure('motion'); }
  }

  function start(opts) {
    if (state.running) return { ok: false, reason: 'already_running' };
    if (!state.calibration) return { ok: false, reason: 'no_calibration' };
    if (!pickVideo()) return { ok: false, reason: 'no_video_in_frame' };
    state.keepCapture = !!(opts && opts.keepCapture);
    state.trigger = globalThis.VSMotionTrigger.createMotionTrigger();
    state.busy = false;                 // recupera de um burst que nunca liquidou
    state.running = true;
    state.timer = setInterval(tick, TRIGGER_PERIOD_MS);
    return { ok: true, targetFrameIntervalS: globalThis.VSDirection.recommendedFrameIntervalS() };
  }

  function stop() {
    state.running = false;
    state.busy = false;                 // idem: `stop`+`start` tem de recuperar o coletor
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    return { ok: true, stats: state.stats };
  }

  function loadSettings(cb) {
    chrome.storage.local.get([CALIB_KEY, CLASS_KEY, SHA_KEY], function (o) {
      state.calibration = (o && o[CALIB_KEY]) || null;
      state.evidenceClass = (o && o[CLASS_KEY]) || 'fixture';
      state.algorithmSha = (o && o[SHA_KEY]) || null;
      if (cb) cb(state.calibration);
    });
  }

  chrome.storage.onChanged.addListener(function (ch, area) {
    if (area !== 'local') return;
    if (ch[CLASS_KEY]) state.evidenceClass = ch[CLASS_KEY].newValue || 'fixture';
    if (ch[CALIB_KEY]) state.calibration = ch[CALIB_KEY].newValue || null;
    if (ch[SHA_KEY]) state.algorithmSha = ch[SHA_KEY].newValue || null;
  });

  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (!msg || msg.type !== 'vs_collector') return;
    // O content script roda em TODOS os frames. Se este frame não tem `<video>`, ele NÃO
    // responde: `chrome.tabs.sendMessage` entrega ao popup apenas a PRIMEIRA resposta, e
    // um `{ok:false,'no_video_in_frame'}` do top frame mascararia o iframe da mesa que
    // iniciou corretamente (e vice-versa).
    if (!pickVideo() && msg.action !== 'ping') return false;
    if (msg.action === 'start') { loadSettings(function () { sendResponse(start(msg.opts)); }); return true; }
    if (msg.action === 'stop') { sendResponse(stop()); return true; }
    if (msg.action === 'measure') { sendResponse(measure('manual')); return true; }
    if (msg.action === 'record') { loadSettings(function () { sendResponse(record(msg.count)); }); return true; }
    if (msg.action === 'status') {
      sendResponse({
        running: state.running,
        busy: state.busy,
        hasCalibration: !!state.calibration,
        hasVideo: true,
        hasCapture: !!state.lastCapture,
        captureFrames: state.lastCapture ? state.lastCapture.frames.length : 0,
        evidenceClass: state.evidenceClass,
        stats: state.stats
      });
      return true;
    }
    // Snapshot 1:1 nas coordenadas INTRÍNSECAS do vídeo, para a calibração.
    // O operador clica sobre ESTE bitmap, não sobre o vídeo renderizado: assim
    // `object-fit`, CSS, letterbox e `devicePixelRatio` não entram na conta.
    if (msg.action === 'snapshot') {
      var v = pickVideo();
      if (!v || !(v.videoWidth > 0)) { sendResponse({ ok: false, reason: 'no_video_in_frame' }); return true; }
      try {
        var ctx = ensureCanvas(v.videoWidth, v.videoHeight);
        ctx.drawImage(v, 0, 0, v.videoWidth, v.videoHeight);
        _canvas.convertToBlob({ type: 'image/png' }).then(function (blob) {
          var fr = new FileReader();
          fr.onload = function () {
            sendResponse({ ok: true, width: v.videoWidth, height: v.videoHeight, dataUrl: fr.result });
          };
          fr.onerror = function () { sendResponse({ ok: false, reason: 'reader_failed' }); };
          fr.readAsDataURL(blob);
        }).catch(function (e) {
          sendResponse({ ok: false, reason: e && e.name, message: e && e.message });
        });
      } catch (e) {
        sendResponse({ ok: false, reason: e && e.name, message: e && e.message, tainted: e && e.name === 'SecurityError' });
      }
      return true;
    }
    return false;
  });

  // Exportação da captura: streaming por PORT com ACK, backpressure e RETOMADA
  // (`lib/export_stream.js`). O destinatário é `probe/export.html` — uma PÁGINA de
  // extensão, não o popup: o popup fecha ao primeiro clique fora dele e levava junto uma
  // transferência de ~100 MB, e com ela uma coleta de campo inteira.
  // Sai da máquina? NÃO: o destino é um `download` do próprio navegador, em disco local.
  // O frame SEM captura apenas desconecta — se ele respondesse "não tenho", o destinatário
  // (que recebe de todos os frames) abortaria o export do iframe que de fato gravou.
  chrome.runtime.onConnect.addListener(function (port) {
    if (port.name !== 'vs_export') return;
    if (!state.lastCapture) { port.disconnect(); return; }
    var cap = state.lastCapture;
    var sender = globalThis.VSExportStream.createSender({
      frames: cap.frames,
      meta: cap.meta,
      chunkFrames: 1,
      window: 2,
      post: function (m) {
        try { port.postMessage(m); } catch (e) { /* port morto: o destinatário retoma */ }
      }
    });
    port.onMessage.addListener(function (m) {
      if (!m) return;
      if (m.type === 'start' || m.type === 'resume') sender.start(m.from || 0);
      else if (m.type === 'ack') sender.onAck(m.to);
    });
  });

  chrome.storage.local.get(POLICY_KEY, function (o) {
    if (o && o[POLICY_KEY] === 'on') loadSettings();
  });

  globalThis.VSCollector = {
    start: start, stop: stop, measure: measure, record: record,
    grabRoi: grabRoi, roiBox: roiBox, analyze: analyze, captureMeta: captureMeta,
    state: state
  };
}());
