// Roleta Cloud - Glass Box Dashboard JavaScript

const WS_URL = 'wss://roleta.xma-ia.com/ws';
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
    resultVerdict: document.getElementById('result-verdict'),
    resultPair: document.getElementById('result-pair'),
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
    lastUpdate: document.getElementById('last-update'),
    // Strategy & Performance
    strategyName: document.getElementById('strategy-name'),
    strategyDesc: document.getElementById('strategy-desc'),
    strategyTrend: document.getElementById('strategy-trend'),
    // SDA17 Performance (4 lists)
    perfSda17CW: document.getElementById('perf-sda17-cw'),
    perfSda17CCW: document.getElementById('perf-sda17-ccw'),
    perfRateSda17CW: document.getElementById('perf-rate-sda17-cw'),
    perfRateSda17CCW: document.getElementById('perf-rate-sda17-ccw'),
    // New: Bet Performance
    perfBetCW: document.getElementById('perf-bet-cw'),
    perfBetCCW: document.getElementById('perf-bet-ccw'),
    perfRateBetCW: document.getElementById('perf-rate-bet-cw'),
    perfRateBetCCW: document.getElementById('perf-rate-bet-ccw'),
    // New: Martingale per direction
    mgCWDisplay: document.getElementById('mg-cw-display'),
    mgCWBet: document.getElementById('mg-cw-bet'),
    mgCCWDisplay: document.getElementById('mg-ccw-display'),
    mgCCWBet: document.getElementById('mg-ccw-bet')
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

        ws.onerror = () => addLog('error', '⚠️ Erro de conexão');
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
    } else if (data.type === 'state_sync') {
        handleStateSync(data.data);
    } else if (data.type === 'ack') {
        addLog('info', `✅ ${data.message}`);
    }
}

// Handle heartbeat state_sync from server
function handleStateSync(data) {
    // Staking display: block_gale (nova lógica C1/C2 14#) só tem precedência quando
    // está ATIVO (SDA_STAKING_MODE=block_gale); em gale/flat/kelly cai no martingale
    // legado (o engine fica sempre instanciado, então checar `active` é obrigatório).
    if (data.block_gale && data.block_gale.active) {
        updateBlockGale(data.block_gale, data.aposta, data.target_direction);
    } else {
        if (data.martingale_cw) updateMartingale('cw', data.martingale_cw);
        if (data.martingale_ccw) updateMartingale('ccw', data.martingale_ccw);
    }

    // Par escolhido (C1+C3 / C2+C3) e veredito red/green do último spin (aditivos)
    if (data.c_selection) updateCSelection(data.c_selection);
    if (data.ultimo_acerto) updateVerdict(data.ultimo_acerto);
    if (data.force17 || data.regioes) updateForce17(data.force17, data.regioes);

    // Update Performance (4 lists: sda17 + bet per direction)
    if (data.performance) updatePerformance4(data.performance);

    // Update last number indicator
    if (data.last_number !== undefined) {
        el.spinNumber.textContent = data.last_number;
    }

    // Update window history visualization
    if (data.window_history) {
        renderWindowHistory(data.window_history);
    }
}

// Render gale window history for both directions
function renderWindowHistory(history) {
    const container = document.getElementById('window-history-container');
    if (!container) return;

    let html = '';

    ['cw', 'ccw'].forEach(dir => {
        const windows = history[dir] || [];
        const label = dir === 'cw' ? 'Horário 🔄' : 'Anti-horário 🔃';

        html += `<div class="window-direction">`;
        html += `<h4>${label}</h4>`;

        if (windows.length === 0) {
            html += `<p class="no-data">Sem histórico</p>`;
        } else {
            windows.forEach(w => {
                // Handle active windows (no result yet) vs closed windows
                const isActive = !w.result;
                const resultClass = isActive ? 'active' :
                    w.result === 'success' ? 'success' :
                        w.result === 'stop' ? 'stop' : 'escalated';
                const resultIcon = isActive ? '⏳' :
                    w.result === 'success' ? '✅' :
                        w.result === 'stop' ? '🛑' : '⬆️';

                html += `<div class="window-card ${resultClass}">`;
                html += `<div class="window-header">`;
                html += `<span class="gale-badge">G${w.gale_level || 1}</span>`;
                html += `<span class="window-result">${resultIcon} ${w.total_hits || 0}/${w.total_plays || 0}</span>`;
                html += `</div>`;

                // Render plays as dots (handle null hit values)
                if (w.plays && w.plays.length > 0) {
                    html += `<div class="window-plays">`;
                    w.plays.forEach(p => {
                        // Handle null/undefined hit values (pending plays)
                        const dotClass = p.hit === true ? 'hit' :
                            p.hit === false ? 'miss' : 'pending';
                        const tooltip = `#${p.spin_number || '?'} → ${p.center_predicted || '?'}`;
                        html += `<span class="play-dot ${dotClass}" title="${tooltip}"></span>`;
                    });
                    html += `</div>`;
                }
                html += `</div>`;
            });
        }
        html += `</div>`;
    });

    container.innerHTML = html;
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

    // Strategy & Performance
    if (data.strategy) updateStrategy(data.strategy, data.result.trend);
    if (data.performance) updatePerformance(data.performance);

    // Staking instantâneo no spin: block_gale só quando ATIVO; senão martingale legado.
    // aposta omitida aqui (o valor vem no state_sync 1s); evita flicker.
    if (data.block_gale && data.block_gale.active) {
        updateBlockGale(data.block_gale, undefined, data.spin && data.spin.direcao);
    } else {
        if (data.martingale_cw) updateMartingale('cw', data.martingale_cw);
        if (data.martingale_ccw) updateMartingale('ccw', data.martingale_ccw);
    }

    // Par escolhido (C1+C3 / C2+C3) + veredito red/green (aditivos no trace)
    if (data.c_selection) updateCSelection(data.c_selection);
    if (data.ultimo_acerto) updateVerdict(data.ultimo_acerto);
    if (data.force17 || data.regioes) updateForce17(data.force17, data.regioes);

    // Log
    const dir = data.spin.direcao === 'horario' ? '🔄' : '🔃';
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
    el.status.textContent = online ? '⚫ ONLINE' : '⚫ OFFLINE';
}

function updateSpinDisplay(spin, ms) {
    el.spinNumber.textContent = spin.numero;
    el.spinDirection.textContent = spin.direcao === 'horario' ? '🔄' : '🔃';
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

function updateStrategy(strategy, trend) {
    if (el.strategyName) el.strategyName.textContent = strategy.name || 'SDA-17';
    if (el.strategyDesc) el.strategyDesc.textContent = strategy.description || '';
    if (el.strategyTrend) el.strategyTrend.textContent = trend || '--';
}

// Performance update — delegates to 4-list format (sda17 + bet per direction)
function updatePerformance(perf) {
    if (!perf) return;
    updatePerformance4(perf);
}

// Update Martingale display for a direction (cw or ccw)
function updateMartingale(direction, mg) {
    const hits = mg.window_hits ?? mg.consecutive_hits ?? 0;
    const count = mg.window_count ?? mg.total_bets ?? 0;
    const bet = mg.current_bet ?? '--';
    if (direction === 'cw') {
        if (el.mgCWDisplay) {
            el.mgCWDisplay.textContent = `G${mg.level} ${hits}/${count}`;
            el.mgCWDisplay.className = `mg-gale level-${mg.level}`;
        }
        if (el.mgCWBet) el.mgCWBet.textContent = `R$${bet}`;
    } else {
        if (el.mgCCWDisplay) {
            el.mgCCWDisplay.textContent = `G${mg.level} ${hits}/${count}`;
            el.mgCCWDisplay.className = `mg-gale level-${mg.level}`;
        }
        if (el.mgCCWBet) el.mgCCWBet.textContent = `R$${bet}`;
    }
}

// Update staking display from Block-Gale per direction (nova lógica C1/C2 14#).
// O valor apostado (R$) vem do servidor (data.aposta) — FONTE ÚNICA, sem fallback
// hardcoded. aposta só é aplicada na direção ALVO (aposta-se um sentido por vez);
// quando omitida (mensagem trace), o valor é preservado para evitar flicker.
function updateBlockGale(bg, aposta, targetDir) {
    if (!bg) return;
    const tdir = (targetDir === 'horario' || targetDir === 'cw') ? 'cw' : 'ccw';
    ['cw', 'ccw'].forEach(dir => {
        const st = bg[dir];
        if (!st) return;
        const dispEl = dir === 'cw' ? el.mgCWDisplay : el.mgCCWDisplay;
        const betEl = dir === 'cw' ? el.mgCWBet : el.mgCCWBet;
        if (dispEl) {
            dispEl.textContent = `G${st.level} ${st.block}`;
            dispEl.className = `mg-gale level-${st.level}`;
        }
        if (betEl && aposta != null) {
            betEl.textContent = (dir === tdir) ? `R$${aposta}` : '--';
        }
    });
}

// Update the chosen pair badge (C1+C3 / C2+C3) from c_selection.
function updateCSelection(cs) {
    if (!cs || !el.resultPair) return;
    el.resultPair.textContent = cs.pair || (cs.chosen ? `${cs.chosen}+C3` : '--');
}

// Update red/green verdict of the last verified spin (slot 'miss' = red).
function updateVerdict(ua) {
    if (!ua || !el.resultVerdict) return;
    const green = ua.green === true;
    el.resultVerdict.className = `result-verdict ${green ? 'green' : 'red'}`;
    const slot = ua.slot && ua.slot !== 'miss' ? ` em ${ua.slot}` : '';
    // Sentido analisado (horário/anti-horário) junto do veredito (pedido do operador).
    const dir = ua.direction === 'horario' ? ' · horário'
              : (ua.direction ? ' · anti-horário' : '');
    el.resultVerdict.textContent = green
        ? `✅ GREEN — ${ua.numero}${slot}${dir}`
        : `❌ RED — ${ua.numero}${dir}`;
}

// force17: renderiza as 3 regiões rotuladas (c2/c3/c1) com o número central e o
// rótulo pequeno embaixo, mais os números cobertos. Aditivo/defensivo.
function updateForce17(f17, regioes) {
    const body = document.getElementById('f17-body');
    const cov = document.getElementById('f17-cov');
    const bias = document.getElementById('f17-bias');
    if (!body) return;
    const regs = (regioes && regioes.length ? regioes : (f17 && f17.regioes) || []);
    if (!regs.length) return;
    const centros = regs.map(r => {
        const warm = r.status === 'aquecendo' ? ' ⏳' : '';
        // Paleta por label: force17 clássico (c1/c2/c3) e V5 (r1=primário verde,
        // r2=tendência azul, r3=fria amarelo). Fallback branco p/ labels novos.
        const COLORS = { c1: '#ffd166', c2: '#06d6a0', c3: '#118ab2',
                         r1: '#06d6a0', r2: '#118ab2', r3: '#ffd166' };
        const color = COLORS[r.label] || '#e0e0e0';
        return `<div style="display:inline-flex;flex-direction:column;align-items:center;margin:0 10px;">`
            + `<span style="font-size:26px;font-weight:bold;color:${color};line-height:1.1;">${r.center}${warm}</span>`
            + `<span style="font-size:11px;font-weight:bold;text-transform:uppercase;opacity:0.8;">${r.label}</span>`
            + `</div>`;
    }).join('');
    // fix BUG-FRONT #2: preferir os números do próprio meta force17 (mesma fonte das
    // regiões) — só cai no state.lastResult quando o meta não trouxer cobertura.
    const nums = (f17 && f17.numeros && f17.numeros.length
        ? f17.numeros
        : (state.lastResult && state.lastResult.numeros)) || [];
    const numsHTML = nums.length
        ? `<div style="margin-top:8px;font-size:12px;opacity:0.85;line-height:1.6;">${nums.join(' · ')}</div>`
        : '';
    body.innerHTML = `<div style="display:flex;justify-content:center;align-items:flex-end;flex-wrap:wrap;">${centros}</div>${numsHTML}`;
    if (cov && f17 && f17.coverage_n) cov.textContent = `(${f17.coverage_n}#)`;
    if (bias && f17 && f17.dir_bias) {
        bias.textContent = f17.dir_bias === 'favoravel' ? '✅ favorável' : '⚠️ desfavorável';
    }
}

// Update all 4 performance lists (sda17 and bet per direction)
function updatePerformance4(perf) {
    // Helper to update a set of squares
    function updateSquares(container, rateEl, data) {
        if (!container || !data) return;
        const squares = container.querySelectorAll('.perf-square');
        squares.forEach((sq, i) => {
            sq.className = 'perf-square';
            if (data.results && i < data.results.length) {
                sq.classList.add(data.results[i] ? 'hit' : 'miss');
            } else {
                sq.classList.add('empty');
            }
        });
        if (rateEl) rateEl.textContent = `${data.rate || 0}%`;
    }

    // SDA17 Performance (base for Triple Rate)
    if (perf.sda17) {
        updateSquares(el.perfSda17CW, el.perfRateSda17CW, perf.sda17.cw);
        updateSquares(el.perfSda17CCW, el.perfRateSda17CCW, perf.sda17.ccw);
    }

    // Bet Performance (real bets - for Martingale)
    if (perf.bet) {
        updateSquares(el.perfBetCW, el.perfRateBetCW, perf.bet.cw);
        updateSquares(el.perfBetCCW, el.perfRateBetCCW, perf.bet.ccw);
    }
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
