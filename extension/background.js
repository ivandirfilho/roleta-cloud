// Escuta Beat v2.7 - Background Service Worker
// 🆕 v2.7: Integração WebSocket com RoletaV11
// 🆕 v2.6: CORREÇÃO DE PERSISTÊNCIA - Usa chrome.alarms em vez de setInterval
// Compatível com Extrator Beat v17.1

console.log('🎧 Escuta Beat v2.7 - Background iniciado (Persistente + WebSocket!)');


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
  currentMesa: null,
  mesaConfig: null
};

// 🆕 v2.6: Removido readIntervalId - não persiste em MV3 Service Workers
// Agora usa chrome.alarms para persistência
let readCount = 0;

// 🆕 v2.7: Direção atual do giro (definida pelo usuário no popup)
let currentDirection = 'horario';

// ===== 🆕 v2.7: WEBSOCKET CLIENT PARA INTEGRAÇÃO =====
const WS_CONFIG = {
  url: 'wss://roleta.xma-ia.com:8765',
  reconnectInterval: 5000,  // 5 segundos entre reconexões
  maxReconnectAttempts: 10
};

let wsConnection = null;
let wsReconnectAttempts = 0;
let wsConnected = false;

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


function connectWebSocket() {
  if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
    return; // Já conectado
  }

  try {
    console.log('🔌 Conectando ao servidor WebSocket...');
    wsConnection = new WebSocket(WS_CONFIG.url);

    wsConnection.onopen = async () => {
      console.log('✅ WebSocket conectado ao servidor Python');
      wsConnected = true;
      wsReconnectAttempts = 0;

      // 🆕 v3.5: Enviar registro com device_id
      const deviceId = await getDeviceId();
      wsConnection.send(JSON.stringify({
        type: 'register',
        device_id: deviceId
      }));

      addLog('success', 'WebSocket conectado', { url: WS_CONFIG.url, device_id: deviceId });
      notifyConnectionStatus(true); // 🆕 v3.0: Notificar overlay
    };

    wsConnection.onclose = () => {
      console.log('🔌 WebSocket desconectado');
      wsConnected = false;
      wsConnection = null;
      notifyConnectionStatus(false); // 🆕 v3.0: Notificar overlay

      // Tentar reconectar se ainda estiver escutando
      scheduleReconnect();
    };

    wsConnection.onerror = (error) => {
      console.warn('⚠️ Erro WebSocket:', error);
      wsConnected = false;
    };

    wsConnection.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'ack') {
          console.log('✅ Servidor confirmou recebimento:', data.received);
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
          // Enviar para o content script para manter overlay sincronizado
          sendStateSyncToContentScript(data.data);
        }
        else if (data.type === 'sessao_resetada') {
          // 🆕 v3.3: Resposta de reset de sessão
          console.log('✅ Sessão resetada pelo servidor:', data.data);
          addLog('success', 'Sessão resetada', data.data);
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
  setTimeout(() => {
    getState().then(state => {
      if (state.isListening) {
        console.log(`🔄 Tentativa de reconexão ${wsReconnectAttempts}/${WS_CONFIG.maxReconnectAttempts}`);
        connectWebSocket();
      }
    });
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
    // Throttle: só envia se mudou algo
    const hash = JSON.stringify(stateData);
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
chrome.runtime.onInstalled.addListener(() => {
  console.log('Extensão instalada/atualizada');
  chrome.storage.local.set({ escutaState: DEFAULT_STATE });
});

// 🆕 v2.6: Listener para quando o Chrome inicia
chrome.runtime.onStartup.addListener(async () => {
  console.log('🔄 Chrome iniciou - verificando estado...');
  const state = await getState();
  if (state.isListening && state.tabId) {
    console.log('🔄 Retomando escuta após startup do Chrome');
    startReadLoopAlarm();
  }
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

// Listener para mensagens do popup e content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  const action = request.action;

  if (action === 'getState') {
    getState().then(sendResponse);
    return true; // Assíncrono
  }

  // 🆕 v3.0: Microserviço - Listar mesas
  if (action === 'listarMesas') {
    if (!wsConnected) connectWebSocket();
    sendToWebSocket({ type: 'listar_mesas' });

    // Como o retorno do WS é assíncrono, o popup deve ouvir 'updateMesas'
    // Mas para facilitar o sendMessage inicial, vamos apenas confirmar o disparo
    sendResponse({ success: true });
    return true;
  }

  // 🆕 v3.0: Microserviço - Obter config
  if (action === 'obterConfigMesa') {
    sendToWebSocket({ type: 'obter_config_mesa', mesa_id: request.mesa_id });
    sendResponse({ success: true });
    return true;
  }

  // 🆕 v3.0: Microserviço - Capturar DOM remoto
  if (action === 'capturarMesa') {
    capturarMesaRemota().then(sendResponse);
    return true;
  }
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
  // 🆕 v2.6: Alarm principal para leitura (substitui setInterval)
  if (alarm.name === 'readLoop') {
    const state = await getState();
    if (state.isListening && state.tabId) {
      readResults();
    } else {
      // Parar se não está mais escutando
      stopReadLoopAlarm();
    }
    return;
  }

  // Keep-alive para garantir que worker não durma
  if (alarm.name === 'keepAlive') {
    const state = await getState();
    console.log('⏰ Keep-alive - isListening:', state.isListening, 'tabId:', state.tabId);

    if (state.isListening && state.tabId) {
      // Garantir que o alarm de leitura existe
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

// 🆕 v2.6: Removido setInterval - não persiste em MV3
// A verificação agora é feita pelo alarm keepAlive

// ===== MENSAGENS DO POPUP =====
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('📩 Mensagem:', message.action, 'de:', sender.tab?.id || 'popup');

  handleMessage(message, sender).then(response => {
    sendResponse(response);
  }).catch(err => {
    console.error('Erro ao processar mensagem:', err);
    sendResponse({ success: false, error: err.message });
  });

  return true;
});

async function handleMessage(message, sender = null) {
  const { action } = message;

  if (action === 'setExtractorData') {
    const state = await getState();
    state.extractorData = message.data;
    state.error = null;

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

    // 🆕 v3.1: CORREÇÃO BUG #2 - Se não tem extractorData, usa template base automaticamente
    if (!state.extractorData) {
      console.log('⚠️ Sem extractorData - usando template base do Evolution');

      // Template base mínimo para funcionar
      state.extractorData = {
        provider: 'evolution',
        version: '1.0',
        selectors: {
          results: "[data-role='recent-number']",
          gameStatus: "[class*='trafficLightText']",
          balance: "[data-role='balance-label-value']",
          totalBet: "[data-role='total-bet-label-value']",
          chips: "[data-role='chip']",
          chipWrapper: "[data-role='chip-stack-wrapper']"
        }
      };

      addLog('info', 'Template base Evolution carregado automaticamente');
    }

    state.isListening = true;
    // 🆕 v4.0: Usar sender.tab.id como fallback se tabId não for passado (ex: control_panel.js)
    state.tabId = message.tabId || sender?.tab?.id || state.tabId;
    state.error = null;
    state.lastUpdate = Date.now();
    readCount = 0;

    await saveState(state);

    // 🆕 v2.6: Usar alarms persistentes
    startReadLoopAlarm();
    startKeepAliveAlarm();

    // 🆕 v2.7: Conectar ao servidor WebSocket
    connectWebSocket();

    // 🆕 v4.0: Broadcast para atualizar UIs
    broadcastToTabs({ action: 'stateSync', data: { isListening: true } });

    console.log('✅ Escuta iniciada para tab:', state.tabId);
    return { success: true };
  }

  if (action === 'stopListening') {
    const state = await getState();
    state.isListening = false;
    state.error = null;

    await saveState(state);

    // 🆕 v2.6: Parar todos os alarms
    stopAllAlarms();

    // 🆕 v2.7: Desconectar WebSocket
    closeWebSocket();

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

      if (newHash !== state.lastHash && state.lastHash !== '') {
        // NOVO RESULTADO!
        const newNumber = newNumbers[0];
        state.totalRead++;
        state.results = newNumbers.slice(0, 12);
        state.lastHash = newHash;
        state.lastUpdate = Date.now();
        state.error = null;

        // 🆕 v2.8: Armazenar resultado COM direção para exibir setas no popup
        if (!state.resultsWithDir) state.resultsWithDir = [];
        state.resultsWithDir.unshift({ numero: newNumber, direcao: currentDirection });
        if (state.resultsWithDir.length > 12) {
          state.resultsWithDir = state.resultsWithDir.slice(0, 12);
        }

        console.log(`🎯 NOVO RESULTADO: ${newNumber} (Total: ${state.totalRead})`);

        // 🆕 v2.7: Enviar para servidor Python via WebSocket
        const sent = sendToWebSocket({
          type: 'novo_resultado',
          numero: newNumber,
          direcao: currentDirection,  // 🆕 v2.7: Direção do giro
          trace_id: `${Date.now()}-${Math.random().toString(36).substr(2, 6)}`,  // 🆕 v3.1: ID único
          t_client: Date.now(),  // 🆕 v3.1: Timestamp cliente
          timestamp: Date.now(),
          allNumbers: newNumbers.slice(0, 12),
          monitoringData: state.monitoringData
        });

        if (sent) {
          const dirLabel = currentDirection === 'horario' ? '⬅️' : '➡️';
          addLog('result', `Enviado: ${newNumber} ${dirLabel}`, { wsConnected: true, direcao: currentDirection });
        }

        // 🆕 v2.8: Auto-alternar direção após cada jogada
        const previousDir = currentDirection;
        currentDirection = currentDirection === 'horario' ? 'anti-horario' : 'horario';
        console.log(`🔄 Direção alternada: ${previousDir} → ${currentDirection}`);

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
  }
});

console.log('🎧 Background v2.6 (Persistente) pronto');
