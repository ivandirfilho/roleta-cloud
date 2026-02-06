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

// ===== CRIAR OVERLAY =====
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

  // Touch para arrastar (mobile)
  setupDrag(overlay);

  console.log('✅ Overlay criado');
  return overlay;
}

// ===== TOGGLE MINIMIZAR =====
function toggleMinimize() {
  const overlay = document.getElementById('escuta-beat-overlay');
  if (!overlay) return;

  overlayState.isMinimized = !overlayState.isMinimized;
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
function init() {
  // Criar overlay se ainda não existe
  createOverlay();

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
