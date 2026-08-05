'use strict';
// SPR-V2 — testes do FLUXO REAL do service worker (`extension/background.js` carregado
// em `node:vm`). Cobrem a coreografia que o módulo puro não consegue cobrir:
// reentrância do alarme, corrida do boot, quem escreve o estado, e a telemetria.

const test = require('node:test');
const assert = require('node:assert/strict');

const { loadBackground, frame } = require('./chrome_harness.js');

const BASE = [7, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27];
const FP = BASE.join(',');
// Sem `extractorData.data.session` a extensão nem injeta o extrator de sessão —
// os testes de mesa/round precisam do manifesto presente desde o boot.
const SESSION_CFG = { data: { session: { table: ['x'] } } };

// Estado inicial do storage: NÃO escutando, para que o boot do worker não dispare um
// read-loop antes de o teste preparar as injeções.
function idleState(over = {}) {
  return Object.assign({
    isListening: false,
    tabId: null,
    results: BASE.slice(),
    lastHash: FP,
    resultsWithDir: [],
    totalRead: 0,
    extractorData: null,
    dir20: { baselineVersion: 2, baselineTable: 'Mesa-A', lastGoodFrameId: 3 }
  }, over);
}

// Deixa o boot assentar, liga a escuta pelo caminho serializado e abre o WebSocket.
// Devolve o socket já OPEN, com a fila de mensagens zerada (descarta o `register`).
async function boot(bg, over = {}) {
  await bg.flush();
  const patch = JSON.stringify(Object.assign({ isListening: true, tabId: 42 }, over));
  await bg.evalIn(`mutateState((s) => { Object.assign(s, ${patch}); })`);
  await bg.flush();

  bg.evalIn('connectWebSocket()');
  await bg.flush();
  const sock = bg.sockets[bg.sockets.length - 1];
  await sock._open();
  await bg.flush();
  // O servidor elege o dispositivo; sem isso a extensão fica SLAVE e não emite dados.
  await sock._recv({ type: 'role_assigned', role: 'master', connection_id: 'conn-1' });
  await bg.flush();
  // O resync pontual pós-conexão (DIR1/DIR5) é legado e vale sem a capability;
  // consumimos aqui para que cada teste avalie só o que pretende avaliar.
  bg.evalIn('pendingPhaseResync = false');
  bg.sent.length = 0;
  bg.logs.length = 0;
  return sock;
}

test('harness carrega o background.js real com o módulo puro', () => {
  const bg = loadBackground();
  assert.ok(bg.loaded.includes('phase_align.js'));
  assert.equal(bg.evalIn('typeof PhaseAlign'), 'object');
  assert.equal(bg.evalIn('DIR20_ENABLED'), true);
  assert.equal(bg.evalIn('dir20Active()'), true);
});

test('fail-closed: sem phase_align.js a leitura é SUSPENSA (não cai no legado)', async () => {
  const bg = loadBackground({
    blockImports: ['phase_align.js'],
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  assert.equal(bg.evalIn('typeof PhaseAlign'), 'undefined');
  bg.injections.results = [frame(3, [11].concat(BASE))];

  await boot(bg);
  await bg.evalIn('readResults()');
  await bg.flush();

  assert.equal(bg.sent.length, 0, 'nada pode ser enviado sem o módulo de alinhamento');
  assert.equal(bg.state.totalRead, 0);
  assert.ok(bg.logs.some(([lvl, msg]) => lvl === 'error' && String(msg).includes('fail-closed')));
});

test('giro real: envia UMA vez, com fingerprint de 12 e telemetria embarcada', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  await boot(bg);

  await bg.evalIn('readResults()');
  await bg.flush();

  const spins = bg.sent.filter((m) => m.type === 'novo_resultado');
  assert.equal(spins.length, 1);
  assert.equal(spins[0].numero, 11);
  assert.equal(spins[0].direcao, 'horario');
  assert.equal(spins[0].k_novos, 1);
  assert.equal(spins[0].allNumbers.length, 12);
  assert.ok(spins[0].client_health, 'client_health é o bloco aditivo da DoD');
  assert.equal(spins[0].client_health.ext_version, '3.10.0');

  // Baseline re-ancorado sobre os MESMOS 12 números do payload.
  assert.equal(bg.state.lastHash, spins[0].allNumbers.join(','));
  assert.equal(bg.state.totalRead, 1);
  // A fase flipou uma vez, e só uma.
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario');
  assert.equal(bg.store.currentDirection, 'anti-horario');
});

test('leitura NÃO alinhada: zero envio, zero flip, baseline intacto, perda CONTADA', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  // Outra realidade (frame do lobby / DOM meio-renderizado).
  bg.injections.results = [frame(3, [3, 26, 0, 12, 35, 14, 8, 23, 10, 5, 24, 16])];
  await boot(bg);

  await bg.evalIn('readResults()');
  await bg.flush();

  assert.equal(bg.sent.length, 0, 'NADA pode sair de uma leitura suspeita');
  assert.equal(bg.evalIn('currentDirection'), 'horario', 'a fase NÃO pode flipar');
  assert.equal(bg.state.lastHash, FP, 'baseline intacto');
  assert.deepEqual(bg.state.results, BASE, 'baseline intacto');
  assert.equal(bg.state.totalRead, 0);
  assert.equal(bg.state.dir20.skippedUnaligned, 1, 'a perda é observável');
  assert.equal(bg.state.dir20.unalignedStreak, 1);
  assert.equal(bg.state.dir20.lastReason, 'no_alignment');
  assert.equal(bg.state.dir20.lastGoodFrameId, 3, 'frame suspeito NÃO vira frame bom');
});

test('re-baseline após 5 skips: re-ancora sem enviar giro e sem historico_inicial', async () => {
  const bg = loadBackground({
    storage: {
      escutaState: idleState({ dir20: { baselineVersion: 2, baselineTable: 'Mesa-A', unalignedStreak: 4 }, extractorData: SESSION_CFG }),
      currentDirection: 'horario'
    }
  });
  const outros = [3, 26, 0, 12, 35, 14, 8, 23, 10, 5, 24, 16];
  bg.injections.results = [frame(7, outros)];
  bg.injections.session = [{ frameId: 7, result: { table: 'Mesa-A', round_id: 'r-99', dealer: null } }];
  await bg.flush();
  await boot(bg);

  await bg.evalIn('readResults()');
  await bg.flush();

  assert.equal(bg.sent.filter((m) => m.type === 'novo_resultado').length, 0);
  assert.equal(bg.sent.filter((m) => m.type === 'historico_inicial').length, 0,
    'mesma mesa ⇒ re-baseline silencioso (o servidor já tem o histórico)');
  assert.equal(bg.evalIn('currentDirection'), 'horario', 're-baseline nunca flipa');
  assert.deepEqual(bg.state.results, outros, 'baseline re-ancorado');
  assert.equal(bg.state.dir20.rebaselines, 1);
  assert.equal(bg.state.dir20.unalignedStreak, 0);
});

test('troca de mesa no re-baseline manda historico_inicial (evidência)', async () => {
  const bg = loadBackground({
    storage: {
      escutaState: idleState({ dir20: { baselineVersion: 2, baselineTable: 'Mesa-A', unalignedStreak: 4 }, extractorData: SESSION_CFG }),
      currentDirection: 'horario'
    }
  });
  bg.injections.results = [frame(7, [3, 26, 0, 12, 35, 14, 8, 23, 10, 5, 24, 16])];
  bg.injections.session = [{ frameId: 7, result: { table: 'Mesa-B', round_id: 'r-1', dealer: null } }];
  await bg.flush();
  await boot(bg);

  await bg.evalIn('readResults()');
  await bg.flush();

  assert.equal(bg.sent.filter((m) => m.type === 'historico_inicial').length, 1);
  assert.equal(bg.sent.filter((m) => m.type === 'novo_resultado').length, 0);
  assert.equal(bg.state.dir20.baselineTable, 'Mesa-B');
});

test('REENTRÂNCIA: dois ticks sobrepostos produzem UM único envio', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' },
    injectionDelayMs: 25
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  await boot(bg);

  // O alarme dispara duas vezes com o primeiro tick ainda em voo (janela minimizada).
  await Promise.all([bg.fireAlarm('readLoop'), bg.fireAlarm('readLoop')]);
  await bg.flush(20);

  const spins = bg.sent.filter((m) => m.type === 'novo_resultado');
  assert.equal(spins.length, 1, 'o tick sobreposto DESISTE — antes eram 2 envios e 2 flips');
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario', 'exatamente um flip');
  assert.equal(bg.state.totalRead, 1);
});

test('BOOT: o 1º tick não sai com a fase literal "horario" quando o storage atrasa', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'anti-horario', directionSeed: 'anti-horario' },
    storageDelayMs: 12
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  await boot(bg);

  // Dispara o tick IMEDIATAMENTE após o wake (antes do storage resolver).
  await bg.fireAlarm('readLoop');
  await bg.flush(20);

  const spins = bg.sent.filter((m) => m.type === 'novo_resultado');
  assert.equal(spins.length, 1);
  assert.equal(spins[0].direcao, 'anti-horario', 'a fase veio do storage, não do default');
  assert.equal(bg.evalIn('currentDirection'), 'horario', 'flipou a partir da fase correta');
});

test('SINGLE-WRITER: start + tick concorrentes não perdem escrita', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' },
    injectionDelayMs: 10
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  await boot(bg);

  await Promise.all([
    bg.evalIn('readResults()'),
    bg.evalIn("handleMessage({ action: 'setDirection', direction: 'anti-horario', manual: false }, {})")
  ]);
  await bg.flush(20);

  // Seja qual for a ordem, o estado final é COERENTE: o baseline do tick não sumiu
  // e a telemetria continua lá (era exatamente isso que o "último a escrever" apagava).
  assert.equal(bg.state.lastHash.split(',').length, 12);
  assert.ok(bg.state.dir20, 'bloco de telemetria preservado');
  assert.equal(typeof bg.state.dir20.skippedUnaligned, 'number');
});

test('frame STICKY: o frame que já funcionou vence a "lista mais longa" de outro frame', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  // frame 9 (lobby) tem MAIS números, mas o frame 3 é o que sempre alinhou.
  bg.injections.results = [
    frame(9, [3, 26, 0, 12, 35, 14, 8, 23, 10, 5, 24, 16]),
    frame(3, [11].concat(BASE).slice(0, 12))
  ];
  await boot(bg);

  await bg.evalIn('readResults()');
  await bg.flush();

  const spins = bg.sent.filter((m) => m.type === 'novo_resultado');
  assert.equal(spins.length, 1);
  assert.equal(spins[0].numero, 11, 'leu o frame do JOGO, não o do lobby');
  assert.equal(bg.state.dir20.lastFrameId, 3);
});

test('estado volátil (isConnected/deviceRole/wsUrl) NUNCA é persistido', async () => {
  const bg = loadBackground({ storage: { escutaState: idleState() } });
  await bg.evalIn('mutateState((s) => { s.totalRead = 5; })');
  await bg.flush();

  assert.equal(bg.state.totalRead, 5);
  assert.equal('isConnected' in bg.state, false);
  assert.equal('deviceRole' in bg.state, false);
  assert.equal('wsUrl' in bg.state, false);

  const view = await bg.evalIn('getState()');
  assert.equal(view.isConnected, false, 'a visão continua expondo o volátil');
  assert.equal(typeof view.wsUrl, 'string');
});

test('migração de baseline: hash de 5 vira fingerprint de 12 sem enviar giro', async () => {
  const bg = loadBackground({
    storage: {
      escutaState: {
        isListening: false, tabId: null, results: BASE.slice(),
        lastHash: BASE.slice(0, 5).join(','), totalRead: 3
      }
    }
  });
  await bg.evalIn('mutateState(migrateBaseline)');
  await bg.flush();

  assert.equal(bg.state.lastHash, FP);
  assert.equal(bg.state.dir20.baselineVersion, 2);
  assert.equal(bg.state.totalRead, 3, 'migração não mexe em contadores de negócio');
  assert.equal(bg.sent.length, 0);
});

// ---------------------------------------------------------------------------
// phase_authority (SPR-V1) — consumo RETROCOMPATÍVEL
// ---------------------------------------------------------------------------

test('resync pontual pós-conexão (DIR1) continua valendo SEM a capability', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  await bg.flush();
  bg.evalIn('connectWebSocket()');
  await bg.flush();
  const sock = bg.sockets[bg.sockets.length - 1];
  await sock._open();
  await bg.flush();

  await sock._recv({ type: 'state_sync', data: { sentido: { next_direction: 'anti-horario' } } });
  await bg.flush();
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario', 'o resync de reconexão é one-shot');

  // …e é ONE-SHOT: o 2º state_sync já não move nada sem a capability.
  await sock._recv({ type: 'state_sync', data: { sentido: { next_direction: 'horario' } } });
  await bg.flush();
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario');
});

test('phase_authority ausente: reconciliação DESARMADA (rollback do servidor)', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  const sock = await boot(bg);

  await sock._recv({ type: 'state_sync', data: { sentido: { next_direction: 'anti-horario' } } });
  await bg.flush();

  assert.equal(bg.evalIn('currentDirection'), 'horario',
    'sem a capability, o servidor NÃO reconcilia continuamente');
  assert.equal(bg.state.dir20.flipsReverted, 0);
});

test('phase_authority enabled=false: também desarmado', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  const sock = await boot(bg);

  await sock._recv({
    type: 'state_sync',
    data: {
      sentido: { next_direction: 'anti-horario' },
      phase_authority: { enabled: false, spin_seq: 10, direction: 'ccw' }
    }
  });
  await bg.flush();

  assert.equal(bg.evalIn('currentDirection'), 'horario');
});

test('phase_authority enabled=true reconcilia a fase continuamente (cw/ccw)', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  const sock = await boot(bg);

  await sock._recv({
    type: 'state_sync',
    data: {
      sentido: { next_direction: 'anti-horario' },
      phase_authority: { enabled: true, spin_seq: 10, direction: 'ccw', seed_parity: 0, seed_n: 3 }
    }
  });
  await bg.flush();

  assert.equal(bg.evalIn('currentDirection'), 'anti-horario');
  assert.equal(bg.store.currentDirection, 'anti-horario');
  assert.equal(bg.state.dir20.paLastSeq, 10);
});

test('giro REJEITADO pelo servidor: o flip local é desfeito e CONTADO', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  const sock = await boot(bg);

  // 1) servidor informa spin_seq = 10
  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' } }
  });
  await bg.flush();
  assert.equal(bg.state.dir20.paLastSeq, 10);

  // 2) enviamos um giro — a fase local flipa para anti-horario
  await bg.evalIn('readResults()');
  await bg.flush();
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario');
  assert.equal(bg.state.dir20.paAwaitingAck, true);
  assert.equal(bg.state.dir20.paSeqBeforeSend, 10);

  // 3) passada a janela de graça, o servidor ainda está em spin_seq=10 ⇒ rejeitou
  bg.evalIn('(async()=>{ await mutateState((s)=>{ ensureDir20(s).paSentAtMs = 0; }); })()');
  await bg.flush();
  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' } }
  });
  await bg.flush();

  assert.equal(bg.evalIn('currentDirection'), 'horario', 'flip local desfeito');
  assert.equal(bg.state.dir20.flipsReverted, 1);
  assert.equal(bg.state.dir20.paAwaitingAck, false);
});

// ---------------------------------------------------------------------------
// Achados do code-review pós-implantação (todos travados por teste)
// ---------------------------------------------------------------------------

test('REVIEW#1 eco automático do popup NÃO desarma o PA-ACK (só a âncora manual)', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  const sock = await boot(bg);

  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' } }
  });
  await bg.flush();
  await bg.evalIn('readResults()');
  await bg.flush();
  assert.equal(bg.state.dir20.paAwaitingAck, true);

  // O popup reage ao `storage.onChanged` do flip e ecoa a MESMA fase, sem ser o operador.
  await bg.chrome.runtime.__send({ action: 'setDirection', direction: 'anti-horario', manual: false });
  await bg.flush();
  assert.equal(bg.state.dir20.paAwaitingAck, true, 'o eco não é âncora — o giro segue em voo');
  assert.equal(bg.state.dir20.paSeqBeforeSend, 10);

  // Já a âncora MANUAL do operador invalida a expectativa de eco.
  await bg.chrome.runtime.__send({ action: 'setDirection', direction: 'horario', manual: true });
  await bg.flush();
  assert.equal(bg.state.dir20.paAwaitingAck, false);
  assert.equal(bg.state.dir20.paSeqBeforeSend, null);
});

test('REVIEW#2 heartbeat PRÉ-giro na janela do envio não desfaz o flip recém-feito', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' },
    storageDelayMs: 3   // alarga a janela entre o flip e o `sendToWebSocket`
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  const sock = await boot(bg);

  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' } }
  });
  await bg.flush();

  // Dispara a leitura SEM esperar e injeta o heartbeat pré-giro no meio do caminho.
  const reading = bg.evalIn('readResults()');
  await new Promise((r) => setTimeout(r, 4));
  await sock._recv({
    type: 'state_sync',
    data: {
      target_direction: 'horario',
      phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' }
    }
  });
  await reading;
  await bg.flush();

  assert.equal(bg.sent.filter((m) => m.type === 'novo_resultado').length, 1);
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario',
    'o guard é armado ATOMICAMENTE com o flip — o snapshot pré-giro não reconcilia por cima');
  assert.equal(bg.state.dir20.paSeqBeforeSend, 10, 'a foto do seq é ANTERIOR ao giro');
});

test('REVIEW#3 rejeição sem reversão NÃO incrementa flipsReverted', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  const sock = await boot(bg);

  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' } }
  });
  await bg.flush();
  await bg.evalIn('readResults()');
  await bg.flush();
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario');

  // Servidor não contou o giro E não diz em que fase está: nada a reverter.
  bg.evalIn('(async()=>{ await mutateState((s)=>{ ensureDir20(s).paSentAtMs = 0; }); })()');
  await bg.flush();
  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 10 } }
  });
  await bg.flush();

  assert.equal(bg.state.dir20.paAwaitingAck, false, 'a expectativa é encerrada de qualquer forma');
  assert.equal(bg.state.dir20.flipsReverted, 0,
    'a métrica de perda só conta flip REALMENTE desfeito');
  assert.equal(bg.evalIn('currentDirection'), 'anti-horario');
});

test('envio que FALHA desarma o guard (senão a graça reverteria um flip legítimo)', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  const sock = await boot(bg);

  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' } }
  });
  await bg.flush();

  sock.readyState = 3;   // CLOSED: `sendToWebSocket` devolve false
  await bg.evalIn('readResults()');
  await bg.flush();

  assert.equal(bg.sent.filter((m) => m.type === 'novo_resultado').length, 0);
  assert.equal(bg.state.dir20.paAwaitingAck, false);
  assert.equal(bg.state.dir20.paSeqBeforeSend, null);
});

test('giro ACEITO pelo servidor: nada é revertido', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }  });
  bg.injections.results = [frame(3, [11].concat(BASE).slice(0, 12))];
  const sock = await boot(bg);

  await sock._recv({ type: 'state_sync', data: { phase_authority: { enabled: true, spin_seq: 10, direction: 'cw' } } });
  await bg.flush();
  await bg.evalIn('readResults()');
  await bg.flush();

  await sock._recv({
    type: 'state_sync',
    data: { phase_authority: { enabled: true, spin_seq: 11, direction: 'ccw' } }
  });
  await bg.flush();

  assert.equal(bg.evalIn('currentDirection'), 'anti-horario', 'a fase pós-giro se mantém');
  assert.equal(bg.state.dir20.flipsReverted, 0);
  assert.equal(bg.state.dir20.paAwaitingAck, false);
});

test('backoff exponencial com jitter, teto e timer ÚNICO (sem desistir)', async () => {
  const bg = loadBackground({ storage: {} });
  assert.equal(bg.evalIn('_reconnectTimer'), null);

  bg.evalIn('scheduleReconnect()');
  bg.evalIn('scheduleReconnect()');   // não deve criar um segundo timer
  assert.equal(bg.evalIn('wsReconnectAttempts'), 1, 'timer único ⇒ uma tentativa agendada');
  assert.notEqual(bg.evalIn('_reconnectTimer'), null);

  // Depois do teto de tentativas o cliente CONTINUA tentando (satura, não desiste).
  bg.evalIn('clearTimeout(_reconnectTimer); _reconnectTimer = null; wsReconnectAttempts = 50;');
  bg.evalIn('scheduleReconnect()');
  assert.equal(bg.evalIn('wsReconnectAttempts'), 51);
  assert.notEqual(bg.evalIn('_reconnectTimer'), null, 'nunca para de tentar');
  bg.evalIn('clearTimeout(_reconnectTimer); _reconnectTimer = null;');
  assert.equal(bg.evalIn('WS_CONFIG.maxBackoffMs'), 60000);
});

test('register leva ext_version e client_health (bloco aditivo)', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState({ dir20: { skippedUnaligned: 7, rebaselines: 2 } }) }
  });
  bg.evalIn('connectWebSocket()');
  await bg.flush();
  await bg.sockets[bg.sockets.length - 1]._open();
  await bg.flush();

  const reg = bg.sent.find((m) => m.type === 'register');
  assert.ok(reg, 'register continua sendo enviado');
  assert.equal(reg.ext_version, '3.10.0');
  assert.equal(reg.client_health.skipped_unaligned, 7);
  assert.equal(reg.client_health.rebaselines, 2);
});

test('nenhum número no DOM: skip contado, sem envio e sem tocar no baseline', async () => {
  const bg = loadBackground({
    storage: { escutaState: idleState(), currentDirection: 'horario' }
  });
  bg.injections.results = [{ frameId: 3, result: { numbers: [], elementsFound: 0 } }];
  await boot(bg);

  await bg.evalIn('readResults()');
  await bg.flush();

  assert.equal(bg.sent.length, 0);
  assert.equal(bg.state.lastHash, FP);
  assert.equal(bg.evalIn('currentDirection'), 'horario');
  assert.equal(bg.state.debug.numbersFound, 0);
});
