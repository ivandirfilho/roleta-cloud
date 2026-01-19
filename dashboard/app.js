// Roleta Cloud - Glass Box Dashboard JavaScript

const WS_URL = 'wss://roleta.xma-ia.com:8765';
const RECONNECT_INTERVAL = 5000;
const MAX_LOGS = 50;

let ws = null;
let reconnectAttempts = 0;

// State
const state = {
    spins: 0, betCount: 0, skipCount: 0,
    timelineCW: 0, timelineCCW: 0,
    lastSpin: null, lastResult: null,
    logs: [], currentFilter: 'all'
};

// DOM Elements
const el = {
    status: document.getElementById('status-indicator'),
    latency: document.getElementById('latency'),
    flowNodes: {
        escuta: document.getElementById('flow-escuta'),
        server: document.getElementById('flow-server'),
        sda: document.getElementById('flow-sda'),
        overlay: document.getElementById('flow-overlay')
    },
    arrows: [
        document.getElementById('arrow-1'),
        document.getElementById('arrow-2'),
        document.getElementById('arrow-3')
    ],
    spinNumber: document.getElementById('spin-number'),
    spinDirection: document.getElementById('spin-direction'),
    spinForce: document.getElementById('spin-force'),
    spinLatency: document.getElementById('spin-latency'),
    resultCard: document.getElementById('result-card'),
    resultAction: document.getElementById('result-action'),
    resultCenter: document.getElementById('result-center'),
    resultScore: document.getElementById('result-score'),
    resultRegion: document.getElementById('result-region'),
    barCW: document.getElementById('bar-cw'),
    barCCW: document.getElementById('bar-ccw'),
    countCW: document.getElementById('count-cw'),
    countCCW: document.getElementById('count-ccw'),
    metricSpins: document.getElementById('metric-spins'),
    metricBet: document.getElementById('metric-bet'),
    metricSkip: document.getElementById('metric-skip'),
    metricRate: document.getElementById('metric-rate'),
    traceId: document.getElementById('trace-id'),
    traceSteps: document.getElementById('trace-steps'),
    logsContainer: document.getElementById('logs-container'),
    logCount: document.getElementById('log-count'),
    lastUpdate: document.getElementById('last-update')
};

// WebSocket
function connect() {
    addLog('info', 'Conectando ao servidor...');

    try {
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            reconnectAttempts = 0;
            updateStatus(true);
            addLog('info', '✅ Conectado');
            animateFlow('escuta', true);
            ws.send(JSON.stringify({ type: 'get_state' }));
        };

        ws.onclose = () => {
            updateStatus(false);
            addLog('error', '🔌 Desconectado');
            resetFlow();
            setTimeout(connect, RECONNECT_INTERVAL);
        };

        ws.onerror = () => addLog('error', '❌ Erro de conexão');
        ws.onmessage = (e) => handleMessage(JSON.parse(e.data));

    } catch (err) {
        addLog('error', `Falha: ${err.message}`);
        setTimeout(connect, RECONNECT_INTERVAL);
    }
}

function handleMessage(data) {
    if (data.type === 'trace') {
        handleTrace(data);
    } else if (data.type === 'sugestao') {
        handleSuggestion(data.data);
    } else if (data.type === 'state') {
        handleState(data);
    } else if (data.type === 'ack') {
        addLog('info', `✅ ${data.message}`);
    }
}

function handleTrace(data) {
    state.spins++;
    state.lastSpin = data.spin;
    state.lastResult = data.result;

    // Update timeline
    state.timelineCW = data.state.timeline_cw;
    state.timelineCCW = data.state.timeline_ccw;

    // Count actions
    if (data.result.acao === 'APOSTAR') state.betCount++;
    else state.skipCount++;

    // Animate flow
    animateFlowSequence();

    // Update UI
    updateSpinDisplay(data.spin, data.total_ms);
    updateResultDisplay(data.result);
    updateTimeline();
    updateMetrics();
    updateTraceSteps(data);

    // Log
    const dir = data.spin.direcao === 'horario' ? '⬅️' : '➡️';
    addLog('spin', `${data.spin.numero} ${dir} → força ${data.spin.force}`);
    addLog('result', `${data.result.acao} centro ${data.result.centro} (score: ${data.result.score})`);

    el.latency.textContent = `${data.total_ms}ms`;
}

function handleSuggestion(data) {
    // From overlay connection - lighter update
    if (!state.lastResult || state.lastResult.trace_id !== data.trace_id) {
        state.spins++;
        if (data.acao === 'APOSTAR') state.betCount++;
        else state.skipCount++;
        updateMetrics();
    }
}

function handleState(data) {
    state.timelineCW = data.timeline_cw || 0;
    state.timelineCCW = data.timeline_ccw || 0;
    updateTimeline();
    addLog('info', `Estado: CW=${state.timelineCW}, CCW=${state.timelineCCW}`);
}

// UI Updates
function updateStatus(online) {
    el.status.className = `status ${online ? 'online' : 'offline'}`;
    el.status.textContent = online ? '● ONLINE' : '● OFFLINE';
}

function updateSpinDisplay(spin, ms) {
    el.spinNumber.textContent = spin.numero;
    el.spinDirection.textContent = spin.direcao === 'horario' ? '⬅️' : '➡️';
    el.spinForce.textContent = spin.force;
    el.spinLatency.textContent = `${ms}ms`;
}

function updateResultDisplay(result) {
    const isApostar = result.acao === 'APOSTAR';
    el.resultCard.className = `card result-card ${isApostar ? 'apostar' : 'pular'}`;
    el.resultAction.className = `result-action ${isApostar ? 'apostar' : 'pular'}`;
    el.resultAction.textContent = result.acao;
    el.resultCenter.textContent = result.centro;
    el.resultScore.textContent = `${result.score}/6`;
    el.resultRegion.textContent = result.numeros?.join(', ') || '--';
}

function updateTimeline() {
    const maxForces = 20;
    el.barCW.style.width = `${Math.min(state.timelineCW / maxForces * 100, 100)}%`;
    el.barCCW.style.width = `${Math.min(state.timelineCCW / maxForces * 100, 100)}%`;
    el.countCW.textContent = state.timelineCW;
    el.countCCW.textContent = state.timelineCCW;
}

function updateMetrics() {
    el.metricSpins.textContent = state.spins;
    el.metricBet.textContent = state.betCount;
    el.metricSkip.textContent = state.skipCount;
    const rate = state.spins > 0 ? Math.round(state.betCount / state.spins * 100) : 0;
    el.metricRate.textContent = `${rate}%`;
}

function updateTraceSteps(data) {
    el.traceId.textContent = `[${data.trace_id.substring(0, 12)}...]`;
    el.traceSteps.innerHTML = data.steps.map(step => `
        <div class="trace-step">
            <span class="trace-step-name">${step.name}</span>
            <span class="trace-step-data">${JSON.stringify(step.data || {})}</span>
        </div>
    `).join('');
}

// Flow Animation
function animateFlow(node, active) {
    Object.values(el.flowNodes).forEach(n => n.classList.remove('active', 'success'));
    el.arrows.forEach(a => a.classList.remove('active'));

    if (active && el.flowNodes[node]) {
        el.flowNodes[node].classList.add('active');
    }
}

function animateFlowSequence() {
    const nodes = ['escuta', 'server', 'sda', 'overlay'];
    let i = 0;

    const animate = () => {
        if (i > 0) el.flowNodes[nodes[i - 1]].classList.replace('active', 'success');
        if (i > 0) el.arrows[i - 1].classList.add('active');
        if (i < nodes.length) {
            el.flowNodes[nodes[i]].classList.add('active');
            i++;
            setTimeout(animate, 150);
        }
    };

    animateFlow(null, false);
    animate();
}

function resetFlow() {
    Object.values(el.flowNodes).forEach(n => {
        n.classList.remove('active', 'success');
        n.querySelector('.flow-status').textContent = '--';
    });
    el.arrows.forEach(a => a.classList.remove('active'));
}

// Logs
function addLog(type, message) {
    const timestamp = new Date().toLocaleTimeString();
    state.logs.unshift({ type, message, timestamp });
    if (state.logs.length > MAX_LOGS) state.logs.pop();
    renderLogs();
    el.lastUpdate.textContent = timestamp;
}

function renderLogs() {
    const filtered = state.currentFilter === 'all'
        ? state.logs
        : state.logs.filter(l => l.type === state.currentFilter);

    el.logsContainer.innerHTML = filtered.map(log =>
        `<div class="log-entry ${log.type}">[${log.timestamp}] ${log.message}</div>`
    ).join('');

    el.logCount.textContent = `(${state.logs.length})`;
}

// Filter buttons
document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.currentFilter = btn.dataset.filter;
        renderLogs();
    });
});

// Init
document.addEventListener('DOMContentLoaded', () => {
    addLog('info', '🎰 Dashboard Glass Box iniciado');
    connect();
});
