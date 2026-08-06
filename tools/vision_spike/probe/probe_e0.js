// SPR-V3 · vision_spike/probe/probe_e0.js — PROBE E0: acesso, entrega e TAINT.
//
// ⚠️ ESTA PROBE É ENTREGUE RODÁVEL; a EXECUÇÃO em mesa real é V3-B ⚠️
// Em V3-A ela existe, roda contra `probe/fixture_video.html` e grava. Os campos de E0 no
// RESULTADO.md ficam VAZIOS até um humano rodá-la na mesa (§10.6, fronteira do brief).
//
// Perguntas que ela responde POR ESCRITO, com evidência bruta:
//   1. existe `<video>` neste frame? (roda em `all_frames`, como o `deal_capture.js`)
//   2. a entrega é `srcObject` (MediaStream) ou `src` (`blob:` / URL direta)?
//   3. `createImageBitmap` + `OffscreenCanvas` + `getImageData` funcionam SEM `SecurityError`?
//
// Honestidade declarada (a crítica cobrou isto):
//   • `blob:` **NÃO PROVA MSE**. Do mundo isolado do content script não dá para inspecionar
//     o `MediaSource`. Reportamos `delivery: 'blob_url'` e `mse_confirmed: null` — "não sei"
//     é uma resposta válida; "MSE" seria evidência inventada.
//   • O taint é medido num ÚNICO try/catch: é exatamente o fallback limpo que o desenho
//     prevê (HLS cross-origin sem CORS ⇒ `SecurityError` ⇒ caminho de vídeo morre).
//
// Default-OFF: sem `vsProbePolicy === 'on'` no storage, este arquivo não faz NADA.
(function () {
  'use strict';

  var POLICY_KEY = 'vsProbePolicy';
  var started = false;

  function frameLabel() {
    try {
      return {
        is_top: window.top === window,
        origin: location.origin,
        path_depth: location.pathname.split('/').length
      };
    } catch (e) {
      return { is_top: null, origin: 'cross-origin', path_depth: null };
    }
  }

  function classifyDelivery(v) {
    try {
      if (v.srcObject) {
        var so = v.srcObject;
        var kind = (typeof MediaStream !== 'undefined' && so instanceof MediaStream)
          ? 'mediastream' : 'srcobject_other';
        var tracks = [];
        if (kind === 'mediastream' && so.getTracks) {
          tracks = so.getTracks().map(function (t) {
            var s = {};
            try { s = t.getSettings ? t.getSettings() : {}; } catch (e) { s = {}; }
            return {
              kind: t.kind, readyState: t.readyState, muted: t.muted,
              width: s.width || null, height: s.height || null, frameRate: s.frameRate || null
            };
          });
        }
        return {
          delivery: kind,
          // MediaStream é COMPATÍVEL com WebRTC, mas também com captureStream() local.
          webrtc_confirmed: null,
          // `srcObject` que NÃO é MediaStream é justamente o caso que não sabemos
          // classificar (MediaSource pode ser anexado por srcObject em navegadores
          // recentes). Afirmar `false` aqui seria inventar; `null` = "não sei".
          mse_confirmed: kind === 'mediastream' ? false : null,
          tracks: tracks,
          src_scheme: null
        };
      }
      var src = v.currentSrc || v.src || '';
      var scheme = src.split(':')[0] || '';
      return {
        delivery: scheme === 'blob' ? 'blob_url' : (scheme ? 'url_' + scheme : 'none'),
        webrtc_confirmed: false,
        // blob: pode ser MSE OU um Blob estático. Do mundo isolado não dá para distinguir.
        mse_confirmed: scheme === 'blob' ? null : false,
        tracks: [],
        src_scheme: scheme || null
      };
    } catch (e) {
      return { delivery: 'error', error: String(e && e.message), mse_confirmed: null };
    }
  }

  // O teste de taint inteiro em UM try/catch — é este o "fallback limpo" do desenho.
  function taintProbe(v) {
    return Promise.resolve().then(function () {
      return createImageBitmap(v);
    }).then(function (bmp) {
      var oc = new OffscreenCanvas(bmp.width || 2, bmp.height || 2);
      var ctx = oc.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(bmp, 0, 0);
      var px = ctx.getImageData(0, 0, 1, 1);
      if (bmp.close) bmp.close();
      return {
        pixel_read_ok: true,
        tainted: false,
        bitmap: { width: bmp.width, height: bmp.height },
        sample_rgba: Array.prototype.slice.call(px.data),
        path: 'createImageBitmap+OffscreenCanvas+getImageData',
        error: null
      };
    }).catch(function (err) {
      return {
        pixel_read_ok: false,
        // SecurityError == canvas manchado. Qualquer outro erro é OUTRA coisa (e é
        // registrado como tal: rotular tudo de "taint" mataria o caminho por engano).
        tainted: !!(err && err.name === 'SecurityError'),
        path: 'createImageBitmap+OffscreenCanvas+getImageData',
        error: { name: err && err.name, message: err && err.message }
      };
    });
  }

  function describeVideo(v, i) {
    return {
      index: i,
      video_width: v.videoWidth,
      video_height: v.videoHeight,
      client_width: v.clientWidth,
      client_height: v.clientHeight,
      ready_state: v.readyState,
      network_state: v.networkState,
      paused: v.paused,
      muted: v.muted,
      current_time: v.currentTime,
      duration: (isFinite(v.duration) ? v.duration : null),
      rvfc_supported: typeof v.requestVideoFrameCallback === 'function',
      device_pixel_ratio: window.devicePixelRatio || 1,
      delivery: classifyDelivery(v)
    };
  }

  function runE0() {
    var vids = Array.prototype.slice.call(document.querySelectorAll('video'));
    var base = {
      frame: frameLabel(),
      video_count: vids.length,
      user_agent_data: (navigator.userAgentData && navigator.userAgentData.brands) || null,
      offscreen_canvas_supported: typeof OffscreenCanvas === 'function',
      create_image_bitmap_supported: typeof createImageBitmap === 'function'
    };
    if (!vids.length) {
      return Promise.resolve(Object.assign({ videos: [], verdict: 'no_video_in_frame' }, base));
    }
    var described = vids.map(describeVideo);
    // Mede taint no maior vídeo (o da mesa; os outros costumam ser thumbnails do lobby).
    var target = described.reduce(function (a, b) {
      return (b.video_width * b.video_height) > (a.video_width * a.video_height) ? b : a;
    }, described[0]);
    return taintProbe(vids[target.index]).then(function (taint) {
      return Object.assign({
        videos: described,
        measured_index: target.index,
        taint: taint,
        verdict: taint.pixel_read_ok ? 'pixels_readable'
          : (taint.tainted ? 'tainted_security_error' : 'read_failed_other')
      }, base);
    });
  }

  function report(payload) {
    var env = globalThis.VSEvidence.envelope('E0', globalThis.VSEvidence.CLASS.FIELD, payload);
    // A CLASSE final é decidida pelo service worker a partir do que o operador declarou no
    // popup: `field` numa sessão `fixture` é REBAIXADO lá. Rebaixar é seguro, promover não.
    try {
      chrome.runtime.sendMessage({ type: 'vs_evidence', evidence: env }, function () {
        // Sem retry: se o SW não recebeu, a evidência fica no console deste frame e o
        // operador rearma a policy no popup (o que dispara a probe de novo).
        if (chrome.runtime.lastError) {
          console.warn('[SPR-V3 E0] evidencia nao chegou ao SW:', chrome.runtime.lastError.message);
        }
      });
    } catch (e) {
      console.warn('[SPR-V3 E0] sendMessage falhou:', e && e.message);
    }
    console.log('[SPR-V3 E0]', env);
  }

  function start() {
    if (started) return;
    started = true;
    runE0().then(report).catch(function (e) {
      report({ error: String(e && e.message), verdict: 'probe_crashed' });
    });
  }

  function boot() {
    chrome.storage.local.get(POLICY_KEY, function (o) {
      if (o && o[POLICY_KEY] === 'on') start();
    });
    // Re-armar a policy re-dispara a probe: é o caminho de retry do operador.
    chrome.storage.onChanged.addListener(function (ch, area) {
      if (area !== 'local' || !ch[POLICY_KEY]) return;
      if (ch[POLICY_KEY].newValue === 'off') started = false;
      else if (ch[POLICY_KEY].newValue === 'on') start();
    });
  }

  globalThis.VSProbeE0 = { runE0: runE0, classifyDelivery: classifyDelivery, taintProbe: taintProbe };
  boot();
}());
