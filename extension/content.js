// Escuta Beat - Content Script v3.4
// Gerencia o overlay de sugestões na página
// Otimizado para Android/Kiwi Browser
// 🆕 v3.4: Sistema MASTER/SLAVE

console.log('🎯 Escuta Beat Overlay v3.4 carregado');

// ===== ESTADO DO OVERLAY =====
let overlayState = {
  isMinimized: false,
  lastSugestao: null,
  isVisible: true,
  deviceRole: 'unknown'  // 🆕 v3.4: 'master' | 'slave' | 'unknown'
};

// 🆕 v4.0: Carregar estado salvo de UI
async function loadUIState() {
  try {
    const data = await chrome.storage.local.get(['overlayUIState']);
    if (data.overlayUIState) {
      overlayState.isMinimized = data.overlayUIState.isMinimized || false;
      console.log('📦 Estado de UI carregado:', overlayState.isMinimized ? 'minimizado' : 'expandido');
    }
  } catch (e) {
    console.warn('⚠️ Não foi possível carregar estado de UI');
  }
}

async function saveUIState() {
  try {
    await chrome.storage.local.set({ overlayUIState: { isMinimized: overlayState.isMinimized } });
  } catch (e) {
    // Ignora erro
  }
}

// ===== CRIAR OVERLAY UNIFICADO =====
function createOverlay() {
  // Verificar se já existe
  if (document.getElementById('escuta-beat-overlay')) {
    return document.getElementById('escuta-beat-overlay');
  }

  const overlay = document.createElement('div');
  overlay.id = 'escuta-beat-overlay';
  overlay.innerHTML = `
    <div class="eb-panel aguardando">
      <div class="eb-header">
        <span class="eb-status aguardando">⏳ AGUARDANDO</span>
        <span class="eb-role" id="eb-role" title="Modo de conexão">⚡</span>
        <div class="eb-header-buttons">
          <button class="eb-new-session" title="Nova Sessão (Novo Dealer)">🔄</button>
          <button class="eb-force-master" id="eb-force-master" title="Forçar MASTER" style="display:none">🎯</button>
          <button class="eb-minimize" title="Minimizar">−</button>
        </div>
      </div>
      <div class="eb-body">
        <div class="eb-row">
          <span class="eb-label">Último</span>
          <span class="eb-value" id="eb-ultimo">--</span>
        </div>
        <div class="eb-region" id="eb-regiao">
          Aguardando dados...
        </div>
        <div class="eb-row">
          <span class="eb-label">Gale</span>
          <span class="eb-gale-display g1" id="eb-gale-display">G1 0/0</span>
        </div>
        <div class="eb-row">
          <span class="eb-label">Aposta</span>
          <span class="eb-value">
            R$ <span id="eb-aposta">17</span>
          </span>
        </div>
        <div class="eb-confidence">
          <div class="eb-confidence-bar" id="eb-confidence-bar" style="width: 0%"></div>
        </div>
        <div class="eb-timer" id="eb-timer">Conectando...</div>
      </div>
      
      <!-- 🆕 v4.0: Botão de Controle Integrado -->
      <button class="eb-control-toggle" id="eb-control-toggle" title="Abrir Painel de Controle">
        🎛️ Controles
      </button>
      
      <!-- 🆕 v5.0: Seção de Controles (igual ao popup) -->
      <div class="eb-control-section" id="eb-control-section">
        <div class="eb-control-header">
          <span>⚙️ PAINEL DE CONTROLE</span>
        </div>
        
        <!-- Status de Conexão -->
        <div class="eb-ctrl-connection">
          <div class="eb-ctrl-led" id="eb-ctrl-indicator"></div>
          <div class="eb-ctrl-conn-info">
            <span id="eb-ctrl-status-text">Desconectado</span>
            <small id="eb-ctrl-url">ws://servidor:8765</small>
          </div>
        </div>
        
        <!-- Seleção de Mesa -->
        <div class="eb-control-row">
          <div class="eb-control-label">MESA</div>
          <div class="eb-ctrl-mesa-row">
            <select id="eb-ctrl-mesa" class="eb-control-select">
              <option value="">-- Selecione --</option>
            </select>
            <button id="eb-ctrl-capture" class="eb-ctrl-icon-btn" title="Capturar Mesa">📸</button>
          </div>
        </div>
        
        <!-- Botões de Ação -->
        <div class="eb-control-actions">
          <button id="eb-ctrl-start" class="eb-ctrl-btn start">▶️ INICIAR</button>
          <button id="eb-ctrl-stop" class="eb-ctrl-btn stop" disabled>⏹️ PARAR</button>
        </div>
        
        <!-- Grid de Resultados -->
        <div class="eb-control-row">
          <div class="eb-control-label">ÚLTIMOS RESULTADOS</div>
          <div class="eb-ctrl-results" id="eb-ctrl-results">
            <!-- Preenchido dinamicamente -->
          </div>
        </div>
        
        <!-- Timestamp -->
        <div class="eb-control-time">
          Última leitura: <span id="eb-ctrl-time">--</span>
        </div>
      </div>

    </div>
  `;

  document.body.appendChild(overlay);

  // Adicionar eventos
  const minimizeBtn = overlay.querySelector('.eb-minimize');
  minimizeBtn.addEventListener('click', toggleMinimize);

  // Botão Nova Sessão (reset de dealer)
  const newSessionBtn = overlay.querySelector('.eb-new-session');
  newSessionBtn.addEventListener('click', handleNewSession);

  // 🎯 Botão Forçar MASTER
  const forceMasterBtn = overlay.querySelector('.eb-force-master');
  forceMasterBtn.addEventListener('click', handleForceMaster);

  // 🆕 v4.0: Botão de Controles
  const controlToggleBtn = overlay.querySelector('#eb-control-toggle');
  controlToggleBtn.addEventListener('click', toggleControlSection);

  // 🆕 v4.0: Eventos do painel de controle
  document.getElementById('eb-ctrl-start').addEventListener('click', async () => {
    const btn = document.getElementById('eb-ctrl-start');
    const btnStop = document.getElementById('eb-ctrl-stop');

    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = '⏳ Iniciando...';

    try {
      // 🆕 v3.1: CORREÇÃO BUG #7 - Verificar se já tem configuração
      const stateResponse = await chrome.runtime.sendMessage({ action: 'getState' });

      if (!stateResponse?.extractorData) {
        // Precisa capturar primeiro
        console.log('📸 Sem config - iniciando captura automática');
        btn.textContent = '📸 Capturando mesa...';

        const captureResponse = await chrome.runtime.sendMessage({ action: 'capturarMesa' });

        if (!captureResponse?.success) {
          throw new Error('Falha na captura da mesa');
        }

        // Aguardar resposta do servidor (mesa_configurada vai iniciar automaticamente via auto_start)
        btn.textContent = '⏳ Aguardando servidor...';
        console.log('✅ Captura enviada - aguardando mesa_configurada');

        // Timeout de segurança - atualizar UI após 3s
        setTimeout(() => {
          chrome.runtime.sendMessage({ action: 'getState' }, (state) => {
            updateControlUI(state);
            if (state?.isListening) {
              btn.style.display = 'none';
              btnStop.style.display = 'block';
              btnStop.disabled = false;
            } else {
              btn.disabled = false;
              btn.textContent = originalText;
            }
          });
        }, 3000);

        return;
      }

      // Já tem config, apenas iniciar
      console.log('▶️ Iniciando escuta com config existente');
      chrome.runtime.sendMessage({ action: 'startListening' }, (response) => {
        updateControlUI(response);
        if (response?.success) {
          btn.style.display = 'none';
          btnStop.style.display = 'block';
          btnStop.disabled = false;
        } else {
          btn.disabled = false;
          btn.textContent = '❌ ERRO';
          setTimeout(() => { btn.textContent = originalText; }, 2000);
        }
      });

    } catch (error) {
      console.error('❌ Erro ao iniciar:', error);
      btn.disabled = false;
      btn.textContent = '❌ ERRO';
      setTimeout(() => { btn.textContent = originalText; }, 2000);
    }
  });

  document.getElementById('eb-ctrl-stop').addEventListener('click', () => {
    chrome.runtime.sendMessage({ action: 'stopListening' }, updateControlUI);
  });

  document.getElementById('eb-ctrl-mesa').addEventListener('change', (e) => {
    if (e.target.value) {
      chrome.runtime.sendMessage({ action: 'obterConfigMesa', mesa_id: e.target.value });
    }
  });

  // 🆕 v5.0: Botão Capturar Mesa
  document.getElementById('eb-ctrl-capture').addEventListener('click', () => {
    const btn = document.getElementById('eb-ctrl-capture');
    btn.disabled = true;
    btn.textContent = '⏳';
    chrome.runtime.sendMessage({ action: 'capturarMesa' }, (response) => {
      btn.disabled = false;
      btn.textContent = '📸';
      if (response?.success) {
        console.log('✅ Mesa capturada');
      }
    });
  });

  // Carregar estado inicial dos controles
  chrome.runtime.sendMessage({ action: 'getState' }, updateControlUI);
  chrome.runtime.sendMessage({ action: 'listarMesas' });


  // Touch para arrastar (mobile)
  setupDrag(overlay);

  console.log('✅ Overlay unificado criado');
  return overlay;
}

// 🆕 v4.0: Toggle da seção de controles
let controlSectionExpanded = false;

function toggleControlSection() {
  const section = document.getElementById('eb-control-section');
  const btn = document.getElementById('eb-control-toggle');
  if (!section || !btn) return;

  controlSectionExpanded = !controlSectionExpanded;

  if (controlSectionExpanded) {
    section.classList.add('expanded');
    btn.textContent = '🎛️ Fechar Controles';
    chrome.runtime.sendMessage({ action: 'getState' }, updateControlUI);
  } else {
    section.classList.remove('expanded');
    btn.textContent = '🎛️ Controles';
  }
}

function updateControlUI(state) {
  if (!state) return;

  const indicator = document.getElementById('eb-ctrl-indicator');
  const statusText = document.getElementById('eb-ctrl-status-text');
  const urlEl = document.getElementById('eb-ctrl-url');
  const btnStart = document.getElementById('eb-ctrl-start');
  const btnStop = document.getElementById('eb-ctrl-stop');
  const timeEl = document.getElementById('eb-ctrl-time');
  const resultsEl = document.getElementById('eb-ctrl-results');

  // Status LED
  if (indicator) {
    indicator.className = 'eb-ctrl-led';
    if (state.isListening) {
      indicator.classList.add('listening');
    } else if (state.isConnected) {
      indicator.classList.add('connected');
    }
  }

  // Status text
  if (statusText) {
    statusText.textContent = state.isListening ? 'ESCUTANDO' : (state.isConnected ? 'CONECTADO' : 'DESCONECTADO');
  }

  // URL do servidor
  if (urlEl && state.wsUrl) {
    urlEl.textContent = state.wsUrl;
  }

  // Botões
  if (btnStart) {
    btnStart.disabled = state.isListening;
    btnStart.style.opacity = state.isListening ? '0.5' : '1';
  }
  if (btnStop) {
    btnStop.disabled = !state.isListening;
    btnStop.style.opacity = state.isListening ? '1' : '0.5';
  }

  // Timestamp
  if (timeEl && state.lastUpdate) {
    timeEl.textContent = new Date(state.lastUpdate).toLocaleTimeString();
  } else if (timeEl) {
    timeEl.textContent = new Date().toLocaleTimeString();
  }

  // Grid de resultados
  if (resultsEl && state.results && state.results.length > 0) {
    const last10 = state.results.slice(-10);
    resultsEl.innerHTML = last10.map(num => {
      const color = getNumberColor(num);
      return `<span class="eb-result-num ${color}">${num}</span>`;
    }).join('');
  }
}

// Mapa de cores da roleta
function getNumberColor(num) {
  const reds = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36];
  if (num === 0) return 'green';
  return reds.includes(num) ? 'red' : 'black';
}


function updateControlMesas(mesas) {
  const select = document.getElementById('eb-ctrl-mesa');
  if (!select || !mesas) return;

  const current = select.value;
  select.innerHTML = '<option value="">-- Selecione --</option>';
  mesas.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.name;
    select.appendChild(opt);
  });
  select.value = current;
}

// ===== TOGGLE MINIMIZAR =====
function toggleMinimize() {
  console.log('🔽 toggleMinimize chamado');
  const overlay = document.getElementById('escuta-beat-overlay');
  if (!overlay) return;

  overlayState.isMinimized = !overlayState.isMinimized;
  saveUIState(); // 🆕 v4.0: Persistir estado

  const status = overlay.querySelector('.eb-status');
  const galeDisplay = overlay.querySelector('#eb-gale-display');

  if (overlayState.isMinimized) {
    overlay.classList.add('minimized');
    // Quando minimizado, mostrar [centro] + gale no status
    if (status && galeDisplay && overlayState.lastSugestao) {
      const centro = overlayState.lastSugestao.centro ?? '--';
      const galeText = galeDisplay.textContent;
      status.textContent = `[${centro}] ${galeText}`;
      // Copiar classe de cor
      status.classList.remove('g1', 'g2', 'g3', 'apostar', 'pular', 'aguardando');
      if (galeDisplay.classList.contains('g1')) status.classList.add('g1');
      if (galeDisplay.classList.contains('g2')) status.classList.add('g2');
      if (galeDisplay.classList.contains('g3')) status.classList.add('g3');
    }
  } else {
    overlay.classList.remove('minimized');
    // Quando expandido, restaurar status original
    if (status && overlayState.lastSugestao) {
      const acao = overlayState.lastSugestao.acao || 'AGUARDAR';
      status.classList.remove('g1', 'g2', 'g3');
      if (acao === 'APOSTAR') {
        status.classList.add('apostar');
        status.textContent = '🎯 APOSTAR';
      } else if (acao === 'PULAR') {
        status.classList.add('pular');
        status.textContent = '⏸️ PULAR';
      } else {
        status.classList.add('aguardando');
        status.textContent = '⏳ AGUARDANDO';
      }
    }
  }
}

// ===== ARRASTAR OVERLAY =====
function setupDrag(overlay) {
  let isDragging = false;
  let startX, startY, startRight, startTop;

  overlay.addEventListener('touchstart', (e) => {
    if (e.target.classList.contains('eb-minimize')) return;
    isDragging = true;
    const touch = e.touches[0];
    startX = touch.clientX;
    startY = touch.clientY;
    const rect = overlay.getBoundingClientRect();
    startRight = window.innerWidth - rect.right;
    startTop = rect.top;
  }, { passive: true });

  overlay.addEventListener('touchmove', (e) => {
    if (!isDragging) return;
    const touch = e.touches[0];
    const deltaX = startX - touch.clientX;
    const deltaY = touch.clientY - startY;

    overlay.style.right = Math.max(0, startRight + deltaX) + 'px';
    overlay.style.top = Math.max(0, startTop + deltaY) + 'px';
  }, { passive: true });

  overlay.addEventListener('touchend', () => {
    isDragging = false;
  });
}

// ===== ATUALIZAR OVERLAY COM SUGESTÃO =====
function updateOverlay(sugestao) {
  const overlay = document.getElementById('escuta-beat-overlay');
  if (!overlay) {
    createOverlay();
    return updateOverlay(sugestao);
  }

  overlayState.lastSugestao = sugestao;

  const panel = overlay.querySelector('.eb-panel');
  const status = overlay.querySelector('.eb-status');
  const ultimo = overlay.querySelector('#eb-ultimo');
  const regiao = overlay.querySelector('#eb-regiao');
  const aposta = overlay.querySelector('#eb-aposta');
  const galeDisplay = overlay.querySelector('#eb-gale-display');
  const confidenceBar = overlay.querySelector('#eb-confidence-bar');
  const timer = overlay.querySelector('#eb-timer');

  // Remover classes anteriores do painel
  panel.classList.remove('apostar', 'pular', 'aguardando');
  regiao.classList.remove('apostar', 'pular');

  const acao = sugestao.acao || 'AGUARDAR';

  // Atualizar painel e região (sempre)
  if (acao === 'APOSTAR') {
    panel.classList.add('apostar');
    regiao.classList.remove('pular');
    regiao.textContent = sugestao.regiao || `Centro ${sugestao.centro}`;
  } else if (acao === 'PULAR') {
    panel.classList.add('pular');
    regiao.classList.add('pular');
    regiao.textContent = 'Sem entrada';
  } else {
    panel.classList.add('aguardando');
    regiao.textContent = 'Aguardando...';
  }

  // Atualizar status - SEMPRE mostrar [centro] + gale
  status.classList.remove('apostar', 'pular', 'aguardando', 'g1', 'g2', 'g3');

  // Sempre mostrar formato [centro] G1 2/5 no status se minimizado
  // Se expandido, mostrar a Ação (APOSTAR/PULAR)
  const centro = sugestao.centro ?? '--';
  const level = sugestao.gale_level || 1;
  const galeText = sugestao.gale_display || `G${level} 0/0`;

  if (overlayState.isMinimized) {
    status.textContent = `[${centro}] ${galeText}`;
  } else {
    if (acao === 'APOSTAR') {
      status.classList.add('apostar');
      status.textContent = '🎯 APOSTAR';
    } else if (acao === 'PULAR') {
      status.classList.add('pular');
      status.textContent = '⏸️ PULAR';
    } else {
      status.classList.add('aguardando');
      status.textContent = '⏳ AGUARDANDO';
    }
  }

  // Aplicar cor do gale
  if (level === 1) status.classList.add('g1');
  else if (level === 2) status.classList.add('g2');
  else status.classList.add('g3');


  // Último número
  ultimo.textContent = sugestao.ultimo_numero ?? '--';

  // Valor da aposta
  const valorAposta = sugestao.aposta || 17;
  if (aposta) aposta.textContent = valorAposta;

  // Atualizar gale display interno também (para consistência)
  if (galeDisplay) {
    galeDisplay.textContent = galeText;
    galeDisplay.classList.remove('g1', 'g2', 'g3');
    if (level === 1) {
      galeDisplay.classList.add('g1');
    } else if (level === 2) {
      galeDisplay.classList.add('g2');
    } else {
      galeDisplay.classList.add('g3');
    }
  }

  // Confiança
  const confianca = Math.min(100, Math.max(0, sugestao.confianca || 0));
  confidenceBar.style.width = confianca + '%';

  // Timer
  timer.textContent = `Atualizado: ${new Date().toLocaleTimeString()}`;

  // Som de alerta se APOSTAR (opcional - funciona em alguns navegadores)
  if (acao === 'APOSTAR') {
    playBeep();
  }

  console.log('📊 Overlay atualizado:', acao, sugestao.regiao, galeText);
}

// ===== BEEP DE ALERTA =====
function playBeep() {
  try {
    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.value = 880; // Hz
    oscillator.type = 'sine';
    gainNode.gain.value = 0.3;

    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.15);
  } catch (e) {
    // Ignora se não suportado
  }
}

// ===== NOVA SESSÃO (RESET) =====
function handleNewSession() {
  // Confirmação do usuário
  if (!confirm('🔄 Resetar sessão?\n\nUse quando:\n• Mudou o dealer\n• Mudou de mesa\n• Quer começar do zero\n\nTodos os históricos serão limpos.')) {
    return;
  }

  // Atualizar overlay para feedback visual
  const overlay = document.getElementById('escuta-beat-overlay');
  const status = overlay?.querySelector('.eb-status');
  const regiao = overlay?.querySelector('#eb-regiao');
  const galeDisplay = overlay?.querySelector('#eb-gale-display');
  const timer = overlay?.querySelector('#eb-timer');

  if (status) {
    status.textContent = '🔄 RESETANDO...';
    status.className = 'eb-status aguardando';
  }
  if (regiao) {
    regiao.textContent = 'Reiniciando sessão...';
  }

  // Enviar para background → servidor
  try {
    chrome.runtime.sendMessage({
      action: 'sendToServer',
      data: {
        type: 'nova_sessao',
        manter_ultimo: false
      }
    }, (response) => {
      if (chrome.runtime.lastError) {
        console.error('Erro ao enviar nova_sessao:', chrome.runtime.lastError);
        if (timer) timer.textContent = '❌ Erro ao resetar';
        return;
      }
      console.log('📤 Mensagem nova_sessao enviada');
    });
  } catch (e) {
    console.error('Erro ao enviar nova_sessao:', e);
  }
}

// ===== FORÇAR MASTER =====
function handleForceMaster() {
  if (!confirm('🎯 Tomar controle?\n\nIsso vai rebaixar o MASTER atual para que VOCÊ possa enviar os dados.')) return;

  chrome.runtime.sendMessage({
    action: 'sendToServer',
    data: { type: 'force_master' }
  });
}

// ===== HANDLER PARA RESPOSTA DE RESET =====
function handleSessionReset(data) {
  const overlay = document.getElementById('escuta-beat-overlay');
  if (!overlay) return;

  const status = overlay.querySelector('.eb-status');
  const regiao = overlay.querySelector('#eb-regiao');
  const galeDisplay = overlay.querySelector('#eb-gale-display');
  const timer = overlay.querySelector('#eb-timer');
  const aposta = overlay.querySelector('#eb-aposta');

  // Atualizar visual para estado zerado
  if (status) {
    status.textContent = '✅ SESSÃO RESETADA';
    status.className = 'eb-status aguardando';
  }
  if (regiao) {
    regiao.textContent = 'Aguardando novo dados...';
  }
  if (galeDisplay) {
    galeDisplay.textContent = 'G1 0/0';
    galeDisplay.className = 'eb-gale-display g1';
  }
  if (aposta) {
    aposta.textContent = '17';
  }
  if (timer) {
    timer.textContent = '🔄 Sessão resetada';
    timer.style.color = '#00ff88';
  }

  // Limpar estado local
  overlayState.lastSugestao = null;
  overlayState.isMinimized = false;

  console.log('✅ Sessão resetada:', data);
}

// ===== MOSTRAR STATUS DE CONEXÃO =====
function showConnectionStatus(connected) {
  const timer = document.querySelector('#eb-timer');
  if (timer) {
    if (connected) {
      timer.textContent = '🟢 Conectado ao servidor';
      timer.style.color = '#00ff88';
    } else {
      timer.textContent = '🔴 Desconectado';
      timer.style.color = '#ff4444';
    }
  }
}

// ===== LISTENER PARA MENSAGENS DO BACKGROUND =====
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('📩 Content recebeu:', message.action);

  if (message.action === 'updateOverlay') {
    updateOverlay(message.data);
    sendResponse({ success: true });
  }
  else if (message.action === 'stateSync') {
    // 🆕 v3.1: Heartbeat - sincronização de estado a cada 1s
    handleStateSync(message.data);
    sendResponse({ success: true });
  }
  else if (message.action === 'showOverlay') {
    const overlay = createOverlay();
    overlay.style.display = 'block';
    overlayState.isVisible = true;
    sendResponse({ success: true });
  }
  else if (message.action === 'hideOverlay') {
    const overlay = document.getElementById('escuta-beat-overlay');
    if (overlay) {
      overlay.style.display = 'none';
      overlayState.isVisible = false;
    }
    sendResponse({ success: true });
  }
  else if (message.action === 'connectionStatus') {
    showConnectionStatus(message.connected);
    sendResponse({ success: true });
  }
  else if (message.action === 'sessionReset') {
    // 🆕 v3.3: Resposta de reset de sessão
    handleSessionReset(message.data);
    sendResponse({ success: true });
  }
  else if (message.action === 'roleChanged') {
    // 🆕 v3.4: Mudança de role (MASTER/SLAVE)
    overlayState.deviceRole = message.role;
    updateRoleIndicator(message.role, message.reason);
    sendResponse({ success: true });
  }
  // 🆕 v4.0: Handlers para controles integrados
  else if (message.action === 'updateMesas') {
    updateControlMesas(message.mesas);
    sendResponse({ success: true });
  }
  else if (message.action === 'mesaConfigurada') {
    chrome.runtime.sendMessage({ action: 'getState' }, updateControlUI);
    sendResponse({ success: true });
  }

  return true;

});

// 🆕 v3.4: Atualiza indicador de role no overlay
function updateRoleIndicator(role, reason) {
  const indicator = document.getElementById('eb-role');
  const forceBtn = document.getElementById('eb-force-master');
  if (!indicator) return;

  overlayState.deviceRole = role;

  if (role === 'master') {
    indicator.textContent = '👑';
    indicator.title = 'MASTER - Enviando dados';
    indicator.style.color = '#ffd700';
    if (forceBtn) forceBtn.style.display = 'none';
  } else if (role === 'slave') {
    indicator.textContent = '👁️';
    indicator.title = 'VIEWER - Apenas recebendo';
    indicator.style.color = '#888';
    if (forceBtn) forceBtn.style.display = 'block';
  } else {
    indicator.textContent = '⚡';
    indicator.title = 'Conectando...';
    indicator.style.color = '#fff';
    if (forceBtn) forceBtn.style.display = 'none';
  }

  console.log(`🔄 Role atualizado: ${role} (${reason})`);
}

// 🆕 v3.2: Handler para heartbeat state_sync
// Só sincroniza Gale quando bet_placed=true (aposta real)
function handleStateSync(data) {
  const overlay = document.getElementById('escuta-beat-overlay');
  if (!overlay) return;

  // ⚠️ IMPORTANTE: Só atualizar Gale se a última ação foi APOSTAR
  // Quando PULAR, o Martingale NÃO deve ser sincronizado/contabilizado
  const betPlaced = data.bet_placed === true;

  if (betPlaced) {
    // Atualizar gale display APENAS se apostou
    const galeDisplay = overlay.querySelector('#eb-gale-display');
    if (galeDisplay && data.gale_display) {
      galeDisplay.textContent = data.gale_display;
      galeDisplay.className = `eb-gale-display g${data.gale_level || 1}`;
    }

    // Atualizar valor da aposta
    const aposta = overlay.querySelector('#eb-aposta');
    if (aposta && data.aposta) {
      aposta.textContent = data.aposta;
    }

    // Atualizar status se minimizado
    if (overlayState.isMinimized) {
      const status = overlay.querySelector('.eb-status');
      if (status && data.pending_prediction) {
        const centro = data.pending_prediction.center || '--';
        status.textContent = `[${centro}] ${data.gale_display || 'G1 0/0'}`;
        status.className = `eb-status g${data.gale_level || 1}`;
      }
    }
  }

  // Atualizar timer para mostrar que está sincronizado
  const timer = overlay.querySelector('#eb-timer');
  if (timer) {
    const statusText = betPlaced ? '🟢 Sincronizado' : '🟡 Aguardando aposta';
    timer.textContent = statusText;
    timer.style.color = betPlaced ? '#00ff88' : '#ffcc00';
  }
}

// ===== INICIALIZAÇÃO =====
async function init() {
  // 🆕 v4.0: Carregar estado salvo de UI primeiro
  await loadUIState();

  // Criar overlay se ainda não existe
  const overlay = createOverlay();

  // 🆕 v4.0: Aplicar estado salvo
  if (overlayState.isMinimized && overlay) {
    overlay.classList.add('minimized');
    console.log('📦 Overlay iniciado minimizado');
  }

  // Notificar background que estamos prontos
  try {
    chrome.runtime.sendMessage({ action: 'contentReady' }, (response) => {
      if (chrome.runtime.lastError) {
        console.log('⚠️ Background não respondeu (normal na inicialização)');
      }
    });
  } catch (e) {
    // Ignora erro se extensão não está ativa
  }
}

// Iniciar quando DOM estiver pronto
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

console.log('🎯 Escuta Beat Content Script pronto');
