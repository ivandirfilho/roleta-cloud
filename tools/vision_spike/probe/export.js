// SPR-V3 · vision_spike/probe/export.js — destinatário DURÁVEL da captura.
//
// Toda a lógica de acumular, confirmar e saber de onde recomeçar vive em
// `lib/export_stream.js` (módulo puro, testado em `node --test`). Aqui só há o encanamento
// do Chrome: abrir o port, empurrar mensagens para o assembler, devolver os acks e vigiar
// o stall — com o relógio **rearmado a cada mensagem**, inclusive depois do `meta`.
'use strict';

const $ = (id) => document.getElementById(id);
const STALL_MS = 8000;

let assembler = null;
let port = null;
let stallTimer = null;

function log(s) { $('out').textContent = s; $('out').style.color = '#e6e6e6'; }

/** Erro SEMPRE na tela. Um export quebrado que só reclama no console vira arquivo ruim. */
function fail(s) {
  $('out').textContent = '❌ ' + s;
  $('out').style.color = '#ff8b8b';
  $('save').disabled = true;
  console.error('[SPR-V3 export]', s);
}

function progressUi() {
  const p = assembler ? assembler.progress() : null;
  if (!p || !p.expected) return;
  const pct = Math.round((p.received / p.expected) * 100);
  $('fill').style.width = pct + '%';
  $('pct').textContent = pct + '%';
  if (p.rejected) {
    fail(`${p.rejected} frame(s) recusado(s) — ${p.rejectedDetail.map((r) => `#${r.index}: ${r.reason}`).join(' · ')}`);
    $('resume').disabled = false;
    return;
  }
  log(`recebidos ${p.received}/${p.expected} frames` +
    (p.missingFrom === null ? ' · completo' : ` · próximo em falta: ${p.missingFrom}`));
  $('save').disabled = !p.complete;
  $('resume').disabled = p.complete;
}

function armStall() {
  clearTimeout(stallTimer);
  stallTimer = setTimeout(() => {
    if (!assembler) return;
    if (assembler.isStalled(STALL_MS)) {
      const p = assembler.progress();
      log(`transferência travada em ${p.received}/${p.expected ?? '?'} frames. ` +
        `Clique em Retomar (continua do frame ${p.missingFrom ?? 0}).`);
      $('resume').disabled = false;
    }
  }, STALL_MS + 200);
}

async function targetTabId() {
  const s = await chrome.storage.local.get('vsTargetTabId');
  return s.vsTargetTabId;
}

async function connect(from) {
  const tabId = await targetTabId();
  if (tabId == null) return log('aba da mesa desconhecida — abra esta tela pelo popup.');
  if (!assembler) assembler = VSExportStream.createAssembler({ stallMs: STALL_MS });

  try { if (port) port.disconnect(); } catch (_) { }
  port = chrome.tabs.connect(tabId, { name: 'vs_export' });
  assembler.touch();
  armStall();

  port.onDisconnect.addListener(() => {
    const p = assembler.progress();
    if (!p.complete) {
      log(`conexão caiu em ${p.received}/${p.expected ?? '?'} frames. ` +
        `Clique em Retomar (continua do frame ${p.missingFrom ?? 0}).`);
      $('resume').disabled = false;
    }
  });

  port.onMessage.addListener((m) => {
    let replies = [];
    try {
      replies = assembler.handle(m);
    } catch (e) {
      // Erro de protocolo (wire desconhecido, lote malformado) tem de aparecer NA TELA.
      // Só no console, o operador salvaria um arquivo quebrado achando que deu certo.
      fail('erro no protocolo de transferência: ' + e.message);
      try { port.disconnect(); } catch (_) { }
      return;
    }
    for (const r of replies) {
      try { port.postMessage(r); } catch (_) { /* caiu: o botão Retomar resolve */ }
    }
    armStall();
    progressUi();
  });

  port.postMessage({ type: from ? 'resume' : 'start', from: from || 0 });
  log('conectado, aguardando meta…');
}

$('start').onclick = () => { assembler = null; connect(0); };
$('resume').onclick = () => {
  const from = assembler ? (assembler.missingFrom() ?? 0) : 0;
  connect(from);
};

$('save').onclick = () => {
  let out;
  try {
    out = assembler.assemble();
  } catch (e) {
    return fail('montagem recusada: ' + e.message + ' — NADA foi salvo.');
  }
  if (!out.bytes.length) return fail('montagem resultou em 0 bytes — NADA foi salvo.');
  try {
    const meta = { ...out.meta, data_file: 'frames.bin' };
    meta.frames = meta.frames.map((f, i) => ({ ...f, file: null, offset: i }));
    saveBlob('capture.json', new Blob([JSON.stringify(meta, null, 2)], { type: 'application/json' }));
    saveBlob('frames.bin', new Blob([out.bytes], { type: 'application/octet-stream' }));
    log(`exportado: ${out.frameCount} frames · ${(out.bytes.length / 1e6).toFixed(1)} MB · ` +
      `${out.stride} bytes/frame · evidence_class=${out.meta.evidence_class}` +
      (out.frameCount < 250 ? '\n⚠️ < 250 frames: insuficiente para o gate de sinal (98%).' : ''));
  } catch (e) {
    fail('falha ao salvar: ' + e.message);
  }
};

function saveBlob(name, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 8000);
}
