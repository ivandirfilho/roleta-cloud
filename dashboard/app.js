// Roleta Cloud Dashboard - Real-time WebSocket Client

const WS_URL = 'wss://roleta.xma-ia.com:8765';
const RECONNECT_INTERVAL = 5000;

// State
let ws = null;
let reconnectAttempts = 0;
let metrics = {
    totalSpins: 0,
    suggestions: 0,
    betCount: 0,
    skipCount: 0,
    timelineCW: 0,
    timelineCCW: 0,
    lastSpin: null
};
let logs = [];

// DOM Elements
const elements = {
    statusIndicator: document.getElementById('status-indicator'),
    uptime: document.getElementById('uptime'),
    connections: document.getElementById('connections'),
    memory: document.getElementById('memory'),
    totalSpins: document.getElementById('total-spins'),
    suggestions: document.getElementById('suggestions'),
    betCount: document.getElementById('bet-count'),
    skipCount: document.getElementById('skip-count'),
    timelineCW: document.getElementById('timeline-cw'),
    timelineCCW: document.getElementById('timeline-ccw'),
    lastSpin: document.getElementById('last-spin'),
    logsContainer: document.getElementById('logs-container'),
    logCount: document.getElementById('log-count'),
    lastUpdate: document.getElementById('last-update'),
    btnRefresh: document.getElementById('btn-refresh')
};

// WebSocket Connection
function connect() {
    addLog('info', 'Conectando ao servidor...');

    try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            reconnectAttempts = 0;
            updateStatus(true);
            addLog('success', '✅ Conectado ao servidor');

            // Request initial state
            ws.send(JSON.stringify({ type: 'get_state' }));
        };

        ws.onclose = () => {
            updateStatus(false);
            addLog('warning', '🔌 Desconectado');
            scheduleReconnect();
        };

        ws.onerror = (error) => {
            addLog('error', '❌ Erro de conexão');
            console.error('WebSocket error:', error);
        };

        ws.onmessage = (event) => {
            handleMessage(JSON.parse(event.data));
        };

    } catch (error) {
        addLog('error', `❌ Falha ao conectar: ${error.message}`);
        scheduleReconnect();
    }
}

function scheduleReconnect() {
    if (reconnectAttempts < 10) {
        reconnectAttempts++;
        addLog('info', `🔄 Reconectando em ${RECONNECT_INTERVAL / 1000}s (${reconnectAttempts}/10)`);
        setTimeout(connect, RECONNECT_INTERVAL);
    }
}

function handleMessage(data) {
    const type = data.type;

    if (type === 'sugestao') {
        const sugestao = data.data;
        metrics.suggestions++;
        metrics.totalSpins++;

        if (sugestao.acao === 'APOSTAR') {
            metrics.betCount++;
            addLog('success', `🎯 APOSTAR: centro ${sugestao.centro} - ${sugestao.regiao}`);
        } else {
            metrics.skipCount++;
            addLog('info', `⏸️ PULAR: score insuficiente`);
        }

        metrics.lastSpin = {
            numero: sugestao.ultimo_numero,
            acao: sugestao.acao,
            timestamp: Date.now()
        };

        updateUI();
    }
    else if (type === 'ack') {
        addLog('info', `✅ ${data.message}`);
    }
    else if (type === 'state') {
        // Update from server state
        if (data.timeline_cw) metrics.timelineCW = data.timeline_cw;
        if (data.timeline_ccw) metrics.timelineCCW = data.timeline_ccw;
        updateUI();
    }
    else if (type === 'error') {
        addLog('error', `❌ ${data.message}`);
    }
}

// UI Updates
function updateStatus(online) {
    elements.statusIndicator.className = `status ${online ? 'online' : 'offline'}`;
    elements.statusIndicator.textContent = online ? '● ONLINE' : '● OFFLINE';
}

function updateUI() {
    elements.totalSpins.textContent = metrics.totalSpins;
    elements.suggestions.textContent = metrics.suggestions;
    elements.betCount.textContent = metrics.betCount;
    elements.skipCount.textContent = metrics.skipCount;
    elements.timelineCW.textContent = `${metrics.timelineCW} forças`;
    elements.timelineCCW.textContent = `${metrics.timelineCCW} forças`;

    if (metrics.lastSpin) {
        const ago = Math.round((Date.now() - metrics.lastSpin.timestamp) / 1000);
        elements.lastSpin.textContent = `${metrics.lastSpin.numero} (${metrics.lastSpin.acao}) há ${ago}s`;
    }

    elements.lastUpdate.textContent = new Date().toLocaleTimeString();
}

function addLog(type, message) {
    const timestamp = new Date().toLocaleTimeString();
    logs.unshift({ type, message, timestamp });

    // Keep last 50 logs
    if (logs.length > 50) logs.pop();

    renderLogs();
}

function renderLogs() {
    elements.logsContainer.innerHTML = logs
        .map(log => `<div class="log-entry ${log.type}">[${log.timestamp}] ${log.message}</div>`)
        .join('');

    elements.logCount.textContent = `(${logs.length})`;
}

// Events
elements.btnRefresh.addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'get_state' }));
        addLog('info', '🔄 Solicitando atualização...');
    } else {
        connect();
    }
});

// Init
document.addEventListener('DOMContentLoaded', () => {
    addLog('info', '🎰 Dashboard iniciado');
    connect();

    // Update relative times every second
    setInterval(updateUI, 1000);
});
