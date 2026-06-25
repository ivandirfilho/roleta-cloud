// Escuta Beat v2.7 - Background Service Worker
// 🆕 v2.7: Integração WebSocket com RoletaV11
// 🆕 v2.6: CORREÇÃO DE PERSISTÊNCIA - Usa chrome.alarms em vez de setInterval
// Compatível com Extrator Beat v17.1

console.log('🎧 Escuta Beat v2.7 - Background iniciado (Persistente + WebSocket!)');

try {
  importScripts('extractor_meta.js');
} catch (e) {
  console.warn('⚠️ Falha ao carregar extractor_meta.js:', e?.message || e);
}

try {
  importScripts('session_extractor.js');
} catch (e) {
  console.warn('⚠️ Falha ao carregar session_extractor.js:', e?.message || e);
}

try {
  importScripts('provider_router.js');
} catch (e) {
  console.warn('⚠️ Falha ao carregar provider_router.js:', e?.message || e);
}


// ===== SISTEMA DE LOGS ESTRUTURADOS =====
const LOG_HISTORY_MAX = 100; // Manter últimos 100 registros
let logHistory = [];

function addLog(type, message, data = null) {
  const entry = {
    id: Date.now(),
    timestamp: new Date().toISOString(),
    type: type, // 'info', 'success', 'warning', 'error', 'monitoring', 'result'
    message: message,
    data: data,
    readCount: readCount
  };

  logHistory.push(entry);

  // Manter apenas os últimos N registros
  if (logHistory.length > LOG_HISTORY_MAX) {
    logHistory = logHistory.slice(-LOG_HISTORY_MAX);
  }

  // Log no console também
  const emoji = {
    'info': '📋',
    'success': '✅',
    'warning': '⚠️',
    'error': '❌',
    'monitoring': '📡',
    'result': '🎯'
  }[type] || '📌';

  console.log(`${emoji} [${type.toUpperCase()}] ${message}`, data || '');

  return entry;
}

// ===== ESTADO =====
// SP-11 DEAL (27/05): cache in-memory do ultimo dealMeta para evitar race
// com state polling. Persistido tambem em chrome.storage.local.dealMeta.
let latestDealMeta = null;

const DEFAULT_STATE = {
  isListening: false,
  tabId: null,
  extractorData: null,
  results: [],
  resultsWithDir: [],  // 🆕 v2.8: [{numero, direcao}, ...] para exibir setas
  lastHash: '',
  totalRead: 0,
  lastUpdate: null,
  error: null,
  debug: null,
  monitoringData: {
    gameStatus: null,
    balance: 0,
    currentBet: 0,
    activeChip: 0
  },
  sessionData: {
    dealer: null,
    round_id: null,
    table: null,
    frameUrl: null,
    lastUpdate: null
  },
  currentMesa: null,
  mesaConfig: null,
  detectedProvider: null,
  autoStarted: false
};

// 🆕 v2.6: Removido readIntervalId - não persiste em MV3 Service Workers
// Agora usa chrome.alarms para persistência
let readCount = 0;

// 🆕 v2.7: Direção atual do giro (definida pelo usuário no popup)
let currentDirection = 'horario';
// 🆕 DIR1 (sentido-fase): a roleta gira UM sentido por vez; o sentido é uma FASE
// alternada, não um dado lido. directionSeed = fase informada pelo operador (1x);
// pendingPhaseResync = reconciliar a fase com a autoridade do servidor no primeiro
// state_sync após (re)conectar. Estas globals do service worker MV3 perdem-se quando
// o SW dorme (minimizar Chrome) — por isso são re-hidratadas do storage no boot.
let directionSeed = 'horario';
let pendingPhaseResync = false;

function phaseFlip(d) { return d === 'horario' ? 'anti-horario' : 'horario'; }
// Conta quantos giros NOVOS entraram no topo da leitura, alinhando a cauda da
// leitura nova com a cabeça da anterior (subsequência ordenada, robusto a repetição).
// Se k>1 giros caíram entre dois ticks (ou no minimizar), a fase precisa avançar k
// vezes, não 1, senão a paridade defasa. Conservador (=1) quando não há alinhamento.
function countNewSpins(newArr, oldArr) {
  if (!Array.isArray(newArr) || newArr.length === 0) return 1;
  if (!Array.isArray(oldArr) || oldArr.length === 0) return 1;
  const maxK = Math.min(newArr.length, 12);
  for (let k = 1; k <= maxK; k++) {
    const overlapLen = Math.min(oldArr.length, newArr.length - k);
    if (overlapLen <= 0) break;
    let match = true;
    for (let i = 0; i < overlapLen; i++) {
      if (newArr[k + i] !== oldArr[i]) { match = false; break; }
    }
    if (match) return k;
  }
  return 1;
}

// ===== 🆕 v2.7: WEBSOCKET CLIENT PARA INTEGRAÇÃO =====
const WS_CONFIG = {
  url: 'wss://roleta.xma-ia.com/ws',
  reconnectInterval: 5000,  // 5 segundos entre reconexões
  maxReconnectAttempts: 10
};

let wsConnection = null;
let wsReconnectAttempts = 0;
let wsConnected = false;

async function seedDealMetaFromExtractorData(extractorData) {
  if (typeof extractDealMetaFromExtractorData !== 'function') return null;
  const extracted = extractDealMetaFromExtractorData(extractorData);
  if (!extracted) return null;
  let currentMeta = latestDealMeta;
  if (!currentMeta) {
    try {
      const stored = await chrome.storage.local.get(['dealMeta']);
      currentMeta = stored?.dealMeta || null;
    } catch (_) { /* ignore storage read failures */ }
  }
  const merged = (typeof mergeDealMeta === 'function')
    ? mergeDealMeta(currentMeta, extracted)
    : extracted;
  if (!merged) return null;
  latestDealMeta = merged;
  try {
    await chrome.storage.local.set({ dealMeta: merged });
  } catch (_) { /* ignore storage write failures */ }
  console.log('🧩 DEAL meta hidratado do extrator:', merged);
  return merged;
}

// 🔧 MEL-005: restaurar contador de reconexões (sobrevive restart do Service Worker)
chrome.storage.session?.get('wsReconnectAttempts', (data) => {
  if (data?.wsReconnectAttempts) wsReconnectAttempts = data.wsReconnectAttempts;
});

// 🆕 v3.4: Sistema MASTER/SLAVE
let deviceRole = 'unknown';  // 'master' | 'slave' | 'unknown'
let connectionId = null;     // ID atribuído pelo servidor

// 🆕 v3.5: Gera ou recupera device_id persistente
async function getDeviceId() {
  const data = await chrome.storage.local.get(['deviceId']);
  if (data.deviceId) return data.deviceId;

  const newId = 'dev-' + crypto.randomUUID().slice(0, 8);
  await chrome.storage.local.set({ deviceId: newId });
  console.log('🆔 Device ID gerado:', newId);
  return newId;
}

// ===== AUTO-START + ZERO-UPLOAD (v3.3) =====
// Detecta o provider da aba (provider_router.js), carrega o manifest empacotado
// (providers/*.json) e inicia a escuta automaticamente. Mata o upload manual.

// Filtros de host para o webNavigation (derivados de PROVIDER_DETECTION).
const CASINO_HOST_FILTERS = (typeof PROVIDER_DETECTION !== 'undefined' ? PROVIDER_DETECTION : [])
  .flatMap((p) => (p.hostPatterns || []).map((h) => ({ hostContains: h })));

// Lock in-memory por aba: serializa disparos concorrentes de auto-start.
const autoStartInProgress = new Set();

// Abas paradas manualmente: o auto-start NÃO re-inicia até o operador reiniciar
// explicitamente ou a aba fechar. Persistido em storage porque o SW é reciclado
// e os listeners/scan rodariam de novo, re-iniciando o que o operador parou
// (auditoria pós-implantação 14/06, achado #1).
async function tabHost(tabId) {
  try {
    const t = await chrome.tabs.get(tabId);
    return (typeof hostOf === 'function') ? hostOf(t.url || '') : null;
  } catch (e) {
    return null;
  }
}

async function suppressTab(tabId) {
  if (!tabId) return;
  try {
    const host = await tabHost(tabId);
    const data = await chrome.storage.local.get(['suppressedTabs']);
    const map = data.suppressedTabs || {};
    map[tabId] = { ts: Date.now(), host: host || null };
    await chrome.storage.local.set({ suppressedTabs: map });
  } catch (e) { /* best-effort */ }
}
async function unsuppressTab(tabId) {
  if (!tabId) return;
  try {
    const data = await chrome.storage.local.get(['suppressedTabs']);
    const map = data.suppressedTabs || {};
    if (map[tabId] != null) {
      delete map[tabId];
      await chrome.storage.local.set({ suppressedTabs: map });
    }
  } catch (e) { /* best-effort */ }
}
// Revalida host + TTL para não prender uma aba NOVA cujo tabId foi reciclado
// após reinício do Chrome (auditoria #a, 14/06).
async function isTabSuppressed(tabId) {
  try {
    const data = await chrome.storage.local.get(['suppressedTabs']);
    const map = data.suppressedTabs || {};
    const entry = map[tabId];
    if (entry == null) return false;
    const ts = (typeof entry === 'object' ? entry.ts : 0) || 0;
    const TTL = 24 * 60 * 60 * 1000;
    if (Date.now() - ts > TTL) { await unsuppressTab(tabId); return false; }
    const expectedHost = (typeof entry === 'object') ? entry.host : null;
    if (expectedHost) {
      const host = await tabHost(tabId);
      if (host && host !== expectedHost) { await unsuppressTab(tabId); return false; }
    }
    return true;
  } catch (e) {
    return false;
  }
}
// Poda no boot: remove supressões de abas que não existem mais (tabId fechado
// sem onRemoved, ex.: shutdown do Chrome).
async function pruneSuppressedTabs() {
  try {
    const data = await chrome.storage.local.get(['suppressedTabs']);
    const map = data.suppressedTabs || {};
    const ids = Object.keys(map);
    if (!ids.length) return;
    const tabs = await chrome.tabs.query({});
    const live = new Set(tabs.map((t) => String(t.id)));
    let changed = false;
    for (const id of ids) {
      if (!live.has(String(id))) { delete map[id]; changed = true; }
    }
    if (changed) await chrome.storage.local.set({ suppressedTabs: map });
  } catch (e) { /* best-effort */ }
}

// Política de auto-start: 'auto' (default) | 'off'. Qualquer valor legado ≠ 'off'
// (ex.: 'ask' gravado por versão anterior) é normalizado para 'auto' (achado #4/extra).
async function getAutoStartPolicy() {
  try {
    const data = await chrome.storage.local.get(['autoStartPolicy']);
    return data.autoStartPolicy === 'off' ? 'off' : 'auto';
  } catch (e) {
    return 'auto';
  }
}

// 📸 Vision (foto_roleta): política de captura de foto. 'on' (default) | 'off'.
// Quando 'on', a cada novo número a Escuta tira 1 screenshot da aba visível e
// envia ao servidor (msg foto_frame) para OCR. Desligar: storage.local fotoCapturePolicy='off'.
async function getFotoCapturePolicy() {
  try {
    const data = await chrome.storage.local.get(['fotoCapturePolicy']);
    return data.fotoCapturePolicy === 'off' ? 'off' : 'on';
  } catch (e) {
    return 'on';
  }
}

// 📸 Vision (foto_roleta): captura de foto. Estado de throttle/single-flight para
// não inundar o servidor (cada OCR leva alguns segundos no CPU do servidor).
let _fotoInFlight = false;
let _lastFotoTs = 0;
const FOTO_MIN_INTERVAL_MS = 6000; // no máx 1 foto a cada 6s

// Captura UMA foto da aba visível e envia ao servidor para OCR. Defensivo:
// nunca lança (o chamador já está em try/catch); só roda se a política for 'on'.
async function captureAndSendFrame(state) {
  if ((await getFotoCapturePolicy()) === 'off') return;
  if (!state || !state.tabId) return;

  // throttle + single-flight: evita empilhar fotos (causa de travada no WS/OCR)
  const now = Date.now();
  if (_fotoInFlight) return;
  if (now - _lastFotoTs < FOTO_MIN_INTERVAL_MS) return;

  // descobre o windowId da aba monitorada (captureVisibleTab é por janela)
  let windowId;
  try {
    const tab = await chrome.tabs.get(state.tabId);
    windowId = tab && tab.windowId;
  } catch (e) {
    return; // aba sumiu
  }
  if (windowId == null) return;

  _fotoInFlight = true;
  try {
    let dataUrl;
    try {
      dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: 'jpeg', quality: 55 });
    } catch (e) {
      // captura falha se a aba não estiver visível/ativa (esperado) — silencioso
      return;
    }
    if (!dataUrl) return;
    _lastFotoTs = Date.now();
    const traceId = `foto-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    sendToWebSocket({ type: 'foto_frame', trace_id: traceId, image: dataUrl });
  } finally {
    _fotoInFlight = false;
  }
}


// Carrega manifest empacotado via fetch(getURL) — zero-upload.
async function loadBundledManifest(providerId) {
  const path = (typeof manifestPathFor === 'function')
    ? manifestPathFor(providerId)
    : `providers/${providerId}.json`;
  if (!path) return null;
  try {
    const res = await fetch(chrome.runtime.getURL(path));
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return await res.json();
  } catch (e) {
    console.warn('⚠️ Falha ao carregar manifest empacotado', providerId, e?.message || e);
    addLog('error', `Falha ao carregar manifest ${providerId}: ${e?.message || e}`);
    return null;
  }
}

async function getFrameUrlsForTab(tabId) {
  try {
    const frames = await chrome.webNavigation.getAllFrames({ tabId });
    return (frames || []).map((f) => f.url).filter(Boolean);
  } catch (e) {
    return [];
  }
}

// Combina URL principal + URLs dos iframes (o jogo Evolution vive num iframe).
async function detectProviderForTab(tabId, mainUrl) {
  const frameUrls = await getFrameUrlsForTab(tabId);
  const all = [mainUrl, ...frameUrls].filter(Boolean);
  if (typeof detectFromFrames !== 'function') return { providerId: null, confidence: 0 };
  return detectFromFrames(all);
}

function setBadge(text, color) {
  try {
    chrome.action.setBadgeText({ text: text || '' });
    if (color) chrome.action.setBadgeBackgroundColor({ color });
  } catch (e) { /* badge best-effort */ }
}

// Núcleo compartilhado de start (usado por auto-start e pelo botão manual).
async function startListeningInternal(tabId, manifest, providerId, origin) {
  const state = await getState();
  if (state.isListening && state.tabId === tabId) return false;

  if (manifest) {
    state.extractorData = manifest;
    await seedDealMetaFromExtractorData(manifest);
    if (manifest?.data?.results?.lastNumbers) {
      state.results = manifest.data.results.lastNumbers.slice(0, 12);
      state.lastHash = state.results.slice(0, 5).join(',');
    }
  }
  state.detectedProvider = providerId || state.detectedProvider || null;
  state.autoStarted = origin === 'auto';
  state.isListening = true;
  state.tabId = tabId;
  state.error = null;
  state.lastUpdate = Date.now();
  readCount = 0;

  await saveState(state);

  startReadLoopAlarm();
  startKeepAliveAlarm();
  connectWebSocket();
  setBadge('●', '#1a7f37');
  broadcastToTabs({
    action: 'stateSync',
    data: { isListening: true, autoStarted: state.autoStarted, detectedProvider: state.detectedProvider },
  });
  addLog('info', `Escuta ${origin === 'auto' ? 'AUTO-iniciada' : 'iniciada'} (${providerId || 'manual'}) tab ${tabId}`);
  console.log(`✅ Escuta ${origin} iniciada — tab ${tabId} provider ${providerId}`);
  return true;
}

// Decide se deve auto-iniciar a escuta para uma aba.
async function maybeAutoStart(tabId, url) {
  if (!tabId) return;
  // Lock por aba: onCompleted + onHistoryStateUpdated + scan + popup trigger podem
  // disparar quase ao mesmo tempo; sem isto o guard por getState() é TOCTOU e dois
  // fluxos chegam a connectWebSocket criando socket duplicado (review 14/06).
  if (autoStartInProgress.has(tabId)) return;
  autoStartInProgress.add(tabId);
  try {
    const policy = await getAutoStartPolicy();
    if (policy === 'off') return;

    // STOP manual segura: não re-inicia aba parada pelo operador (achado #1).
    if (await isTabSuppressed(tabId)) return;

    const state = await getState();
    if (state.isListening && state.tabId === tabId) return; // já escutando esta aba
    // Já escutando OUTRA aba: não sequestra o tabId singleton (achado #3).
    if (state.isListening && state.tabId !== tabId) {
      addLog('info', `Auto-start ignorado: já escutando a aba ${state.tabId}; aba ${tabId} não assumida.`);
      return;
    }

    const detection = await detectProviderForTab(tabId, url);
    if (!detection || !detection.providerId) return; // unknown ou ambíguo (NB-03)

    const provider = (typeof getProvider === 'function') ? getProvider(detection.providerId) : null;
    if (!provider || !provider.available) {
      addLog('info', `Provider detectado sem manifest empacotado: ${detection.providerId}`);
      return;
    }

    if (policy === 'ask') {
      await chrome.storage.local.set({
        pendingAutoStart: { tabId, providerId: detection.providerId, confidence: detection.confidence, ts: Date.now() },
      });
      setBadge('!', '#9a6700');
      broadcastToTabs({ action: 'providerDetected', data: { tabId, providerId: detection.providerId, confidence: detection.confidence } });
      return;
    }

    // policy === 'auto'
    const manifest = await loadBundledManifest(detection.providerId);
    if (!manifest) return;
    await startListeningInternal(tabId, manifest, detection.providerId, 'auto');
  } finally {
    autoStartInProgress.delete(tabId);
  }
}

// Registra os listeners de auto-detecção (1×).
let autoDetectRegistered = false;
function registerAutoDetectListeners() {
  if (autoDetectRegistered) return;
  if (!chrome.webNavigation || !chrome.webNavigation.onCompleted) return;
  const filter = CASINO_HOST_FILTERS.length ? { url: CASINO_HOST_FILTERS } : undefined;
  const handler = (details) => { maybeAutoStart(details.tabId, details.url).catch(() => {}); };
  try {
    chrome.webNavigation.onCompleted.addListener(handler, filter);
    if (chrome.webNavigation.onHistoryStateUpdated) {
      chrome.webNavigation.onHistoryStateUpdated.addListener(handler, filter);
    }
    autoDetectRegistered = true;
    console.log('🔎 Auto-detecção registrada para', CASINO_HOST_FILTERS.length, 'padrões de host');
  } catch (e) {
    console.warn('⚠️ webNavigation listener falhou:', e?.message || e);
  }
}

// Varre abas já abertas (cobre o caso de a aba existir antes do SW iniciar).
async function scanOpenTabsForProviders() {
  try {
    await pruneSuppressedTabs(); // limpa supressões de abas que sumiram (achado #a)
    const tabs = await chrome.tabs.query({});
    for (const tab of tabs) {
      if (!tab.id) continue;
      await maybeAutoStart(tab.id, tab.url).catch(() => {});
    }
  } catch (e) { /* best-effort */ }
}


function connectWebSocket() {
  // Idempotente: já conectado OU em conexão. O segundo guard (CONNECTING) é
  // essencial sob auto-start concorrente — sem ele, dois disparos quase
  // simultâneos criam um 2º socket e deixam o 1º órfão (review 14/06).
  if (wsConnection && (wsConnection.readyState === WebSocket.OPEN || wsConnection.readyState === WebSocket.CONNECTING)) {
    return;
  }

  try {
    console.log('🔌 Conectando ao servidor WebSocket...');
    const socket = new WebSocket(WS_CONFIG.url);
    wsConnection = socket;

    socket.onopen = async () => {
      if (wsConnection !== socket) { try { socket.close(); } catch (e) {} return; } // órfão
      console.log('✅ WebSocket conectado ao servidor Python');
      wsConnected = true;
      wsReconnectAttempts = 0;
      chrome.storage.session?.set({ wsReconnectAttempts: 0 });

      // 🆕 v3.5: Enviar registro com device_id
      const deviceId = await getDeviceId();
      socket.send(JSON.stringify({
        type: 'register',
        device_id: deviceId
      }));

      // 🆕 DIR1: ao (re)conectar, pedir reconciliação de fase no primeiro state_sync.
      pendingPhaseResync = true;

      addLog('success', 'WebSocket conectado', { url: WS_CONFIG.url, device_id: deviceId });
      notifyConnectionStatus(true); // 🆕 v3.0: Notificar overlay
    };

    socket.onclose = () => {
      // Ignora close de socket órfão: não derruba a referência saudável atual.
      if (wsConnection !== socket) return;
      console.log('🔌 WebSocket desconectado');
      wsConnected = false;
      wsConnection = null;
      notifyConnectionStatus(false); // 🆕 v3.0: Notificar overlay

      // Tentar reconectar se ainda estiver escutando
      scheduleReconnect();
    };

    socket.onerror = (error) => {
      console.warn('⚠️ Erro WebSocket:', error);
      if (wsConnection === socket) wsConnected = false;
    };

    socket.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'ack') {
          console.log('✅ Servidor confirmou recebimento:', data.received);
        }
        else if (data.type === 'foto_resultado') {
          // 📸 Vision (foto_roleta): resultado do OCR do frame enviado
          if (data.ok) {
            console.log('📸 OCR:', { dealer: data.dealer, provider: data.provider, wheel_model: data.wheel_model, conf: data.confidence, ms: data.ms });
            addLog('result', `📸 Foto→dados: dealer=${data.dealer || '—'} provider=${data.provider || '—'} roleta=${data.wheel_model || '—'} (conf ${Math.round((data.confidence || 0) * 100)}%)`, {
              texts: data.texts, ms: data.ms
            });
          } else {
            console.log('📸 OCR sem resultado:', { enabled: data.enabled, available: data.available });
          }
        }
        else if (data.type === 'sugestao') {
          // 🆕 v3.0: Recebeu sugestão do servidor - enviar para content script
          console.log('🎯 SUGESTÃO RECEBIDA:', data.data);
          addLog('success', 'Sugestão recebida', data.data);

          // Enviar para o content script na aba ativa
          sendSuggestionToContentScript(data.data);
        }
        else if (data.type === 'state_sync') {
          // 🆕 v3.1: Heartbeat - sincronização de estado a cada 1s
          // 🆕 DIR1 (sentido-fase): o state_sync já carrega target_direction (a direção
          // do PRÓXIMO giro = autoridade do servidor). Após (re)conectar, reconcilia UMA
          // vez a fase local com a do servidor — corrige o caso em que o service worker
          // reiniciou e voltou currentDirection a 'horario' ao minimizar o Chrome.
          if (pendingPhaseResync && data.data && data.data.target_direction) {
            const srvDir = data.data.target_direction;
            if (srvDir === 'horario' || srvDir === 'anti-horario') {
              if (srvDir !== currentDirection) {
                console.log(`🔄 DIR1 resync de fase: ${currentDirection} → ${srvDir} (servidor)`);
                currentDirection = srvDir;
                chrome.storage.local.set({ currentDirection });
              }
              pendingPhaseResync = false;
            }
          }
          // Enviar para o content script para manter overlay sincronizado
          sendStateSyncToContentScript(data.data);
        }
        else if (data.type === 'sessao_resetada') {
          // 🆕 v3.3: Resposta de reset de sessão
          console.log('✅ Sessão resetada pelo servidor:', data.data);
          addLog('success', 'Sessão resetada', data.data);
          // 🆕 DIR1 (sentido-fase): o reset zera last_direction no servidor; a fase do
          // cliente deve voltar à semente do operador para não dessincronizar na cadência
          // pós-reset (1ª calibração). Reconcilia com o servidor no próximo state_sync.
          currentDirection = directionSeed || 'horario';
          chrome.storage.local.set({ currentDirection });
          pendingPhaseResync = true;
          sendSessionResetToContentScript(data.data);
        }
        // 🆕 v3.4: Sistema MASTER/SLAVE
        else if (data.type === 'role_assigned') {
          // Recebido após conectar - informa nosso role inicial
          deviceRole = data.role;
          connectionId = data.connection_id;
          console.log(`👑 Role atribuído: ${deviceRole} (ID: ${connectionId})`);
          addLog('info', `Role: ${deviceRole}`, { connectionId });
          sendRoleToContentScript(deviceRole, 'assigned');
        }
        else if (data.type === 'role_changed') {
          // Nosso role mudou (ex: novo MASTER conectou ou MASTER desconectou)
          const oldRole = deviceRole;
          deviceRole = data.role;
          console.log(`🔄 Role mudou: ${oldRole} → ${deviceRole} (${data.reason})`);
          addLog('info', `Role mudou: ${deviceRole}`, { reason: data.reason });
          sendRoleToContentScript(deviceRole, data.reason);
        }
        else if (data.type === 'error' && data.code === 'NOT_MASTER') {
          // Tentamos enviar dados como SLAVE
          console.warn(`⚠️ Erro: ${data.message}`);
          addLog('warning', 'Não é MASTER', { message: data.message });
        }
        // 🆕 v3.0: Microserviço Extrator
        else if (data.type === 'mesas_disponiveis') {
          console.log('📋 Mesas disponíveis:', data.mesas);
          broadcastToTabs({ action: 'updateMesas', mesas: data.mesas });
        }
        else if (data.type === 'mesa_configurada' || data.type === 'config_mesa') {
          console.log(`✅ Configuração recebida para: ${data.mesa_id}`);
          const state = await getState();
          state.currentMesa = data.mesa_id;
          state.mesaConfig = data.config;
          state.extractorData = data.config; // Retrocompatibilidade
          await seedDealMetaFromExtractorData(data.config);

          if (data.config && data.config.data && data.config.data.results) {
            state.results = data.config.data.results.lastNumbers?.slice(0, 12) || [];
          }

          // 🆕 v3.1: CORREÇÃO BUG #3 - Obter tabId da aba ativa se não tiver
          if (!state.tabId) {
            try {
              const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
              if (tab && !tab.url.startsWith('chrome://') && !tab.url.startsWith('chrome-extension://')) {
                state.tabId = tab.id;
                console.log('📍 tabId obtido da aba ativa:', state.tabId);
                addLog('info', `Aba detectada: ${tab.title?.substring(0, 30)}`);
              }
            } catch (e) {
              console.warn('⚠️ Não foi possível obter tabId:', e.message);
            }
          }

          await chrome.storage.local.set({ escutaState: state });
          addLog('success', `Mesa ${data.mesa_id} configurada`);

          // Se auto_start, iniciar escuta
          if (data.auto_start && !state.isListening && state.tabId) {
            console.log('🚀 Auto-start ativado!');
            startReadLoopAlarm();
            startKeepAliveAlarm();
            state.isListening = true;
            await chrome.storage.local.set({ escutaState: state });
            addLog('success', 'Escuta iniciada automaticamente');
          } else if (data.auto_start && !state.tabId) {
            console.warn('⚠️ Auto-start solicitado mas tabId não disponível');
            addLog('warning', 'Não foi possível iniciar automaticamente - abra a página da roleta');
          }

          chrome.runtime.sendMessage({ action: 'mesaConfigurada', data: data });
          broadcastToTabs({ action: 'mesaConfigurada', data: data });
        }
      } catch (e) {
        console.warn('⚠️ Erro ao processar mensagem WS:', e);
      }
    };

  } catch (error) {
    console.warn('⚠️ Não foi possível conectar WebSocket:', error.message);
    wsConnected = false;
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (wsReconnectAttempts >= WS_CONFIG.maxReconnectAttempts) {
    console.log('⚠️ Máximo de tentativas de reconexão atingido');
    return;
  }

  wsReconnectAttempts++;
  chrome.storage.session?.set({ wsReconnectAttempts });
  setTimeout(() => {
    console.log(`🔄 Tentativa de reconexão ${wsReconnectAttempts}/${WS_CONFIG.maxReconnectAttempts}`);
    connectWebSocket();
  }, WS_CONFIG.reconnectInterval);
}

function sendToWebSocket(data) {
  if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
    // Tentar conectar se não estiver
    connectWebSocket();
    return false;
  }

  // 🆕 v3.4: Verificar role para mensagens de dados
  const dataMessages = ['novo_resultado', 'historico_inicial', 'correcao_historico'];
  if (dataMessages.includes(data.type) && deviceRole !== 'master') {
    console.log(`⏸️ SLAVE: não enviando ${data.type} (role: ${deviceRole})`);
    return false;  // Não envia se não for MASTER
  }

  try {
    wsConnection.send(JSON.stringify(data));
    return true;
  } catch (error) {
    console.warn('⚠️ Erro ao enviar via WebSocket:', error.message);
    return false;
  }
}

function closeWebSocket() {
  if (wsConnection) {
    wsConnection.close();
    wsConnection = null;
    wsConnected = false;
  }
}

// 🆕 v3.0: Envia sugestão para o content script
async function sendSuggestionToContentScript(sugestao) {
  try {
    const state = await getState();
    const tabId = state.tabId;

    if (!tabId) {
      console.warn('⚠️ Nenhuma aba monitorada para enviar sugestão');
      return;
    }

    // Enviar para o content script na aba monitorada
    chrome.tabs.sendMessage(tabId, {
      action: 'updateOverlay',
      data: sugestao
    }, (response) => {
      if (chrome.runtime.lastError) {
        console.warn('⚠️ Erro ao enviar para content:', chrome.runtime.lastError.message);
        // Tentar injetar o content script se não estiver presente
        injectContentScriptIfNeeded(tabId, sugestao);
      } else {
        console.log('✅ Sugestão enviada para overlay');
      }
    });

  } catch (error) {
    console.error('❌ Erro ao enviar sugestão:', error);
  }
}

// 🆕 v3.0: Injeta content script se não estiver presente
async function injectContentScriptIfNeeded(tabId, sugestao) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId: tabId },
      files: ['content.js']
    });

    await chrome.scripting.insertCSS({
      target: { tabId: tabId },
      files: ['overlay.css']
    });

    // Tentar enviar novamente após injeção
    setTimeout(() => {
      chrome.tabs.sendMessage(tabId, {
        action: 'updateOverlay',
        data: sugestao
      });
    }, 500);

  } catch (error) {
    console.warn('⚠️ Não foi possível injetar content script:', error.message);
  }
}

// 🆕 v3.1: Envia state_sync para o content script (heartbeat)
let lastStateSyncHash = '';
async function sendStateSyncToContentScript(stateData) {
  try {
    // Throttle: só envia se mudou (excluindo timestamp para comparação estável)
    const { timestamp, ...stableData } = stateData;
    const hash = JSON.stringify(stableData);
    if (hash === lastStateSyncHash) return;
    lastStateSyncHash = hash;

    const state = await getState();
    const tabId = state.tabId;

    if (!tabId) return;

    // Enviar para o content script
    chrome.tabs.sendMessage(tabId, {
      action: 'stateSync',
      data: stateData
    });

  } catch (error) {
    // Silencioso - heartbeat não deve spammar logs
  }
}

// 🆕 v3.0: Notificar content script sobre status de conexão
function notifyConnectionStatus(connected) {
  getState().then(state => {
    if (state.tabId) {
      chrome.tabs.sendMessage(state.tabId, {
        action: 'connectionStatus',
        connected: connected
      }).catch(() => { });
    }
  });
}

// 🆕 v3.3: Encaminha resposta de reset de sessão para o content script
async function sendSessionResetToContentScript(data) {
  try {
    const state = await getState();
    const tabId = state.tabId;

    if (!tabId) return;

    chrome.tabs.sendMessage(tabId, {
      action: 'sessionReset',
      data: data
    });

    console.log('📤 Reset de sessão enviado para overlay');
  } catch (error) {
    console.warn('⚠️ Erro ao enviar reset para content:', error);
  }
}

// 🆕 v3.4: Encaminha mudança de role para o content script
async function sendRoleToContentScript(role, reason) {
  try {
    const state = await getState();
    const tabId = state.tabId;

    if (!tabId) return;

    chrome.tabs.sendMessage(tabId, {
      action: 'roleChanged',
      role: role,
      reason: reason
    });

    console.log(`📤 Role ${role} enviado para overlay`);
  } catch (error) {
    console.warn('⚠️ Erro ao enviar role para content:', error);
  }
}
// 🆕 v3.0: Captura DOM via microserviço
async function capturarMesaRemota() {
  try {
    const state = await getState();
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error('Nenhuma aba ativa para capturar');

    addLog('info', 'Iniciando captura DOM remota...');

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id, allFrames: true },
      func: () => {
        // Esta função roda no contexto de cada frame
        function getCleanDOM() {
          const betSpots = Array.from(document.querySelectorAll('[data-bet-spot-id]')).map(el => {
            const rect = el.getBoundingClientRect();
            return {
              id: el.getAttribute('data-bet-spot-id'),
              rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
            };
          });

          const chips = Array.from(document.querySelectorAll("[data-role='chip']")).map(el => ({
            value: el.getAttribute('data-value'),
            label: el.innerText
          }));

          return {
            url: window.location.href,
            betSpots: betSpots,
            chips: chips,
            html: document.body.innerText.substring(0, 1000) // Amostra de texto para status
          };
        }
        return getCleanDOM();
      }
    });

    // Enviar resultado para o servidor
    const snapshot = {
      url: tab.url,
      frames: results.map(r => r.result),
      timestamp: Date.now()
    };

    sendToWebSocket({
      type: 'extrair_mesa',
      url: tab.url,
      dom_snapshot: snapshot
    });

    return { success: true };
  } catch (e) {
    addLog('error', `Falha na captura remota: ${e.message}`);
    return { success: false, error: e.message };
  }
}

// ===== FIM WEBSOCKET =====

// ===== INICIALIZAÇÃO =====
chrome.runtime.onInstalled.addListener(async () => {
  console.log('Extensão instalada/atualizada');
  chrome.storage.local.set({ escutaState: DEFAULT_STATE });
  // 🆕 v3.3: política de auto-start default = 'auto' (responde §8 #7 do plano)
  const pol = await chrome.storage.local.get(['autoStartPolicy']);
  if (!pol.autoStartPolicy) await chrome.storage.local.set({ autoStartPolicy: 'auto' });
  registerAutoDetectListeners();
  scanOpenTabsForProviders();
});

// 🆕 v2.6: Listener para quando o Chrome inicia
chrome.runtime.onStartup.addListener(async () => {
  console.log('🔄 Chrome iniciou - verificando estado...');
  registerAutoDetectListeners();
  const state = await getState();
  if (state.isListening && state.tabId) {
    console.log('🔄 Retomando escuta após startup do Chrome');
    startReadLoopAlarm();
  }
  scanOpenTabsForProviders();
});

// Carregar estado ao iniciar worker
chrome.storage.local.get(['escutaState'], (data) => {
  if (!data.escutaState) {
    chrome.storage.local.set({ escutaState: DEFAULT_STATE });
  } else if (data.escutaState.isListening && data.escutaState.tabId) {
    console.log('🔄 Worker reiniciado - retomando escuta ativa');
    startReadLoopAlarm();
    connectWebSocket(); // Garantir que WS está conectado
  }
});

// 🆕 DIR1 (sentido-fase): re-hidratar a FASE do storage no boot do service worker.
// Sem isto, o SW MV3 reinicia com currentDirection='horario' (literal) ao acordar de
// uma minimização, perdendo a paridade — causa do "dois números no mesmo sentido".
chrome.storage.local.get(['currentDirection', 'directionSeed'], (data) => {
  if (data.directionSeed === 'horario' || data.directionSeed === 'anti-horario') {
    directionSeed = data.directionSeed;
  }
  if (data.currentDirection === 'horario' || data.currentDirection === 'anti-horario') {
    currentDirection = data.currentDirection;
    console.log(`🔄 DIR1: fase re-hidratada do storage no boot: ${currentDirection}`);
  }
});

// 🆕 v3.3: registra a auto-detecção sempre que o service worker carrega
// (event-driven MV3). Guard interno evita listener duplicado; o scan cobre
// abas de cassino já abertas antes do SW acordar.
registerAutoDetectListeners();
scanOpenTabsForProviders();

// Listener ÚNICO para mensagens do popup e content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const action = request.action;

  // SP-11 DEAL-01 (27/05): captura DOM enviada pelo content script.
  // FIX (27/05 audit): escreve direto via chrome.storage.local.set para
  // evitar race com o polling de spins (que faz getState/saveState).
  // Tambem mantemos em memoria global para o sendToWebSocket pegar fresh.
  if (action === 'dealMetaUpdate') {
    (async () => {
      try {
        latestDealMeta = request.dealMeta || null;
        chrome.storage.local.set({ dealMeta: latestDealMeta });
        sendResponse({ success: true });
      } catch (e) {
        sendResponse({ success: false, error: String(e) });
      }
    })();
    return true;
  }

  // Ações síncronas rápidas (microserviço WS)
  if (action === 'listarMesas') {
    if (!wsConnected) connectWebSocket();
    sendToWebSocket({ type: 'listar_mesas' });
    sendResponse({ success: true });
    return true;
  }

  if (action === 'obterConfigMesa') {
    sendToWebSocket({ type: 'obter_config_mesa', mesa_id: request.mesa_id });
    sendResponse({ success: true });
    return true;
  }

  if (action === 'capturarMesa') {
    capturarMesaRemota().then(sendResponse);
    return true;
  }

  // Todas as demais ações: delegar ao handleMessage
  console.log('📩 Mensagem:', action, 'de:', sender.tab?.id || 'popup');
  handleMessage(request, sender).then(response => {
    sendResponse(response);
  }).catch(err => {
    console.error('Erro ao processar mensagem:', err);
    sendResponse({ success: false, error: err.message });
  });

  return true;
});

// 🆕 v4.0: Broadcast para todas as abas (Overlay e Control Panel)
async function broadcastToTabs(message) {
  try {
    const tabs = await chrome.tabs.query({});
    tabs.forEach(tab => {
      chrome.tabs.sendMessage(tab.id, message).catch(() => {
        // Ignora abas que não têm o content script injetado
      });
    });
    // Também envia para o popup se estiver aberto
    chrome.runtime.sendMessage(message).catch(() => { });
  } catch (e) {
    console.warn('⚠️ Erro no broadcast:', e);
  }
}

// ===== ALARM HANDLERS - PERSISTÊNCIA MV3 =====
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === 'readLoop') {
    const state = await getState();
    if (state.isListening && state.tabId) {
      readResults();
    } else {
      stopReadLoopAlarm();
    }
    return;
  }

  if (alarm.name === 'keepAlive') {
    const state = await getState();
    console.log('⏰ Keep-alive - isListening:', state.isListening, 'tabId:', state.tabId);

    if (state.isListening && state.tabId) {
      const alarms = await chrome.alarms.getAll();
      const hasReadLoop = alarms.some(a => a.name === 'readLoop');
      if (!hasReadLoop) {
        console.log('🔄 Recriando alarm de leitura...');
        startReadLoopAlarm();
      }
    } else {
      stopAllAlarms();
    }
  }
});

async function handleMessage(message, sender = null) {
  const { action } = message;

  // 🆕 v3.3: controle de auto-start (zero-upload)
  if (action === 'getAutoStartPolicy') {
    return { success: true, policy: await getAutoStartPolicy() };
  }

  if (action === 'setAutoStartPolicy') {
    // 'ask' removido da whitelist: não há UI que consuma pendingAutoStart (achado #4).
    const policy = ['auto', 'off'].includes(message.policy) ? message.policy : 'auto';
    await chrome.storage.local.set({ autoStartPolicy: policy });
    addLog('info', `Política de auto-start: ${policy}`);
    return { success: true, policy };
  }

  // Popup pede detecção imediata na aba atual (botão "Detectar agora").
  if (action === 'detectProvider') {
    const tabId = message.tabId || sender?.tab?.id;
    const detection = await detectProviderForTab(tabId, message.url || null);
    return { success: true, detection };
  }

  // Popup força o auto-start na aba. force=true (operador ligou o toggle/clicou)
  // remove a supressão; sem force (popup só abriu) respeita STOP manual (achado #1).
  if (action === 'triggerAutoStart') {
    const tabId = message.tabId || sender?.tab?.id;
    if (message.force && tabId) await unsuppressTab(tabId);
    await maybeAutoStart(tabId, message.url || null);
    return { success: true };
  }

  if (action === 'setExtractorData') {
    const state = await getState();
    state.extractorData = message.data;
    state.error = null;
    await seedDealMetaFromExtractorData(message.data);

    if (message.data?.data?.results?.lastNumbers) {
      state.results = message.data.data.results.lastNumbers.slice(0, 12);
      state.lastHash = state.results.slice(0, 5).join(',');
    }

    await saveState(state);
    console.log('✅ Dados do extrator salvos');
    return { success: true };
  }

  if (action === 'startListening') {
    const state = await getState();

    // 🆕 v3.3: ZERO-UPLOAD — sem extractorData, carrega o manifest EMPACOTADO do
    // provider detectado na aba (ou Evolution por default). Conserta o template
    // mínimo legado, que vinha em formato antigo (selectors:{}) incompatível com o
    // readResults data-driven (data.session/monitoring/results).
    if (!state.extractorData) {
      const tabId = message.tabId || sender?.tab?.id || state.tabId;
      let providerId = 'evolution';
      try {
        const det = await detectProviderForTab(tabId, null);
        if (det && det.providerId) providerId = det.providerId;
      } catch (e) { /* mantém evolution */ }

      const bundled = await loadBundledManifest(providerId);
      if (bundled) {
        state.extractorData = bundled;
        state.detectedProvider = providerId;
        addLog('info', `Manifest empacotado '${providerId}' carregado automaticamente (zero-upload)`);
      } else {
        addLog('error', 'Zero-upload falhou: nenhum manifest empacotado disponível');
      }
    }

    await seedDealMetaFromExtractorData(state.extractorData);

    state.isListening = true;
    // 🆕 v4.0: Usar sender.tab.id como fallback se tabId não for passado (ex: control_panel.js)
    state.tabId = message.tabId || sender?.tab?.id || state.tabId;
    state.error = null;
    state.lastUpdate = Date.now();
    readCount = 0;

    await saveState(state);
    await unsuppressTab(state.tabId); // início explícito remove a supressão (achado #1)

    // 🆕 v2.6: Usar alarms persistentes
    startReadLoopAlarm();
    startKeepAliveAlarm();

    // 🆕 v2.7: Conectar ao servidor WebSocket
    connectWebSocket();
    setBadge('●', '#1a7f37'); // badge consistente com auto-start (achado #2)

    // 🆕 v4.0: Broadcast para atualizar UIs
    broadcastToTabs({ action: 'stateSync', data: { isListening: true } });

    console.log('✅ Escuta iniciada para tab:', state.tabId);
    return { success: true };
  }

  if (action === 'stopListening') {
    const state = await getState();
    const stoppedTab = state.tabId;
    state.isListening = false;
    state.error = null;

    await saveState(state);

    // Teardown PRIMEIRO — não pode ser pulado se o suppress (storage) falhar (achado #c)
    stopAllAlarms();
    closeWebSocket();
    setBadge(''); // limpa o badge ao parar (achado #2)

    // Depois suprime o auto-start desta aba até reinício explícito (achado #1)
    if (stoppedTab) await suppressTab(stoppedTab);

    // 🆕 v4.0: Broadcast para atualizar UIs
    broadcastToTabs({ action: 'stateSync', data: { isListening: false } });

    console.log('⏹️ Escuta parada');
    return { success: true };
  }

  if (action === 'getState') {
    return await getState();
  }

  // 🆕 v2.4: Ações para gerenciar logs
  if (action === 'getLogs') {
    return {
      success: true,
      logs: logHistory,
      count: logHistory.length,
      maxSize: LOG_HISTORY_MAX
    };
  }

  if (action === 'clearLogs') {
    logHistory = [];
    addLog('info', 'Histórico de logs limpo');
    return { success: true };
  }

  if (action === 'exportLogs') {
    const exportData = {
      exportedAt: new Date().toISOString(),
      version: '2.7',
      totalLogs: logHistory.length,
      logs: logHistory,
      currentState: await getState()
    };
    return { success: true, data: exportData };
  }

  // 🆕 v2.8: Handler para mudança de direção - RECALCULA HISTÓRICO
  // Só envia correção se for mudança MANUAL do usuário
  if (action === 'setDirection') {
    const isManualCorrection = message.manual === true;  // 🔧 Flag para distinguir
    currentDirection = message.direction || 'horario';
    console.log(`🔄 Direção alterada para: ${currentDirection} (manual: ${isManualCorrection})`);
    addLog('info', `Direção alterada: ${currentDirection}`);

    // Só recalcula e envia se for correção MANUAL do usuário
    if (isManualCorrection) {
      const state = await getState();
      if (state.resultsWithDir && state.resultsWithDir.length > 0) {
        let tempDir = currentDirection;
        for (let i = 0; i < state.resultsWithDir.length; i++) {
          state.resultsWithDir[i].direcao = tempDir;
          tempDir = tempDir === 'horario' ? 'anti-horario' : 'horario';
        }
        await saveState(state);

        console.log('📊 Histórico recalculado (correção manual)');

        // Enviar correção para Python
        sendToWebSocket({
          type: 'correcao_historico',
          resultados: state.resultsWithDir
        });
      }
    }

    return { success: true, direction: currentDirection };
  }

  // 🆕 v3.3: Handler para enviar mensagens do content script para o servidor
  if (action === 'sendToServer') {
    const sent = sendToWebSocket(message.data);
    if (sent) {
      console.log('📤 Mensagem enviada ao servidor:', message.data.type);
      return { success: true };
    } else {
      console.warn('⚠️ Não foi possível enviar ao servidor');
      return { success: false, error: 'WebSocket não conectado' };
    }
  }

  return { success: false, error: 'Ação desconhecida' };
}

// ===== FUNÇÕES DE ESTADO =====
async function getState() {
  const data = await chrome.storage.local.get(['escutaState']);
  const state = data.escutaState || { ...DEFAULT_STATE };
  return {
    ...state,
    isConnected: wsConnected,
    deviceRole: deviceRole,
    wsUrl: WS_CONFIG.url  // 🆕 v5.0: URL para exibir no painel de controle
  };
}

async function saveState(state) {
  await chrome.storage.local.set({ escutaState: state });
}

// ===== LOOP DE LEITURA (v2.6 - PERSISTENTE) =====
// 🆕 Usa chrome.alarms em vez de setInterval
// Mínimo do Chrome é ~1.2s, usamos 2s para segurança

function startReadLoopAlarm() {
  console.log('🔄 Iniciando loop persistente (alarm ~2s)');
  readCount = 0;

  // Ler imediatamente
  readResults();

  // Criar alarm que dispara a cada ~2 segundos
  // periodInMinutes mínimo é 0.0333 (~2s), valores menores são ignorados
  chrome.alarms.create('readLoop', {
    delayInMinutes: 0.0333,  // Primeira execução em ~2s
    periodInMinutes: 0.0333  // Repetir a cada ~2s
  });
}

function stopReadLoopAlarm() {
  chrome.alarms.clear('readLoop');
  console.log('⏹️ Alarm de leitura parado');
}

function stopAllAlarms() {
  chrome.alarms.clear('readLoop');
  chrome.alarms.clear('keepAlive');
  console.log('⏹️ Todos os alarms parados');
}

// ===== KEEP-ALIVE ALARM =====
// 🆕 v2.6: Reduzido para 15 segundos (0.25 min)
function startKeepAliveAlarm() {
  chrome.alarms.create('keepAlive', {
    delayInMinutes: 0.25,   // 15 segundos
    periodInMinutes: 0.25   // Verificar a cada 15 segundos
  });
  console.log('⏰ Alarm keep-alive ativo (15s)');
}

// ===== FUNÇÕES AUXILIARES DE PROCESSAMENTO =====
function cleanFinancialValue(rawText) {
  if (!rawText) return 0;

  // 🆕 v2.5: Remove caracteres Unicode bidirecionais (LRE, RLE, PDF, LRI, RLI, FSI, PDI)
  // Esses caracteres invisíveis vêm do Evolution Gaming e quebram o parse
  // U+2066 (LRI), U+2067 (RLI), U+2068 (FSI), U+2069 (PDI)
  // U+202A (LRE), U+202B (RLE), U+202C (PDF), U+202D (LRO), U+202E (RLO)
  let cleaned = rawText
    .replace(/[\u2066\u2067\u2068\u2069\u202A\u202B\u202C\u202D\u202E]/g, '')
    .replace(/R\$/g, '')
    .replace(/\u00A0/g, '')
    .replace(/\s+/g, '')
    .trim();

  // Remove pontos de milhar: "1.380,00" -> "1380,00"
  cleaned = cleaned.replace(/\./g, '');

  // Substitui vírgula decimal por ponto: "1380,00" -> "1380.00"
  cleaned = cleaned.replace(/,/g, '.');

  const value = parseFloat(cleaned);

  // Log para debug (apenas valores válidos)
  if (!isNaN(value) && value > 0) {
    console.log(`💰 cleanFinancialValue: "${rawText}" -> ${value}`);
  }

  return isNaN(value) ? 0 : value;
}

function buildTargetsMap(extractorData) {
  const targets = {};

  if (!extractorData?.data?.betSpots) return targets;

  const spots = extractorData.data.betSpots;

  // 🆕 v2.3: Compatível com Extrator Beat v17.1
  // v17.1 usa: betSpots.numbers.items[] com betSpotId
  // Versões antigas: betSpots.numbers[] com id

  // Mapear números
  const numbersItems = spots.numbers?.items || spots.numbers || [];
  if (Array.isArray(numbersItems)) {
    numbersItems.forEach(item => {
      const id = item.betSpotId || item.id;
      const selector = item.actionSelector || item.selector;
      if (id && selector) {
        targets[id] = selector;
      }
    });
  }

  // Mapear regiões (red, black, even, odd, etc)
  const regionsItems = spots.regions?.items || spots.regions || [];
  if (Array.isArray(regionsItems)) {
    regionsItems.forEach(item => {
      const id = item.betSpotId || item.id;
      const selector = item.actionSelector || item.selector;
      if (id && selector) {
        targets[id] = selector;
      }
    });
  }

  // Mapear especiais (1st12, 2nd12, 3rd12, column1, etc)
  const specialsItems = spots.specials?.items || spots.specials || [];
  if (Array.isArray(specialsItems)) {
    specialsItems.forEach(item => {
      const id = item.betSpotId || item.id;
      const selector = item.actionSelector || item.selector;
      if (id && selector) {
        targets[id] = selector;
      }
    });
  }

  console.log(`📍 buildTargetsMap: ${Object.keys(targets).length} alvos mapeados`);
  return targets;
}

function buildBroadcastState(state, pageNumbers, rawMonitoring) {
  const statusText = (rawMonitoring.gameStatus || '').toUpperCase();
  const isOpen = statusText.includes('FAÇAM') || statusText.includes('PLACE') || statusText.includes('ABERTO');

  return {
    timestamp: Date.now(),
    liveState: {
      status: isOpen ? 'OPEN' : 'CLOSED',
      balance: cleanFinancialValue(rawMonitoring.balance),
      currentRoundBet: cleanFinancialValue(rawMonitoring.currentBet),
      activeChipValue: cleanFinancialValue(rawMonitoring.activeChip),
      lastResults: pageNumbers.slice(0, 12)
    },
    executionConfig: state.extractorData?.config || null,
    availableChips: state.extractorData?.data?.monitoring?.chipControl?.availableChips || [],
    targets: buildTargetsMap(state.extractorData)
  };
}

// ===== LEITURA DE RESULTADOS =====
async function readResults() {
  const state = await getState();

  if (!state.isListening || !state.tabId) {
    console.log('❌ Leitura cancelada - isListening:', state.isListening, 'tabId:', state.tabId);
    return;
  }

  readCount++;

  try {
    // Verificar se aba existe
    let tab;
    try {
      tab = await chrome.tabs.get(state.tabId);
    } catch (e) {
      console.log('❌ Aba não existe mais:', state.tabId);
      state.isListening = false;
      state.error = 'Aba fechada';
      await saveState(state);
      stopAllAlarms();
      setBadge(''); // limpa o badge quando a aba some (achado #2)
      return;
    }

    // Executar script na página
    const injectionResults = await chrome.scripting.executeScript({
      target: { tabId: state.tabId, allFrames: true },
      func: extractResultsFromPage
    });

    // Debug: mostrar o que foi encontrado
    let totalElementsFound = 0;
    let newNumbers = [];

    for (const result of injectionResults) {
      if (result.result) {
        if (result.result.numbers && result.result.numbers.length > 0) {
          newNumbers = result.result.numbers;
          totalElementsFound = result.result.elementsFound;
          break;
        }
      }
    }

    // Log a cada 10 leituras
    if (readCount % 10 === 1) {
      console.log(`📊 Leitura #${readCount}: ${totalElementsFound} elementos, ${newNumbers.length} números:`, newNumbers.slice(0, 5));
    }

    if (newNumbers.length > 0) {
      const newHash = newNumbers.slice(0, 5).join(',');

      // Atualizar debug no estado
      state.debug = {
        lastRead: new Date().toISOString(),
        readCount: readCount,
        elementsFound: totalElementsFound,
        numbersFound: newNumbers.length,
        currentHash: newHash,
        lastHash: state.lastHash
      };

      // ===== NOVA SEÇÃO: COLETA DE DADOS DE MONITORAMENTO (PARALELA) =====
      // 🆕 v2.3: Sempre tentar monitoramento, mesmo sem config (usa fallbacks)
      const monitoringConfig = state.extractorData?.data?.monitoring || {};

      try {
        // Executar segunda injeção APENAS para monitoramento
        const monitoringResults = await chrome.scripting.executeScript({
          target: { tabId: state.tabId, allFrames: true }, // Procurar em todos os frames (iframe Evolution)
          func: extractMonitoringData,
          args: [monitoringConfig]
        });

        // 🆕 v2.5: CORREÇÃO CRÍTICA - Acumular dados de TODOS os frames!
        // O saldo pode estar em um frame, a ficha em outro, etc.
        let combinedMonitoring = {
          gameStatus: null,
          gameStatusRaw: null,
          gameStatusMethod: null,
          isOpen: null,
          balance: null,
          currentBet: null,
          activeChip: null,
          frameUrl: null,
          debug: {}
        };

        for (const result of monitoringResults) {
          if (result.result) {
            const data = result.result;

            // 🆕 v2.5: Log estruturado de cada frame com info de gameStatus
            if (readCount % 10 === 1) {
              addLog('monitoring', 'Frame analisado', {
                gameStatus: data.gameStatus,
                isOpen: data.isOpen,
                method: data.gameStatusMethod,
                balance: data.balance,
                currentBet: data.currentBet,
                activeChip: data.activeChip,
                frameUrl: data.frameUrl?.substring(0, 60),
                debug: data.debug
              });
            }

            // Acumular dados - pegar o primeiro não-nulo de cada campo
            // 🆕 v2.5: Priorizar gameStatus que tem isOpen definido
            if (combinedMonitoring.isOpen === null && data.isOpen !== null) {
              combinedMonitoring.gameStatus = data.gameStatus;
              combinedMonitoring.gameStatusRaw = data.gameStatusRaw;
              combinedMonitoring.gameStatusMethod = data.gameStatusMethod;
              combinedMonitoring.isOpen = data.isOpen;
              combinedMonitoring.debug = data.debug;
              addLog('success', 'gameStatus detectado', {
                status: data.gameStatus,
                isOpen: data.isOpen,
                method: data.gameStatusMethod,
                raw: data.gameStatusRaw?.substring(0, 40)
              });
            }
            if (!combinedMonitoring.balance && data.balance) {
              combinedMonitoring.balance = data.balance;
              addLog('success', 'balance encontrado', { value: data.balance });
            }
            if (!combinedMonitoring.currentBet && data.currentBet) {
              combinedMonitoring.currentBet = data.currentBet;
              addLog('success', 'currentBet encontrado', { value: data.currentBet });
            }
            if (!combinedMonitoring.activeChip && data.activeChip) {
              combinedMonitoring.activeChip = data.activeChip;
              addLog('success', 'activeChip encontrado', { value: data.activeChip });
            }
          }
        }


        // Verificar se encontramos algo útil
        const hasData = combinedMonitoring.balance || combinedMonitoring.gameStatus ||
          combinedMonitoring.activeChip || combinedMonitoring.currentBet ||
          combinedMonitoring.isOpen !== null;

        if (hasData) {
          // Construir BroadcastState
          const broadcast = buildBroadcastState(state, newNumbers, combinedMonitoring);

          // 🆕 v2.5: Atualizar estado com dados de monitoramento INCLUINDO isOpen
          state.monitoringData = {
            gameStatus: combinedMonitoring.gameStatus,
            gameStatusRaw: combinedMonitoring.gameStatusRaw,
            gameStatusMethod: combinedMonitoring.gameStatusMethod,
            isOpen: combinedMonitoring.isOpen,  // ⬅️ CRÍTICO: true = pode apostar!
            balance: broadcast.liveState.balance,
            currentBet: broadcast.liveState.currentRoundBet,
            activeChip: broadcast.liveState.activeChipValue,
            debug: combinedMonitoring.debug
          };

          state.broadcastState = broadcast;

          // 🆕 v2.5: Log com emoji diferente para ABERTO/FECHADO
          const statusEmoji = combinedMonitoring.isOpen === true ? '🟢' :
            combinedMonitoring.isOpen === false ? '🔴' : '⚪';

          // Log apenas se status mudou ou a cada 10 leituras
          if (readCount % 10 === 1 || state.lastGameStatus !== broadcast.liveState.status) {
            console.log(`${statusEmoji} Status: ${combinedMonitoring.gameStatus} (isOpen: ${combinedMonitoring.isOpen}) | Saldo: R$ ${broadcast.liveState.balance.toFixed(2)} | Ficha: ${broadcast.liveState.activeChipValue}`);
            state.lastGameStatus = broadcast.liveState.status;

            // 🆕 v2.5: Log estruturado da mudança de status
            addLog('info', `Status mudou para ${combinedMonitoring.gameStatus}`, {
              isOpen: combinedMonitoring.isOpen,
              method: combinedMonitoring.gameStatusMethod,
              balance: broadcast.liveState.balance
            });
          }

          // Salvar estado com dados de monitoramento atualizados
          await saveState(state);
        } else {
          console.log('⚠️ Nenhum frame retornou dados de monitoramento');
        }

      } catch (monitoringError) {
        // Erro no monitoramento não quebra a funcionalidade principal
        console.warn('⚠️ Erro ao coletar monitoramento:', monitoringError.message);
      }
      // ===== FIM DA NOVA SEÇÃO =====

      // ===== NOVA SEÇÃO v18.2 (14/06): COLETA DE DADOS DE SESSÃO (dealer/round/table) =====
      // Data-driven: usa seletores de state.extractorData.data.session do extrator_completo.json.
      // Tudo opcional: se o JSON nao tiver bloco session, simplesmente nao popula sessionData
      // e o caminho legacy (deal_capture.js + latestDealMeta) continua sendo a fonte.
      const sessionConfig = state.extractorData?.data?.session || null;
      if (sessionConfig && typeof extractSessionData === 'function') {
        try {
          const sessionResults = await chrome.scripting.executeScript({
            target: { tabId: state.tabId, allFrames: true },
            func: extractSessionData,
            args: [sessionConfig, { collectCandidates: (readCount % 5 === 1) }]
          });

          const combinedSession = (typeof combineSessionFrames === 'function')
            ? combineSessionFrames(sessionResults)
            : (function () {
                const out = { dealer: null, round_id: null, table: null, frameUrl: null };
                for (const r of (sessionResults || [])) {
                  const d = r && r.result;
                  if (!d) continue;
                  if (!out.dealer && d.dealer) out.dealer = d.dealer;
                  if (!out.round_id && d.round_id) out.round_id = d.round_id;
                  if (!out.table && d.table) out.table = d.table;
                  if (!out.frameUrl && d.frameUrl) out.frameUrl = d.frameUrl;
                }
                return out;
              })();

          if (combinedSession.dealer || combinedSession.round_id || combinedSession.table) {
            state.sessionData = {
              dealer: combinedSession.dealer,
              round_id: combinedSession.round_id,
              table: combinedSession.table,
              frameUrl: combinedSession.frameUrl,
              lastUpdate: new Date().toISOString()
            };
            if (readCount % 10 === 1) {
              addLog('monitoring', 'Sessão capturada (data-driven)', state.sessionData);
            }
          }
          // DEAL-AUDIT 15/06: se o dealer NAO casou nenhum seletor, logar os candidatos
          // do DOM (coletados sob demanda) para afinar evolution.json > data.session.dealer
          // sem chute. Aparece nos logs da Escuta (popup) a cada ~5 leituras.
          if (!combinedSession.dealer && Array.isArray(combinedSession.dealerCandidates)
              && combinedSession.dealerCandidates.length && readCount % 5 === 1) {
            addLog('monitoring', 'Dealer NAO capturado — candidatos no DOM (afinar seletores)', {
              frameUrl: combinedSession.frameUrl,
              candidates: combinedSession.dealerCandidates
            });
          }
        } catch (sessionError) {
          // Erro na coleta de sessão nao quebra a funcionalidade principal
          console.warn('⚠️ Erro ao coletar sessão:', sessionError.message);
        }
      }
      // ===== FIM DA SEÇÃO SESSION =====

      if (newHash !== state.lastHash && state.lastHash !== '') {
        // NOVO RESULTADO!
        const newNumber = newNumbers[0];
        // 🆕 DIR1 (sentido-fase): quantos giros novos entraram desde a última leitura
        // (antes de sobrescrever state.results). A fase do número mais recente e a próxima
        // fase derivam dessa contagem. Quando k=1 (caso normal) sendDir==currentDirection
        // e tudo fica idêntico ao comportamento anterior; só difere quando k>1 (corrige gap).
        const _prevResults = Array.isArray(state.results) ? state.results.slice() : [];
        const _novos = countNewSpins(newNumbers, _prevResults);
        const sendDir = (_novos % 2 === 1) ? currentDirection : phaseFlip(currentDirection);
        if (_novos > 1) {
          console.log(`🔄 DIR1: ${_novos} giros novos detectados — fase do envio = ${sendDir}`);
        }
        state.totalRead++;
        state.results = newNumbers.slice(0, 12);
        state.lastHash = newHash;
        state.lastUpdate = Date.now();
        state.error = null;

        // 🆕 v2.8: Armazenar resultado COM direção para exibir setas no popup
        if (!state.resultsWithDir) state.resultsWithDir = [];
        state.resultsWithDir.unshift({ numero: newNumber, direcao: sendDir });
        if (state.resultsWithDir.length > 12) {
          state.resultsWithDir = state.resultsWithDir.slice(0, 12);
        }

        console.log(`🎯 NOVO RESULTADO: ${newNumber} (Total: ${state.totalRead})`);

        // 🆕 v2.7: Enviar para servidor Python via WebSocket
        // SP-11 DEAL-01 (27/05): incluir dealer/table/provider via deal_meta capturado por content.js
        // FIX 2 (27/05 audit pos-reload): MV3 service worker dorme e perde
        // latestDealMeta. Le do storage.local.dealMeta de forma SINCRONA via await.
        let _dm = (typeof latestDealMeta === 'object' && latestDealMeta) ? latestDealMeta : null;
        if (!_dm) {
          try {
            const stored = await new Promise((res) => chrome.storage.local.get(['dealMeta'], res));
            _dm = stored.dealMeta || {};
            if (stored.dealMeta) latestDealMeta = stored.dealMeta; // re-hidrata cache
          } catch (_) { _dm = {}; }
        }
        // v18.2 (14/06): data-driven session capture tem prioridade sobre deal_capture legacy.
        // state.sessionData vem do bloco data.session do extrator_completo.json (Etapa 2-4).
        // Se nao tiver dado, cai para latestDealMeta (deal_capture.js).
        const _sd = (state.sessionData && typeof state.sessionData === 'object') ? state.sessionData : {};
        console.log('🎯 DEAL meta no envio:', { sessionData: _sd, dealMeta: _dm });
        const sent = sendToWebSocket({
          type: 'novo_resultado',
          numero: newNumber,
          direcao: sendDir,  // 🆕 v2.7 + DIR1: fase do giro (corrigida por shift local)
          trace_id: `${Date.now()}-${Math.random().toString(36).substr(2, 6)}`,  // 🆕 v3.1: ID único
          t_client: Date.now(),  // 🆕 v3.1: Timestamp cliente
          timestamp: Date.now(),
          allNumbers: newNumbers.slice(0, 12),
          monitoringData: state.monitoringData,
          dealer: _sd.dealer || _dm.dealer || null,         // SP-11 + v18.2 data-driven first
          table: _sd.table || _dm.table || null,            // SP-11 + v18.2 data-driven first
          provider: _dm.provider || null,                   // SP-11 (provider continua do deal_meta - URL-based)
          round_id: _sd.round_id || _dm.round_id || null    // SP-11 + v18.2 data-driven first
        });

        if (sent) {
          const dirLabel = sendDir === 'horario' ? '⬅️' : '➡️';
          addLog('result', `Enviado: ${newNumber} ${dirLabel}`, { wsConnected: true, direcao: sendDir });
        }

        // 📸 Vision (foto_roleta): apos enviar o numero, tira UMA foto da tela e
        // envia ao servidor para OCR (foto->dados). Gated por flag, defensivo
        // (try/catch nunca quebra o read-loop). 1 frame por giro.
        try {
          await captureAndSendFrame(state);
        } catch (e) {
          console.warn('📸 captura de frame falhou (ignorado):', e && e.message);
        }

        // 🆕 v2.8 + DIR1: a próxima fase é o oposto da fase do número recém-enviado.
        // Quando k=1 (caso normal) sendDir==currentDirection, então isto é idêntico ao
        // comportamento anterior; só difere quando k>1, corrigindo o gap de paridade.
        const previousDir = currentDirection;
        currentDirection = phaseFlip(sendDir);
        console.log(`🔄 Direção alternada: ${previousDir} → ${currentDirection} (k=${_novos})`);

        // Salvar direção no storage para sincronizar com popup
        await chrome.storage.local.set({ currentDirection: currentDirection });

        await saveState(state);

      } else if (state.lastHash === '') {
        // Primeira leitura - definir hash inicial
        state.results = newNumbers.slice(0, 12);
        state.lastHash = newHash;
        state.lastUpdate = Date.now();

        // 🆕 v2.8: Engenharia reversa de direção para histórico inicial
        // O número mais recente (índice 0) assume a direção atual
        // Os anteriores alternam retroativamente
        if (!state.resultsWithDir) state.resultsWithDir = [];
        state.resultsWithDir = [];

        let tempDir = currentDirection;
        for (let i = 0; i < newNumbers.length && i < 12; i++) {
          state.resultsWithDir.push({
            numero: newNumbers[i],
            direcao: tempDir
          });
          // Alternar para o próximo (mais antigo)
          tempDir = tempDir === 'horario' ? 'anti-horario' : 'horario';
        }

        console.log('📌 Hash inicial definido com direções retroativas:', newHash);
        console.log('   Direções atribuídas:', state.resultsWithDir.slice(0, 5).map(r => `${r.numero}${r.direcao === 'horario' ? '⬅️' : '➡️'}`).join(' '));

        // 🆕 v2.8: Enviar histórico inicial para Python processar em batch
        sendToWebSocket({
          type: 'historico_inicial',
          resultados: state.resultsWithDir
        });

        await saveState(state);
      } else {
        // Mesmo hash - apenas atualizar debug
        await saveState(state);
      }
    } else {
      // Nenhum número encontrado
      state.debug = {
        lastRead: new Date().toISOString(),
        readCount: readCount,
        elementsFound: 0,
        numbersFound: 0,
        error: 'Nenhum elemento encontrado'
      };

      if (readCount % 10 === 1) {
        console.log('⚠️ Nenhum elemento [data-role="recent-number"] encontrado');
      }

      await saveState(state);
    }

  } catch (error) {
    console.error('❌ Erro ao ler:', error.message);

    const state = await getState();

    // 🆕 v2.3: Detectar se é erro de iFrame (Evolution Gaming)
    const isIframeError = error.message.includes('Cannot access') ||
      error.message.includes('frame') ||
      error.message.includes('Execution context') ||
      error.message.includes('No frame');

    state.debug = {
      lastRead: new Date().toISOString(),
      error: error.message,
      isIframeError: isIframeError,
      suggestion: isIframeError ?
        'iFrame indisponível - Aguarde "FAÇAM SUAS APOSTAS"' :
        'Erro geral de leitura'
    };

    // Se erro de iFrame nas primeiras leituras, apenas logar
    if (isIframeError && readCount <= 5) {
      console.log('⚠️ iFrame temporariamente indisponível, aguardando próxima fase de apostas...');
    }

    await saveState(state);
  }
}

// ===== FUNÇÃO INJETADA NA PÁGINA =====
function extractResultsFromPage() {
  const numbers = [];
  const elements = document.querySelectorAll('[data-role="recent-number"]');

  for (const el of elements) {
    let value = null;

    // Método 1: data-role="number-X"
    const numberEl = el.querySelector('[data-role^="number-"]');
    if (numberEl) {
      const dataRole = numberEl.getAttribute('data-role');
      const match = dataRole.match(/number-(\d+)/);
      if (match) {
        value = parseInt(match[1]);
      }
    }

    // Método 2: classe que contém "value"
    if (value === null) {
      const valueEl = el.querySelector('[class*="value"]');
      if (valueEl) {
        const text = valueEl.textContent.trim();
        const parsed = parseInt(text);
        if (!isNaN(parsed)) {
          value = parsed;
        }
      }
    }

    // Método 3: texto direto do elemento
    if (value === null) {
      const text = el.textContent.trim();
      const parsed = parseInt(text);
      if (!isNaN(parsed) && parsed >= 0 && parsed <= 36) {
        value = parsed;
      }
    }

    if (value !== null && !isNaN(value) && value >= 0 && value <= 36) {
      numbers.push(value);
    }
  }

  return {
    numbers: numbers,
    elementsFound: elements.length
  };
}

// ===== NOVA FUNÇÃO - EXTRAÇÃO DE DADOS DE MONITORAMENTO =====
// 🆕 v2.5: Implementação completa com 3 métodos de detecção de status
function extractMonitoringData(monitoringConfig) {
  const monitoring = {
    gameStatus: null,
    gameStatusRaw: null,
    gameStatusMethod: null,
    isOpen: null,
    balance: null,
    currentBet: null,
    activeChip: null,
    frameUrl: window.location.href,
    debug: {}
  };

  try {
    // =====================================================
    // MÉTODO 1: Texto do Semáforo (trafficLightText)
    // =====================================================
    const textSelectors = [
      '[class*="trafficLightText"]',
      '[class*="statusMessage"]',
      '[class*="betting-status"]',
      '[class*="game-status"]',
      '[data-role="game-message"]',
      '[class*="StatusMessage"]',
      '[class*="betStatus"]'
    ];

    let statusText = null;
    let statusMethod = null;

    for (const sel of textSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const text = (el.innerText || el.textContent || '').trim();
        if (text && text.length > 3) {
          statusText = text;
          statusMethod = 'TEXT:' + sel;
          monitoring.debug.textSelector = sel;
          monitoring.debug.textFound = text;
          break;
        }
      }
    }

    // =====================================================
    // MÉTODO 2: Bloqueio de Chips (MAIS CONFIÁVEL!)
    // Se os chips estão bloqueados, apostas estão fechadas
    // =====================================================
    const chipWrapperSelectors = [
      "[data-role='chip-stack-wrapper']",
      "[class*='chip-stack']",
      "[class*='chipStack']",
      "[class*='ChipStack']"
    ];

    let chipBlocked = null;
    for (const sel of chipWrapperSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const className = el.className || '';
        const style = el.getAttribute('style') || '';

        // Verifica se tem classe de bloqueio ou pointer-events: none
        const hasBlockClass = className.includes('prevent') ||
          className.includes('blocked') ||
          className.includes('disabled');
        const hasBlockStyle = style.includes('pointer-events') &&
          style.includes('none');

        chipBlocked = hasBlockClass || hasBlockStyle;
        monitoring.debug.chipWrapper = sel;
        monitoring.debug.chipClassName = className.substring(0, 100);
        monitoring.debug.chipBlocked = chipBlocked;

        if (!statusMethod || statusMethod.startsWith('TEXT')) {
          // Método do chip é mais confiável
          statusMethod = 'CHIP:' + sel;
        }
        break;
      }
    }

    // =====================================================
    // MÉTODO 3: Timer Visual (circle-timer)
    // Se o timer está visível e rodando, apostas abertas
    // =====================================================
    const timerSelectors = [
      "[data-role='circle-timer']",
      "[class*='circle-timer']",
      "[class*='circleTimer']",
      "[class*='betting-timer']",
      "[class*='countdown']"
    ];

    let timerVisible = null;
    for (const sel of timerSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const style = window.getComputedStyle(el);
        const display = style.display;
        const visibility = style.visibility;
        const opacity = parseFloat(style.opacity);
        const className = el.className || '';

        // Timer visível = apostas abertas
        const isVisible = display !== 'none' &&
          visibility !== 'hidden' &&
          opacity > 0.3 &&
          !className.includes('fadeOut') &&
          !className.includes('hidden');

        timerVisible = isVisible;
        monitoring.debug.timer = sel;
        monitoring.debug.timerVisible = isVisible;
        monitoring.debug.timerDisplay = display;
        monitoring.debug.timerOpacity = opacity;
        break;
      }
    }

    // =====================================================
    // DECISÃO FINAL: Combinar todos os métodos
    // =====================================================
    let isOpen = null;

    // Prioridade 1: Texto do status (se encontrado)
    if (statusText) {
      const upper = statusText.toUpperCase();
      if (upper.includes('FAÇAM') || upper.includes('PLACE') || upper.includes('ABERTO')) {
        isOpen = true;
      } else if (upper.includes('NÃO') || upper.includes('NO MORE') || upper.includes('FECHAD')) {
        isOpen = false;
      }
      monitoring.gameStatusRaw = statusText;
    }

    // Prioridade 2: Bloqueio de chips (mais confiável!)
    if (chipBlocked !== null && isOpen === null) {
      isOpen = !chipBlocked;  // Se bloqueado, NÃO está aberto
      if (!statusText) {
        statusText = chipBlocked ? 'CHIPS_BLOQUEADOS' : 'CHIPS_LIBERADOS';
      }
    }

    // Prioridade 3: Timer visual
    if (timerVisible !== null && isOpen === null) {
      isOpen = timerVisible;  // Timer visível = apostas abertas
      if (!statusText) {
        statusText = timerVisible ? 'TIMER_ATIVO' : 'TIMER_INATIVO';
      }
    }

    // Formatar status final
    if (isOpen === true) {
      monitoring.gameStatus = 'ABERTO';
    } else if (isOpen === false) {
      monitoring.gameStatus = 'FECHADO';
    } else {
      monitoring.gameStatus = 'DESCONHECIDO';
    }

    monitoring.gameStatusMethod = statusMethod;
    monitoring.isOpen = isOpen;

    // =====================================================
    // SALDO, APOSTA E FICHA (mantém lógica original)
    // =====================================================

    // 2. Saldo
    const balanceSelectors = [
      "[data-role='balance-label-value']",
      "[class*='balance-value']",
      "[class*='balanceValue']"
    ];
    for (const sel of balanceSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        monitoring.balance = el.innerText || el.textContent || null;
        break;
      }
    }

    // 3. Aposta Total
    const betSelectors = [
      "[data-role='total-bet-label-value']",
      "[class*='total-bet']",
      "[class*='totalBet']"
    ];
    for (const sel of betSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        monitoring.currentBet = el.innerText || el.textContent || null;
        break;
      }
    }

    // 4. Ficha Ativa
    const chipSelectors = [
      "[data-role='selected-chip'] [data-role='chip']",
      "[class*='selected-chip'] [data-role='chip']",
      "[class*='activeChip']"
    ];
    for (const sel of chipSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        const dataValue = el.getAttribute('data-value');
        monitoring.activeChip = dataValue || el.innerText || el.textContent || null;
        break;
      }
    }

  } catch (e) {
    monitoring.debug.error = e.message;
    console.error('Erro ao extrair monitoramento:', e);
  }

  return monitoring;
}


// ===== EVENTOS DE ABA =====
chrome.tabs.onRemoved.addListener(async (tabId) => {
  const state = await getState();

  if (tabId === state.tabId && state.isListening) {
    console.log('🚫 Aba monitorada fechada');
    state.isListening = false;
    state.error = 'Aba fechada';
    await saveState(state);
    stopAllAlarms();
    setBadge(''); // limpa o badge (achado #2)
  }
  await unsuppressTab(tabId); // limpa supressão da aba fechada (após o teardown)
});

console.log('🎧 Background v2.6 (Persistente) pronto');
