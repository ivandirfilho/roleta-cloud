// SPR-V3 · vision_spike/probe/popup.js — console local do spike.
//
// Downloads são feitos com `URL.createObjectURL` + `<a download>` a partir da PÁGINA da
// extensão: não é preciso a permissão `downloads`, e o arquivo vai para o disco do próprio
// operador. Nada é enviado a lugar nenhum.
'use strict';

const $ = (id) => document.getElementById(id);

function save(name, blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

function saveJson(name, obj) {
  save(name, new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }));
}

async function activeTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.id != null) {
    // A aba da mesa é a que estava ativa quando o popup abriu. Guardamos porque a tela de
    // calibração vira ELA a aba ativa depois de aberta (`chrome.tabs.create`), e um
    // `tabs.query` de dentro dela devolveria a própria página da extensão.
    await chrome.storage.local.set({ vsTargetTabId: tab.id });
  }
  return tab && tab.id;
}

// A mensagem vai para todos os frames da aba, mas apenas o frame que TEM o `<video>`
// responde (os demais devolvem `false` no listener) — senão a primeira resposta a chegar
// seria a do top frame, que nunca tem o vídeo da mesa.
async function sendToFrames(msg) {
  const tabId = await activeTabId();
  if (tabId == null) return { error: 'no_tab' };
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, msg, (resp) => {
      if (chrome.runtime.lastError) {
        resolve({
          error: chrome.runtime.lastError.message,
          hint: 'nenhum frame desta aba tem <video> (ou as probes estão desarmadas)'
        });
      } else resolve(resp || { error: 'no_response' });
    });
  });
}

async function refreshPolicy() {
  const s = await chrome.storage.local.get(['vsProbePolicy', 'vsEvidenceClass', 'vsEvidence', 'vsVerdicts']);
  $('policy').textContent = `policy=${s.vsProbePolicy || 'off'} · classe=${s.vsEvidenceClass || 'fixture'}`;
  $('policyOn').classList.toggle('on', s.vsProbePolicy === 'on');
  const cls = s.vsEvidenceClass || 'fixture';
  const radio = document.querySelector(`input[name=cls][value=${cls}]`);
  if (radio) radio.checked = true;
  $('evOut').textContent =
    `evidencias=${(s.vsEvidence || []).length}  vereditos=${(s.vsVerdicts || []).length}\n` +
    ((s.vsEvidence || []).slice(-2).map(e => `${e.kind} ${e.evidence_class} ${e.payload && e.payload.verdict || ''}`).join('\n') || '—');
}

$('policyOn').onclick = async () => { await chrome.storage.local.set({ vsProbePolicy: 'on' }); refreshPolicy(); };
$('policyOff').onclick = async () => { await chrome.storage.local.set({ vsProbePolicy: 'off' }); refreshPolicy(); };
document.querySelectorAll('input[name=cls]').forEach(r => {
  r.onchange = async () => { await chrome.storage.local.set({ vsEvidenceClass: r.value }); refreshPolicy(); };
});

$('e0bStart').onclick = async () => { $('e0bOut').textContent = JSON.stringify(await sendToFrames({ type: 'vs_e0b', action: 'start' }), null, 1); };
$('e0bStop').onclick = async () => { $('e0bOut').textContent = JSON.stringify(await sendToFrames({ type: 'vs_e0b', action: 'stop' }), null, 1); };
$('e0bStatus').onclick = async () => { $('e0bOut').textContent = JSON.stringify(await sendToFrames({ type: 'vs_e0b', action: 'status' }), null, 1); };

$('calib').onclick = () => chrome.tabs.create({ url: chrome.runtime.getURL('probe/calibrate.html') });
$('colStart').onclick = async () => {
  $('colOut').textContent = JSON.stringify(
    await sendToFrames({ type: 'vs_collector', action: 'start', opts: { keepCapture: $('keepCapture').checked } }), null, 1);
};
$('colStop').onclick = async () => { $('colOut').textContent = JSON.stringify(await sendToFrames({ type: 'vs_collector', action: 'stop' }), null, 1); };
$('colMeasure').onclick = async () => { $('colOut').textContent = JSON.stringify(await sendToFrames({ type: 'vs_collector', action: 'measure' }), null, 1); };
$('colStatus').onclick = async () => { $('colOut').textContent = JSON.stringify(await sendToFrames({ type: 'vs_collector', action: 'status' }), null, 1); };
// Gravação contínua: o gate de sinal exige captura de >=250 frames; uma medição tem 6.
$('colRecord').onclick = async () => {
  const n = parseInt($('recordFrames').value, 10) || 300;
  $('colOut').textContent = 'gravando ' + n + ' frames decimados (~' + Math.round(n * 0.1) +
    ' s)… use "Status" para acompanhar e depois "Baixar captura".';
  const r = await sendToFrames({ type: 'vs_collector', action: 'record', count: n });
  $('colOut').textContent = JSON.stringify(r, null, 1);
};

$('dlEvidence').onclick = async () => {
  const s = await chrome.storage.local.get('vsEvidence');
  saveJson(`vs_e0_evidence_${Date.now()}.json`, s.vsEvidence || []);
};
$('dlVerdicts').onclick = async () => {
  const s = await chrome.storage.local.get('vsVerdicts');
  saveJson(`vs_verdicts_${Date.now()}.json`, s.vsVerdicts || []);
};
$('clear').onclick = async () => {
  await chrome.storage.local.remove(['vsEvidence', 'vsVerdicts']);
  refreshPolicy();
};

// Captura → dois arquivos que o `replay.js` lê direto (ver FORMATO_CAPTURA.md):
// `capture.json` (com `data_file`) e `frames.bin` (RGBA concatenado, stride = w*h*4).
// O port é aberto contra TODOS os frames da aba; os que não têm captura apenas
// desconectam. Por isso a ausência de captura é detectada por TIMEOUT, e não pela primeira
// desconexão — senão o top frame (que nunca grava) abortaria o export do iframe da mesa.
$('dlCapture').onclick = async () => {
  const tabId = await activeTabId();
  if (tabId == null) return;
  const port = chrome.tabs.connect(tabId, { name: 'vs_export' });
  const chunks = [];
  let meta = null;
  let finished = false;
  const timeout = setTimeout(() => {
    if (finished || meta) return;
    finished = true;
    $('colOut').textContent = 'nenhuma captura guardada neste frame ' +
      '(marque "guardar captura" ou use "Gravar p/ replay" antes)';
    try { port.disconnect(); } catch (_) { }
  }, 4000);

  port.onMessage.addListener((m) => {
    if (finished) return;
    if (m.type === 'meta') { meta = m.meta; return; }
    if (m.type === 'frame') { chunks[m.index] = new Uint8Array(m.data); return; }
    if (m.type === 'end') {
      finished = true;
      clearTimeout(timeout);
      const total = chunks.reduce((a, c) => a + (c ? c.length : 0), 0);
      const buf = new Uint8Array(total);
      let off = 0;
      for (const c of chunks) { if (c) { buf.set(c, off); off += c.length; } }
      meta.data_file = 'frames.bin';
      meta.frames = meta.frames.map((f, i) => ({ ...f, file: null, offset: i }));
      saveJson('capture.json', meta);
      save('frames.bin', new Blob([buf], { type: 'application/octet-stream' }));
      $('colOut').textContent = `captura exportada: ${chunks.length} frames, ` +
        `${(total / 1e6).toFixed(1)} MB, evidence_class=${meta.evidence_class}` +
        (chunks.length < 250 ? '\n⚠️ < 250 frames: insuficiente para o gate de sinal (98%).' : '');
      port.disconnect();
    }
  });
};

refreshPolicy();
