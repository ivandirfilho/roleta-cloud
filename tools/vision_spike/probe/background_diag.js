// SPR-V3 · vision_spike/probe/background_diag.js — service worker da extensão de DIAGNÓSTICO.
//
// Faz duas coisas: acumular a evidência que as probes mandam (ring em
// `chrome.storage.local`) e calcular o `algorithm_sha` que vai dentro de cada captura.
// Não captura tela, não pede permissão nova, não fala com o servidor. `captureVisibleTab`
// NÃO é usado nem aqui nem em lugar nenhum do spike — ele divide bucket de quota GLOBAL
// com o OCR da extensão de produção (2 chamadas/s por extensão) e é cego com a janela
// minimizada. Diagnóstico manual, nunca fonte.
'use strict';

importScripts('../lib/algo_sha.js');

const EVIDENCE_KEY = 'vsEvidence';
const POLICY_KEY = 'vsProbePolicy';
const CLASS_KEY = 'vsEvidenceClass';
const SHA_KEY = 'vsAlgorithmSha';
const MAX_EVIDENCE = 300;

// Hierarquia de confiança. Índice MAIOR afirma mais sobre o mundo.
const CLASS_RANK = { synthetic: 0, fixture: 1, field: 2 };

// Rebaixar é seguro; PROMOVER não. O operador declara no popup se a sessão é `fixture`
// (bancada) ou `field` (mesa real); tudo que chegar afirmando MAIS que a sessão declarada
// é reduzido — e nada é jamais elevado (um envelope `synthetic` continua `synthetic`
// mesmo numa sessão `field`).
async function normalizeClass(env) {
  const store = await chrome.storage.local.get(CLASS_KEY);
  const declared = store[CLASS_KEY] || 'fixture';
  const incoming = env.evidence_class || 'fixture';
  const rankIn = CLASS_RANK[incoming] === undefined ? 0 : CLASS_RANK[incoming];
  const rankDeclared = CLASS_RANK[declared] === undefined ? 0 : CLASS_RANK[declared];
  if (rankIn <= rankDeclared) return env;
  return Object.assign({}, env, {
    evidence_class: declared,
    eligible_for_go_gates: declared === 'field',
    downgraded_from: incoming
  });
}

// Fila serial: com `all_frames: true` CADA frame envia sua evidência E0 mais ou menos ao
// mesmo tempo. Sem serializar, duas mensagens leem a mesma lista e a segunda gravação
// apaga a primeira — e o registro perdido seria justamente o do iframe que tem o `<video>`,
// que é a resposta da Etapa 1 do protocolo.
let writeQueue = Promise.resolve();

async function appendEvidence(env) {
  const store = await chrome.storage.local.get(EVIDENCE_KEY);
  let list = store[EVIDENCE_KEY] || [];
  list.push(env);
  if (list.length > MAX_EVIDENCE) list = list.slice(-MAX_EVIDENCE);
  await chrome.storage.local.set({ [EVIDENCE_KEY]: list });
  return list.length;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== 'vs_evidence') return;
  writeQueue = writeQueue.then(async () => {
    const env = await normalizeClass(msg.evidence);
    env.frame_id = sender.frameId;
    env.tab_id = sender.tab && sender.tab.id;
    const stored = await appendEvidence(env);
    sendResponse({ ok: true, stored });
  }).catch((e) => {
    console.warn('[SPR-V3] falha ao gravar evidencia:', e && e.message);
    try { sendResponse({ ok: false, error: String(e && e.message) }); } catch (_) { }
  });
  return true;
});

/**
 * `algorithm_sha` pela MESMA receita do `replay.js` (`lib/algo_sha.js`): caminho + bytes de
 * cada arquivo do algoritmo, SHA-256, 16 hex. Um número de gate sem o SHA do algoritmo que
 * o produziu não é reproduzível; e duas receitas diferentes produziriam um aviso permanente
 * de divergência que todo mundo aprenderia a ignorar.
 */
async function computeAlgorithmSha() {
  const files = {};
  for (const rel of VSAlgoSha.ALGORITHM_FILES) {
    const res = await fetch(chrome.runtime.getURL(rel));
    files[rel] = new Uint8Array(await res.arrayBuffer());
  }
  const bytes = VSAlgoSha.canonicalBytes((rel) => files[rel]);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  const hex = Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0')).join('');
  return hex.slice(0, VSAlgoSha.SHA_LENGTH);
}

async function bootstrap() {
  const cur = await chrome.storage.local.get([POLICY_KEY, CLASS_KEY]);
  // Default-OFF, como todo comportamento novo neste repo.
  if (cur[POLICY_KEY] == null) await chrome.storage.local.set({ [POLICY_KEY]: 'off' });
  if (cur[CLASS_KEY] == null) await chrome.storage.local.set({ [CLASS_KEY]: 'fixture' });
  try {
    const sha = await computeAlgorithmSha();
    await chrome.storage.local.set({ [SHA_KEY]: sha });
    console.log('[SPR-V3] vision_spike (DIAGNOSTICO) pronto. Probes default-OFF. algorithm_sha=' + sha);
  } catch (e) {
    // Falhar aqui NÃO pode inventar um sha: a captura sai com `algorithm_sha: null` e o
    // replay diz que não dá para comparar.
    console.warn('[SPR-V3] algorithm_sha indisponivel:', e && e.message);
  }
}

chrome.runtime.onInstalled.addListener(bootstrap);
chrome.runtime.onStartup.addListener(bootstrap);
