// Escuta Beat v2.5 - Popup
// Compatível com Extrator Beat v17.1 + Detecção de Status Aprimorada


let currentTab = null;
let isConnected = false;

// Mapa de cores da roleta
const numberColors = {
  0: 'green',
  1: 'red', 2: 'black', 3: 'red', 4: 'black', 5: 'red', 6: 'black',
  7: 'red', 8: 'black', 9: 'red', 10: 'black', 11: 'black', 12: 'red',
  13: 'black', 14: 'red', 15: 'black', 16: 'red', 17: 'black', 18: 'red',
  19: 'red', 20: 'black', 21: 'red', 22: 'black', 23: 'red', 24: 'black',
  25: 'red', 26: 'black', 27: 'red', 28: 'black', 29: 'black', 30: 'red',
  31: 'black', 32: 'red', 33: 'black', 34: 'red', 35: 'black', 36: 'red'
};

// Formatador de moeda BRL
function formatCurrency(value) {
  if (value === null || value === undefined || isNaN(value)) {
    return 'R$ 0,00';
  }
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(value);
}

// Elementos DOM
let indicator, connectionStatus, connectionUrl;
let btnStart, btnStop;
let resultsGrid, listeningIndicator;
let infoFile, infoLast, infoTotal, logEl;
let painelStatus, statusLight, statusText;
let saldoValue, apostaValue, fichaValue;
let mesaDropdown, btnCapturar;

// 🆕 v2.7: Direção do giro
let currentDirection = 'horario';
let btnDirHorario, btnDirAntiHorario;
let btnLoad; // Manual fallback

// ===== INICIALIZAÇÃO =====
document.addEventListener('DOMContentLoaded', async () => {
  // Pegar elementos DOM
  indicator = document.getElementById('indicator');
  connectionStatus = document.getElementById('connectionStatus');
  connectionUrl = document.getElementById('connectionUrl');
  btnStart = document.getElementById('btnStart');
  btnStop = document.getElementById('btnStop');
  resultsGrid = document.getElementById('resultsGrid');
  listeningIndicator = document.getElementById('listeningIndicator');
  infoFile = document.getElementById('infoFile');
  infoLast = document.getElementById('infoLast');
  infoTotal = document.getElementById('infoTotal');
  logEl = document.getElementById('log');

  // Elementos do painel de status
  painelStatus = document.getElementById('painelStatus');
  statusLight = document.getElementById('statusLight');
  statusText = document.getElementById('statusText');
  saldoValue = document.getElementById('saldoValue');
  apostaValue = document.getElementById('apostaValue');
  fichaValue = document.getElementById('fichaValue');

  // Elementos da mesa
  mesaDropdown = document.getElementById('mesaDropdown');
  btnCapturar = document.getElementById('btnCapturar');

  // Event listeners
  if (btnCapturar) btnCapturar.addEventListener('click', captureMesa);
  if (mesaDropdown) mesaDropdown.addEventListener('change', onMesaSelected);

  // Fallback Manual
  btnLoad = document.getElementById('btnLoad');
  if (btnLoad) btnLoad.addEventListener('click', loadExtractorFile);

  btnStart.addEventListener('click', startListening);
  btnStop.addEventListener('click', stopListening);

  // Carregar mesas do servidor
  carregarMesas();

  // 🆕 v2.4: Botão exportar logs
  const btnExportLogs = document.getElementById('btnExportLogs');
  if (btnExportLogs) {
    btnExportLogs.addEventListener('click', exportLogs);
  }

  // 🆕 v2.7: Botões de direção
  btnDirHorario = document.getElementById('btnDirHorario');
  btnDirAntiHorario = document.getElementById('btnDirAntiHorario');

  if (btnDirHorario && btnDirAntiHorario) {
    btnDirHorario.addEventListener('click', () => setDirection('horario'));
    btnDirAntiHorario.addEventListener('click', () => setDirection('anti-horario'));
  }

  // Carregar direção salva
  const savedDir = await chrome.storage.local.get(['currentDirection']);
  if (savedDir.currentDirection) {
    setDirection(savedDir.currentDirection, false);
  }

  // Conectar à aba
  await connectToTab();

  // 🆕 v3.3: inicializar auto-detecção / auto-start
  await initAutoStart();

  // Carregar estado do storage
  await loadStateFromStorage();

  // Escutar mudanças no storage
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === 'local' && changes.escutaState) {
      updateUIFromState(changes.escutaState.newValue);
    }
    // 🆕 v2.8: Sincronizar direção quando background alterna automaticamente
    if (area === 'local' && changes.currentDirection) {
      const newDir = changes.currentDirection.newValue;
      if (newDir && newDir !== currentDirection) {
        setDirection(newDir, false);  // Atualizar UI sem logar
      }
    }
  });

  // Escutar mensagens do background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.action === 'updateMesas') {
      atualizarDropdownMesas(message.mesas);
    }
    else if (message.action === 'mesaConfigurada') {
      log(`✅ Mesa configurada: ${message.data.mesa_id}`, 'success');
      btnCapturar.disabled = false;
      btnCapturar.textContent = '📸';
      btnStart.disabled = false;
      infoFile.textContent = message.data.mesa_id;
    }
  });

  log('Sistema pronto v3.0 (Microserviço)', 'info');
});


// ===== AUTO-START / ZERO-UPLOAD (v3.3) =====
let autoProviderEl, autoStartToggleEl, autoStatusEl;

async function initAutoStart() {
  autoProviderEl = document.getElementById('autoProvider');
  autoStartToggleEl = document.getElementById('autoStartToggle');
  autoStatusEl = document.getElementById('autoStatus');

  // Versão dinâmica no header (PP-06)
  try {
    const ver = document.getElementById('appVersion');
    if (ver) ver.textContent = 'v' + chrome.runtime.getManifest().version + ' · auto-start';
  } catch (e) { /* noop */ }

  // Carregar política atual
  let policy = 'auto';
  try {
    const resp = await chrome.runtime.sendMessage({ action: 'getAutoStartPolicy' });
    if (resp && resp.policy) policy = resp.policy;
  } catch (e) { /* background pode estar dormindo */ }
  if (autoStartToggleEl) autoStartToggleEl.checked = policy !== 'off';

  // Toggle: liga/desliga auto-start
  if (autoStartToggleEl) {
    autoStartToggleEl.addEventListener('change', async () => {
      const newPolicy = autoStartToggleEl.checked ? 'auto' : 'off';
      try { await chrome.runtime.sendMessage({ action: 'setAutoStartPolicy', policy: newPolicy }); } catch (e) {}
      log(`Auto-start ${newPolicy === 'auto' ? 'ligado' : 'desligado'}`, 'info');
      if (newPolicy === 'auto') triggerAutoStart(true); // ação explícita do operador
    });
  }

  await refreshAutoProvider();
  if (policy === 'auto') triggerAutoStart(false); // abertura do popup respeita STOP manual
}

async function refreshAutoProvider() {
  if (!autoProviderEl || !currentTab) return;
  try {
    const resp = await chrome.runtime.sendMessage({
      action: 'detectProvider', tabId: currentTab.id, url: currentTab.url,
    });
    const det = resp && resp.detection;
    if (det && det.providerId) {
      const name = det.providerId.charAt(0).toUpperCase() + det.providerId.slice(1);
      autoProviderEl.textContent = `${name} detectado`;
      if (autoStatusEl) {
        autoStatusEl.textContent = `Confiança ${(det.confidence * 100).toFixed(0)}% — manifest empacotado, sem upload.`;
      }
    } else {
      autoProviderEl.textContent = 'Nenhuma roleta conhecida';
      if (autoStatusEl) autoStatusEl.textContent = 'Abra a mesa de roleta — ou use o modo manual abaixo.';
    }
  } catch (e) {
    autoProviderEl.textContent = 'Detecção indisponível';
  }
}

async function triggerAutoStart(force = false) {
  if (!currentTab) return;
  try {
    await chrome.runtime.sendMessage({
      action: 'triggerAutoStart', tabId: currentTab.id, url: currentTab.url, force: !!force,
    });
  } catch (e) { /* idempotente; background tentará via webNavigation */ }
}

// ===== FALLBACK: CARREGAR ARQUIVO DO EXTRATOR =====
async function loadExtractorFile() {
  if (!btnLoad) return;

  btnLoad.disabled = true;
  const originalText = btnLoad.textContent;
  btnLoad.textContent = '⏳ Carregando...';

  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';

  input.onchange = async (e) => {
    // Restaurar botão se cancelar
    if (!e.target.files.length) {
      btnLoad.disabled = false;
      btnLoad.textContent = originalText;
      return;
    }

    const file = e.target.files[0];

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      // Validação Flexível (Extrator Beat v15+ ou config genérica)
      const isValidExtractor = data._meta && data._meta.service === 'ExtractorBeat';
      const isValidBase = data.selectors || (data.data?.results);

      if (!isValidExtractor && !isValidBase) {
        throw new Error('Arquivo JSON inválido (use Extrator Beat v15+)');
      }

      // Preparar novo estado COM LIMPEZA DA MESA SERVIDOR (PRIORIDADE MANUAL)
      const currentData = await chrome.storage.local.get(['escutaState']);
      const state = currentData.escutaState || {};

      state.currentMesa = null; // Remove seleção de mesa do servidor
      if (mesaDropdown) mesaDropdown.value = "";

      state.extractorData = data;
      state.error = null;

      // Importar histórico se disponível
      if (data.data?.results?.lastNumbers) {
        state.results = data.data.results.lastNumbers.slice(0, 12);
        state.lastHash = state.results.slice(0, 5).join(',');
      }

      await chrome.storage.local.set({ escutaState: state });

      // Atualizar UI
      infoFile.textContent = file.name;
      btnStart.disabled = false;
      log(`✅ Arquivo carregado: ${file.name}`, 'success');

      // Feedback visual imediato
      if (state.results && state.results.length > 0) {
        updateResultsDisplay(state.results);
        infoLast.textContent = state.results[0];
      }

    } catch (err) {
      log(`❌ Erro: ${err.message}`, 'error');
    } finally {
      btnLoad.disabled = false;
      btnLoad.textContent = originalText;
    }
  };

  input.click();
}

// Funções auxiliares
function atualizarDropdownMesas(mesas) {
  if (!mesaDropdown || !mesas) return;
  mesaDropdown.innerHTML = '<option value="">-- Selecione Mesa Salva --</option>';
  mesas.forEach(mesa => {
    const option = document.createElement('option');
    option.value = mesa.id;
    option.textContent = mesa.name;
    mesaDropdown.appendChild(option);
  });
}

// ===== LOG =====
function log(message, type = 'info') {
  const entry = document.createElement('div');
  entry.className = `log-entry ${type}`;
  const time = new Date().toLocaleTimeString('pt-BR');
  entry.textContent = `[${time}] ${message}`;
  logEl.insertBefore(entry, logEl.firstChild);

  while (logEl.children.length > 30) {
    logEl.removeChild(logEl.lastChild);
  }
}

// 🆕 v2.7: Função para alternar direção
async function setDirection(dir, notify = true) {
  currentDirection = dir;

  // Atualizar visual dos botões
  if (dir === 'horario') {
    btnDirHorario.style.background = '#00aaff';
    btnDirHorario.style.color = '#000';
    btnDirHorario.style.borderColor = '#00aaff';
    btnDirAntiHorario.style.background = '#222';
    btnDirAntiHorario.style.color = '#888';
    btnDirAntiHorario.style.borderColor = '#444';
  } else {
    btnDirAntiHorario.style.background = '#ff6600';
    btnDirAntiHorario.style.color = '#000';
    btnDirAntiHorario.style.borderColor = '#ff6600';
    btnDirHorario.style.background = '#222';
    btnDirHorario.style.color = '#888';
    btnDirHorario.style.borderColor = '#444';
  }

  // Salvar no storage
  await chrome.storage.local.set({ currentDirection: dir });

  // Notificar background
  // 🔧 Adicionar manual: notify para distinguir clique manual de sync automático
  try {
    await chrome.runtime.sendMessage({ action: 'setDirection', direction: dir, manual: notify });
  } catch (e) {
    // Background pode estar dormindo
  }

  if (notify) {
    const dirLabel = dir === 'horario' ? '⬅️ Horário' : '➡️ Anti-Horário';
    log(`Direção alterada: ${dirLabel}`, 'info');
  }
}

// ===== CONECTAR À ABA =====
async function connectToTab() {
  indicator.className = 'indicator';
  connectionStatus.textContent = 'Conectando...';
  connectionUrl.textContent = '-';

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab) {
      throw new Error('Nenhuma aba ativa');
    }

    currentTab = tab;

    if (tab.url.startsWith('chrome://') || tab.url.startsWith('chrome-extension://')) {
      indicator.className = 'indicator error';
      connectionStatus.textContent = '❌ Página do Chrome';
      connectionUrl.textContent = 'Abra um site de apostas';
      log('Abra um site de apostas primeiro', 'error');
      return;
    }

    indicator.className = 'indicator connected';
    connectionStatus.textContent = '✅ CONECTADO';
    connectionUrl.textContent = tab.url;
    isConnected = true;

    log(`Conectado: ${tab.title}`, 'success');

  } catch (error) {
    indicator.className = 'indicator error';
    connectionStatus.textContent = '❌ Erro';
    connectionUrl.textContent = error.message;
    log(`Erro: ${error.message}`, 'error');
  }
}

// ===== CARREGAR ESTADO DO STORAGE =====
async function loadStateFromStorage() {
  try {
    const data = await chrome.storage.local.get(['escutaState']);
    if (data.escutaState) {
      updateUIFromState(data.escutaState);
    }
  } catch (e) {
    console.log('Erro ao carregar estado:', e);
  }
}

// ===== ATUALIZAR UI A PARTIR DO ESTADO =====
function updateUIFromState(state) {
  if (!state) return;

  // Atualizar indicador de escuta
  if (state.isListening) {
    indicator.className = 'indicator listening';
    connectionStatus.textContent = '👂 ESCUTANDO...';
    listeningIndicator.classList.add('active');
    btnStop.style.display = 'block';
    if (btnCapturar) btnCapturar.disabled = true;
    if (mesaDropdown) mesaDropdown.disabled = true;
    if (btnLoad) btnLoad.disabled = true; // 🔒 Bloquear upload durante escuta
  } else {
    listeningIndicator.classList.remove('active');
    btnStart.style.display = 'block';
    btnStop.style.display = 'none';
    if (btnCapturar) btnCapturar.disabled = false;
    if (mesaDropdown) mesaDropdown.disabled = false;

    // Habilitar upload apenas se não estiver carregando
    if (btnLoad && btnLoad.textContent !== '⏳ Carregando...') {
      btnLoad.disabled = false;
    }

    if (isConnected) {
      indicator.className = 'indicator connected';
      connectionStatus.textContent = '✅ CONECTADO';
    }
  }

  // Habilitar botão iniciar se tem dados (manual ou servidor)
  if (state.extractorData || state.currentMesa) {
    btnStart.disabled = false;

    // Mostrar fonte de dados
    if (state.isListening) {
      infoFile.textContent = state.currentMesa || 'Arquivo Manual';
    } else {
      if (state.currentMesa) {
        infoFile.textContent = `Mesa: ${state.currentMesa}`;
      } else if (state.extractorData) {
        infoFile.textContent = 'Arquivo Manual Carregado';
      } else {
        infoFile.textContent = 'Nenhum';
      }
    }
  }

  // Atualizar resultados - preferir resultsWithDir para mostrar setas
  // 🆕 v2.8: Usar resultsWithDir que inclui direção de cada número
  if (state.resultsWithDir && state.resultsWithDir.length > 0) {
    updateResultsDisplay(state.resultsWithDir);
    infoLast.textContent = state.resultsWithDir[0].numero;
  } else if (state.results && state.results.length > 0) {
    updateResultsDisplay(state.results);
    infoLast.textContent = state.results[0];
  }

  // Atualizar contador
  infoTotal.textContent = state.totalRead || 0;

  // Mostrar debug se disponível
  if (state.debug) {
    if (state.debug.elementsFound !== undefined) {
      log(`Debug: ${state.debug.elementsFound} elementos, ${state.debug.numbersFound} números`, 'info');
    }
    if (state.debug.error) {
      // 🆕 v2.3: Aviso específico para iFrame
      if (state.debug.isIframeError) {
        log(`⚠️ iFrame indisponível - Aguarde "FAÇAM SUAS APOSTAS"`, 'error');
      } else {
        log(`Debug erro: ${state.debug.error}`, 'error');
      }
    }
  }

  // ===== ATUALIZAR PAINEL DE STATUS (Dashboard) =====
  // Dashboard sempre visível - atualiza valores quando há dados
  if (painelStatus && state.monitoringData) {
    // 1. Traffic Light - Status do Jogo
    // 🆕 v2.5: Usar isOpen diretamente (já vem processado do background)
    const isOpen = state.monitoringData.isOpen;
    const status = state.monitoringData.gameStatus || 'DESCONHECIDO';

    if (isOpen === true) {
      statusLight.className = 'status-box status-open';
      statusText.textContent = '🎯 PODE APOSTAR!';
      statusLight.querySelector('.status-icon').textContent = '🟢';
    } else if (isOpen === false) {
      statusLight.className = 'status-box status-closed';
      statusText.textContent = 'FECHADO';
      statusLight.querySelector('.status-icon').textContent = '🔴';
    } else {
      statusLight.className = 'status-box status-waiting';
      statusText.textContent = 'AGUARDANDO...';
      statusLight.querySelector('.status-icon').textContent = '⏳';
    }

    // 2. Área Financeira - Saldo e Aposta
    if (state.monitoringData.balance !== undefined) {
      saldoValue.textContent = formatCurrency(state.monitoringData.balance);
    }

    if (state.monitoringData.currentBet !== undefined) {
      apostaValue.textContent = formatCurrency(state.monitoringData.currentBet);
    }

    // 3. Ficha Ativa
    if (state.monitoringData.activeChip !== undefined && state.monitoringData.activeChip !== null) {
      fichaValue.textContent = formatCurrency(state.monitoringData.activeChip);
    } else {
      fichaValue.textContent = '-';
    }
  }
  // Painel permanece visível sempre (valores padrão estão no HTML)
}


// ===== MESA SELECTION & CAPTURE (v3.0) =====

async function carregarMesas() {
  if (!mesaDropdown) return;

  try {
    const response = await chrome.runtime.sendMessage({ action: 'listarMesas' });
    if (response && response.mesas) {
      mesaDropdown.innerHTML = '<option value="">-- Selecione Mesa Salva --</option>';
      response.mesas.forEach(mesa => {
        const option = document.createElement('option');
        option.value = mesa.id;
        option.textContent = mesa.name;
        mesaDropdown.appendChild(option);
      });

      // Tentar selecionar a mesa atual do storage
      const data = await chrome.storage.local.get(['escutaState']);
      if (data.escutaState && data.escutaState.currentMesa) {
        mesaDropdown.value = data.escutaState.currentMesa;
      }
    } else {
      mesaDropdown.innerHTML = '<option value="">Sem mesas (servidor offline?)</option>';
    }
  } catch (e) {
    console.warn('Erro ao listar mesas:', e);
    mesaDropdown.innerHTML = '<option value="">Erro ao carregar</option>';
  }
}

async function onMesaSelected() {
  const mesaId = mesaDropdown.value;
  if (!mesaId) {
    // Se selecionou vazio, resetar
    infoFile.textContent = 'Nenhum';
    btnStart.disabled = true;
    return;
  }

  log(`Mesa selecionada: ${mesaId}`, 'info');

  // Limpar indicador de arquivo manual
  infoFile.textContent = "Carregando configuração...";

  // Solicitar config da mesa para o servidor
  btnStart.disabled = true;
  chrome.runtime.sendMessage({ action: 'obterConfigMesa', mesa_id: mesaId });
}

async function captureMesa() {
  if (!isConnected || !currentTab) {
    log('Conecte a uma aba primeiro', 'error');
    return;
  }

  log('Iniciando captura remota...', 'info');
  btnCapturar.disabled = true;
  btnCapturar.textContent = '⏳';

  try {
    const response = await chrome.runtime.sendMessage({ action: 'capturarMesa' });
    if (response && response.success) {
      log('✅ Captura enviada para o servidor!', 'success');
    }
  } catch (e) {
    log(`❌ Erro ao capturar: ${e.message}`, 'error');
    btnCapturar.disabled = false;
    btnCapturar.textContent = '📸';
  }
}

// ===== INICIAR ESCUTA =====
async function startListening() {
  if (!isConnected || !currentTab) {
    log('Conecte a uma aba primeiro', 'error');
    return;
  }

  log('Iniciando escuta...', 'info');
  btnStart.disabled = true;

  // Verificar se tem dados (Manual ou Servidor)
  const data = await chrome.storage.local.get(['escutaState']);
  const state = data.escutaState || {};

  // HÍBRIDO: Aceita extractorData (Manual) OU currentMesa (Servidor)
  if (!state.extractorData && !state.currentMesa) {
    log('❌ Selecione uma mesa OU carregue um arquivo', 'error');
    btnStart.disabled = false;
    return;
  }

  // Atualizar estado no storage
  state.isListening = true;
  state.tabId = currentTab.id;
  state.error = null;
  state.lastUpdate = Date.now();

  await chrome.storage.local.set({ escutaState: state });

  log('✅ Estado salvo no storage', 'success');

  // Tentar notificar background para iniciar loop
  try {
    const response = await chrome.runtime.sendMessage({
      action: 'startListening',
      tabId: currentTab.id
    });

    if (response && response.success) {
      log('✅ Escuta iniciada! Pode fechar o popup.', 'success');
    } else {
      log('⚠️ Background não confirmou, mas estado foi salvo', 'info');
    }
  } catch (e) {
    // Background pode estar dormindo
    log('⚠️ Background dormindo, alarm vai acordar em até 30s', 'info');
  }

  // Atualizar UI
  updateUIFromState(state);
}

// ===== PARAR ESCUTA =====
async function stopListening() {
  // Atualizar storage direto
  const data = await chrome.storage.local.get(['escutaState']);
  const state = data.escutaState || {};
  state.isListening = false;
  state.error = null;

  await chrome.storage.local.set({ escutaState: state });

  log('Escuta parada', 'info');

  // Tentar notificar background
  try {
    await chrome.runtime.sendMessage({ action: 'stopListening' });
  } catch (e) {
    // Não é problema
  }

  // Atualizar UI
  updateUIFromState(state);
}

// ===== ATUALIZAR DISPLAY DE RESULTADOS =====
// 🆕 v2.8: Aceita array de {numero, direcao} ou array simples de números
function updateResultsDisplay(resultsList) {
  if (!resultsGrid) return;

  resultsGrid.innerHTML = '';

  for (let i = 0; i < 12; i++) {
    const div = document.createElement('div');

    if (resultsList && i < resultsList.length) {
      let num, direcao;

      // Verificar se é objeto {numero, direcao} ou número simples
      if (typeof resultsList[i] === 'object' && resultsList[i].numero !== undefined) {
        num = resultsList[i].numero;
        direcao = resultsList[i].direcao;
      } else {
        num = resultsList[i];
        direcao = null;
      }

      const color = numberColors[num] || 'black';

      div.className = `result-number ${color}`;
      div.style.position = 'relative';
      div.style.paddingTop = '8px';

      // 🆕 v2.8: Adicionar seta de direção
      if (direcao) {
        const arrow = document.createElement('div');
        arrow.style.cssText = 'position: absolute; top: -2px; left: 50%; transform: translateX(-50%); font-size: 10px; opacity: 0.8;';
        arrow.textContent = direcao === 'horario' ? '⬅️' : '➡️';
        div.appendChild(arrow);
      }

      const numSpan = document.createElement('span');
      numSpan.textContent = num;
      div.appendChild(numSpan);

    } else {
      div.className = 'result-number placeholder';
      div.textContent = '-';
    }

    resultsGrid.appendChild(div);
  }
}

// 🆕 v2.4: Função para exportar logs
async function exportLogs() {
  log('Exportando logs...', 'info');

  try {
    const response = await chrome.runtime.sendMessage({ action: 'exportLogs' });

    if (response && response.success) {
      const data = response.data;

      // Criar blob e baixar
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);

      const now = new Date();
      const filename = `escuta_beat_logs_${now.toISOString().slice(0, 10)}_${now.toTimeString().slice(0, 5).replace(':', '-')}.json`;

      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();

      URL.revokeObjectURL(url);

      log(`✅ Logs exportados: ${data.totalLogs} registros`, 'success');
    } else {
      log('❌ Erro ao exportar logs', 'error');
    }
  } catch (e) {
    log(`❌ Erro: ${e.message}`, 'error');
  }
}
