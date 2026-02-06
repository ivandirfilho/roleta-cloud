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
let btnLoad, btnStart, btnStop;
let resultsGrid, listeningIndicator;
let infoFile, infoLast, infoTotal, logEl;
let painelStatus, statusLight, statusText;
let saldoValue, apostaValue, fichaValue;

// 🆕 v2.7: Direção do giro
let currentDirection = 'horario';
let btnDirHorario, btnDirAntiHorario;

// ===== INICIALIZAÇÃO =====
document.addEventListener('DOMContentLoaded', async () => {
  // Pegar elementos
  indicator = document.getElementById('indicator');
  connectionStatus = document.getElementById('connectionStatus');
  connectionUrl = document.getElementById('connectionUrl');
  btnLoad = document.getElementById('btnLoad');
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

  // Event listeners
  btnLoad.addEventListener('click', loadExtractorFile);
  btnStart.addEventListener('click', startListening);
  btnStop.addEventListener('click', stopListening);

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

  log('Sistema pronto v2.8 (Auto-Alterna)', 'info');
});

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
    btnStart.style.display = 'none';
    btnStop.style.display = 'block';
    btnLoad.disabled = true;
  } else {
    listeningIndicator.classList.remove('active');
    btnStart.style.display = 'block';
    btnStop.style.display = 'none';
    btnLoad.disabled = false;

    if (isConnected) {
      indicator.className = 'indicator connected';
      connectionStatus.textContent = '✅ CONECTADO';
    }
  }

  // Habilitar botão iniciar se tem dados
  if (state.extractorData) {
    btnStart.disabled = false;
    infoFile.textContent = 'Carregado ✓';
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


// ===== CARREGAR ARQUIVO DO EXTRATOR =====
async function loadExtractorFile() {
  btnLoad.disabled = true;
  btnLoad.textContent = '⏳ Carregando...';

  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';

  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) {
      btnLoad.disabled = false;
      btnLoad.textContent = '📂 CARREGAR ARQUIVO DO EXTRATOR BEAT';
      return;
    }

    try {
      const text = await file.text();
      const data = JSON.parse(text);

      // Validar arquivo
      if (!data._meta || data._meta.service !== 'ExtractorBeat') {
        throw new Error('Arquivo não é do Extrator Beat');
      }

      if (!data.data || !data.data.results) {
        throw new Error('Arquivo não contém dados de resultados');
      }

      // Salvar direto no storage (mais confiável)
      const currentState = (await chrome.storage.local.get(['escutaState'])).escutaState || {};
      currentState.extractorData = data;
      currentState.error = null;

      if (data.data.results.lastNumbers) {
        currentState.results = data.data.results.lastNumbers.slice(0, 12);
        currentState.lastHash = currentState.results.slice(0, 5).join(',');
      }

      await chrome.storage.local.set({ escutaState: currentState });

      infoFile.textContent = file.name;
      btnStart.disabled = false;
      log(`✅ Arquivo carregado: ${file.name}`, 'success');

      if (data.data.results.lastNumbers) {
        updateResultsDisplay(data.data.results.lastNumbers.slice(0, 12));
      }

      // Notificar background (opcional, pode falhar)
      try {
        await chrome.runtime.sendMessage({ action: 'setExtractorData', data: data });
      } catch (e) {
        // Background pode estar dormindo, não é problema
      }

    } catch (err) {
      log(`❌ Erro: ${err.message}`, 'error');
    }

    btnLoad.disabled = false;
    btnLoad.textContent = '📂 CARREGAR ARQUIVO DO EXTRATOR BEAT';
  };

  input.click();
}

// ===== INICIAR ESCUTA =====
async function startListening() {
  if (!isConnected || !currentTab) {
    log('Conecte a uma aba primeiro', 'error');
    return;
  }

  log('Iniciando escuta...', 'info');
  btnStart.disabled = true;

  // Verificar se tem dados do extrator
  const data = await chrome.storage.local.get(['escutaState']);
  const state = data.escutaState || {};

  if (!state.extractorData) {
    log('❌ Carregue o arquivo do Extrator primeiro', 'error');
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
