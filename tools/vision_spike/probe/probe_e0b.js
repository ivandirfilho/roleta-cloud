// SPR-V3 · vision_spike/probe/probe_e0b.js — PROBE E0b: COBERTURA (aba oculta / minimizada).
//
// ⚠️ INSTRUMENTO ENTREGUE RODÁVEL; a MEDIÇÃO em mesa real é V3-B ⚠️
// Em V3-A ele é testado contra `probe/fixture_video.html` (um `<video>` local). Os campos
// de E0b no RESULTADO.md ficam VAZIOS até a coleta com o operador.
//
// A pergunta (§10.6-2, decisão que exige humano):
//   `captureVisibleTab` é CEGO com a janela minimizada — isso é fato conhecido do repo
//   (`background.js`, captura falha e é engolida em silêncio). Mas o `<video>` **pode não
//   ser**. NÃO PRESUMA. Este instrumento conta callbacks de `requestVideoFrameCallback`
//   por segundo e grava a série, anotando `visibilityState` e `hasFocus` em cada amostra.
//
// Réguas separadas (senão o spike produz um número bonito e errado):
//   • callbacks/s  → wall-clock (`performance.now`);
//   • avanço do stream → `metadata.mediaTime`;
//   • frames que o compositor apresentou → `metadata.presentedFrames`.
//
// Default-OFF, como todo comportamento novo neste repo.
(function () {
  'use strict';

  var POLICY_KEY = 'vsProbePolicy';
  var FLUSH_MS = 2000;
  var running = false;
  var meter = null;
  var handle = null;
  var video = null;
  var flushTimer = null;

  function pickVideo() {
    var vids = Array.prototype.slice.call(document.querySelectorAll('video'));
    if (!vids.length) return null;
    return vids.reduce(function (a, b) {
      return (b.videoWidth * b.videoHeight) > (a.videoWidth * a.videoHeight) ? b : a;
    }, vids[0]);
  }

  function onFrame(now, metadata) {
    meter.record({
      wallMs: performance.now(),
      mediaTime: metadata && metadata.mediaTime,
      presentedFrames: metadata && metadata.presentedFrames,
      visibilityState: document.visibilityState,
      hasFocus: (function () { try { return document.hasFocus(); } catch (e) { return null; } })()
    });
    if (running && video && video.requestVideoFrameCallback) {
      handle = video.requestVideoFrameCallback(onFrame);
    }
  }

  function flush(final) {
    if (!meter) return;
    var s = meter.summary();
    var env = globalThis.VSEvidence.envelope('E0b', globalThis.VSEvidence.CLASS.FIELD, {
      final: !!final,
      summary: s,
      // A série completa só viaja no registro FINAL. Mandá-la a cada 2 s encheria o ring
      // de evidência com 360 cópias crescentes e os primeiros minutos seriam os primeiros
      // a ser descartados — exatamente os que interessam (a fase "aba visível" é a
      // referência contra a qual as outras três são lidas).
      series: final ? meter.series() : undefined,
      series_tail: final ? undefined : meter.series().slice(-15),
      note: 'callbacks/s medidos em wall-clock; avanco do stream em mediaTime; ' +
        'presentedFrames vem do compositor. Nao comparar as tres reguas entre si. ' +
        'byPhase traz uma linha por fase do protocolo, INCLUSIVE as silenciosas ' +
        '(callbacks 0 com duracao > 0 e um resultado, nao a ausencia de um).'
    });
    try { chrome.runtime.sendMessage({ type: 'vs_evidence', evidence: env }); } catch (e) { }
  }

  function start(phaseName) {
    if (running) return { ok: false, reason: 'already_running' };
    video = pickVideo();
    if (!video) return { ok: false, reason: 'no_video_in_frame' };
    if (typeof video.requestVideoFrameCallback !== 'function') {
      // Resultado NEGATIVO é resultado: sem rVFC o desenho do sensor cai por completo.
      try {
        chrome.runtime.sendMessage({
          type: 'vs_evidence',
          evidence: globalThis.VSEvidence.envelope('E0b', globalThis.VSEvidence.CLASS.FIELD, {
            verdict: 'rvfc_unsupported'
          })
        });
      } catch (e) { }
      return { ok: false, reason: 'rvfc_unsupported' };
    }
    meter = globalThis.VSRvfcMeter.createFrameRateMeter({ bucketMs: 1000, maxBuckets: 7200 });
    meter.markPhase(phaseName || 'A_visivel', performance.now());
    running = true;
    handle = video.requestVideoFrameCallback(onFrame);
    flushTimer = setInterval(flush, FLUSH_MS);
    return { ok: true, phase: phaseName || 'A_visivel' };
  }

  /**
   * Marca a fronteira entre as fases do protocolo (visível → outra aba → minimizada →
   * retorno). É marca EXPLÍCITA e não inferência: se o player parar de entregar frames com
   * a janela minimizada, não chega amostra nenhuma — e uma fase inferida das amostras
   * simplesmente não existiria. "0 callbacks em 180 s" é o achado mais importante que este
   * instrumento pode produzir.
   */
  function phase(name) {
    if (!running || !meter) return { ok: false, reason: 'not_running' };
    meter.markPhase(name, performance.now());
    return { ok: true, phase: name, phases: meter.phases() };
  }

  function stop() {
    running = false;
    if (handle && video && video.cancelVideoFrameCallback) {
      try { video.cancelVideoFrameCallback(handle); } catch (e) { }
    }
    if (flushTimer) { clearInterval(flushTimer); flushTimer = null; }
    flush(true);
    var s = meter ? meter.summary() : null;
    meter = null;
    return { ok: true, summary: s };
  }

  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (!msg || msg.type !== 'vs_e0b') return;
    // Frames sem `<video>` NÃO respondem: `chrome.tabs.sendMessage` entrega ao popup
    // apenas a PRIMEIRA resposta, e o top frame (que nunca tem o vídeo da mesa, porque
    // ele vive no iframe) mascararia o resultado do frame que importa.
    if (!pickVideo()) return false;
    if (msg.action === 'start') sendResponse(start(msg.phase));
    else if (msg.action === 'stop') sendResponse(stop());
    else if (msg.action === 'phase') sendResponse(phase(msg.phase));
    else if (msg.action === 'status') {
      sendResponse({
        running: running,
        summary: meter ? meter.summary() : null,
        phases: meter ? meter.phases() : null
      });
    }
    return true;
  });

  chrome.storage.local.get(POLICY_KEY, function (o) {
    if (o && o[POLICY_KEY] === 'on' && o.vsAutoStartE0b === true) start();
  });

  globalThis.VSProbeE0b = {
    start: start, stop: stop, phase: phase,
    isRunning: function () { return running; }
  };
}());
