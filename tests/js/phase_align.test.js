'use strict';
// SPR-V2 — testes da LÓGICA PURA de alinhamento de fase (`extension/phase_align.js`).
// Nenhuma API do Chrome envolvida: se um destes falha, o defeito está na regra, não
// no service worker.

const test = require('node:test');
const assert = require('node:assert/strict');

const PA = require('../../extension/phase_align.js');

test('fingerprint cobre a MESMA janela de 12 que o payload envia ao servidor', () => {
  const nums = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14];
  assert.equal(PA.FP_WINDOW, 12);
  assert.equal(PA.fingerprint(nums), '1,2,3,4,5,6,7,8,9,10,11,12');
  // A regressão que o sprint conserta: prova de 5 contra payload de 12.
  assert.equal(PA.fingerprint(nums, PA.LEGACY_FP_WINDOW), '1,2,3,4,5');
  assert.notEqual(PA.fingerprint(nums), PA.fingerprint(nums, PA.LEGACY_FP_WINDOW));
});

test('fingerprint devolve string vazia para entrada inválida (sentinela de "sem baseline")', () => {
  assert.equal(PA.fingerprint([]), '');
  assert.equal(PA.fingerprint(null), '');
  assert.equal(PA.fingerprint(['5', 3]), '');
  assert.equal(PA.fingerprint([1, NaN]), '');
});

test('countNewSpins: leitura idêntica é k=0, NUNCA 1', () => {
  const base = [7, 32, 15, 19, 4, 21, 2, 25];
  const r = PA.countNewSpins(base.slice(), base.slice());
  assert.equal(r.k, 0);
  assert.equal(r.matched, true);
  assert.equal(r.reason, PA.REASON.IDENTICAL);
});

test('countNewSpins: 1 giro novo', () => {
  const old = [7, 32, 15, 19, 4];
  const now = [11, 7, 32, 15, 19, 4];
  const r = PA.countNewSpins(now, old);
  assert.equal(r.k, 1);
  assert.equal(r.matched, true);
  assert.equal(r.overlap, 5);
});

test('countNewSpins: k=3 (gap recuperado após o SW dormir)', () => {
  const old = [7, 32, 15, 19, 4, 21];
  const now = [8, 30, 11, 7, 32, 15, 19, 4, 21];
  const r = PA.countNewSpins(now, old);
  assert.equal(r.k, 3);
  assert.equal(r.matched, true);
  assert.equal(r.overlap, 6);
});

test('countNewSpins: números repetidos não confundem (comparação POSICIONAL)', () => {
  const old = [5, 5, 5, 5, 5];
  const now = [5, 5, 5, 5, 5, 5];
  const r = PA.countNewSpins(now, old);
  // Com prefixo todo igual, k=0 casa primeiro: o DOM devolveu 1 número a mais na
  // cauda, não um giro novo no topo. Preferir o menor k é o lado conservador certo.
  assert.equal(r.k, 0);
  assert.equal(r.matched, true);
});

test('countNewSpins: DESALINHADO devolve matched:false — não inventa "1 giro"', () => {
  const old = [7, 32, 15, 19, 4, 21];
  const now = [3, 26, 0, 12, 35, 14];  // outra realidade (ex.: frame do lobby)
  const r = PA.countNewSpins(now, old);
  assert.equal(r.matched, false);
  assert.equal(r.k, 0);
  assert.equal(r.reason, PA.REASON.NO_ALIGNMENT);
});

test('countNewSpins: overlap de 1 número é ruído (1/37) e NÃO é aceito', () => {
  // Só o último número da nova lista bate com o primeiro do baseline.
  const old = [9, 1, 2, 3];
  const now = [40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 9];
  const r = PA.countNewSpins(now, old);
  assert.equal(r.matched, false);
  assert.equal(r.reason, PA.REASON.NO_ALIGNMENT);
});

test('countNewSpins: overlap de exatamente 2 é aceito (mínimo)', () => {
  const old = [9, 1];
  const now = [40, 41, 9, 1];
  const r = PA.countNewSpins(now, old);
  assert.equal(r.matched, true);
  assert.equal(r.k, 2);
  assert.equal(r.overlap, 2);
  assert.equal(PA.MIN_OVERLAP, 2);
});

test('countNewSpins: entradas inválidas/vazias nunca viram giro', () => {
  for (const [a, b] of [[[], [1, 2]], [[1, 2], []], [null, [1]], [[1], undefined], [['1'], [1]]]) {
    const r = PA.countNewSpins(a, b);
    assert.equal(r.matched, false, `esperava matched:false para ${JSON.stringify([a, b])}`);
    assert.equal(r.k, 0);
  }
});

test('countNewSpins strict=false reproduz o algoritmo v3.9.1 (kill-switch)', () => {
  const old = [7, 32, 15, 19, 4, 21];
  const now = [3, 26, 0, 12, 35, 14];
  const legacy = PA.countNewSpins(now, old, false);
  assert.equal(legacy.matched, true, 'legado assume 1 giro mesmo sem alinhar');
  assert.equal(legacy.k, 1);
  assert.equal(legacy.reason, PA.REASON.LEGACY_ASSUMED);
  // E o legado nem sequer considera k=0:
  const same = PA.countNewSpins([1, 2, 3], [1, 2, 3], false);
  assert.equal(same.k, 1);
});

test('decideRebaseline dispara só no limite configurado', () => {
  assert.equal(PA.decideRebaseline(4, 5), false);
  assert.equal(PA.decideRebaseline(5, 5), true);
  assert.equal(PA.decideRebaseline(6, 5), true);
  assert.equal(PA.decideRebaseline(PA.DEFAULT_MAX_SKIPS, undefined), true);
  assert.equal(PA.decideRebaseline(null, 5), false);
});

// ---------------------------------------------------------------------------
// decideTick — a decisão que o background executa
// ---------------------------------------------------------------------------

const tick = (over) => PA.decideTick(Object.assign({
  numbers: [], baseline: [], baselineHash: '', currentDirection: 'horario',
  unalignedStreak: 0, maxSkips: 5, tableNow: null, tableAtBaseline: null
}, over));

test('decideTick: primeira leitura ancora sem inventar giro e manda histórico', () => {
  const d = tick({ numbers: [7, 32, 15], baselineHash: '', baseline: [] });
  assert.equal(d.action, 'baseline_init');
  assert.equal(d.sendHistorico, true);
  assert.equal(d.sendDir, null);
  assert.deepEqual(d.newBaseline, [7, 32, 15]);
  assert.equal(d.streak, 0);
});

test('decideTick: DOM inalterado é noop absoluto', () => {
  const base = [7, 32, 15, 19, 4];
  const d = tick({ numbers: base.slice(), baseline: base.slice(), baselineHash: PA.fingerprint(base) });
  assert.equal(d.action, 'noop');
  assert.equal(d.reason, PA.REASON.IDENTICAL);
  assert.equal(d.newBaseline, null);
});

test('decideTick: 1 giro novo envia com a fase corrente e prepara o flip', () => {
  const base = [7, 32, 15, 19, 4];
  const d = tick({
    numbers: [11, 7, 32, 15, 19, 4], baseline: base, baselineHash: PA.fingerprint(base),
    currentDirection: 'horario'
  });
  assert.equal(d.action, 'send');
  assert.equal(d.k, 1);
  assert.equal(d.sendDir, 'horario');
  assert.equal(d.nextDir, 'anti-horario');
});

test('decideTick: k par corrige a paridade (a fase do envio NÃO é a corrente)', () => {
  const base = [7, 32, 15, 19, 4];
  const d = tick({
    numbers: [8, 11, 7, 32, 15, 19, 4], baseline: base, baselineHash: PA.fingerprint(base),
    currentDirection: 'horario'
  });
  assert.equal(d.k, 2);
  assert.equal(d.sendDir, 'anti-horario');
  assert.equal(d.nextDir, 'horario');
});

test('decideTick: leitura NÃO alinhada = skip puro (zero envio, zero flip, baseline intacto)', () => {
  const base = [7, 32, 15, 19, 4, 21];
  const d = tick({
    numbers: [3, 26, 0, 12, 35, 14], baseline: base, baselineHash: PA.fingerprint(base),
    unalignedStreak: 0
  });
  assert.equal(d.action, 'skip');
  assert.equal(d.sendDir, null);
  assert.equal(d.nextDir, null);
  assert.equal(d.newBaseline, null, 'baseline NÃO pode ser tocado');
  assert.equal(d.newHash, null);
  assert.equal(d.streak, 1, 'a perda é contada');
});

test('decideTick: cauda truncada com mesmo prefixo é noop — não empobrece o baseline', () => {
  const base = [7, 32, 15, 19, 4, 21, 2, 25];
  const d = tick({
    numbers: [7, 32, 15], baseline: base, baselineHash: PA.fingerprint(base)
  });
  assert.equal(d.action, 'noop');
  assert.equal(d.reason, 'truncated_same_prefix');
  assert.equal(d.newBaseline, null);
  assert.equal(d.k, 0);
});

test('decideTick: após MAX_SKIPS re-ancora SEM enviar giro e SEM histórico (mesma mesa)', () => {
  const base = [7, 32, 15, 19, 4, 21];
  const d = tick({
    numbers: [3, 26, 0, 12, 35, 14], baseline: base, baselineHash: PA.fingerprint(base),
    unalignedStreak: 4, maxSkips: 5, tableNow: 'Mesa-A', tableAtBaseline: 'Mesa-A'
  });
  assert.equal(d.action, 'rebaseline');
  assert.equal(d.sendDir, null, 're-baseline NUNCA envia giro');
  assert.equal(d.sendHistorico, false, 'mesma mesa ⇒ re-baseline silencioso');
  assert.equal(d.tableChanged, false);
  assert.deepEqual(d.newBaseline, [3, 26, 0, 12, 35, 14]);
  assert.equal(d.streak, 0);
});

test('decideTick: re-baseline com TROCA DE MESA manda histórico_inicial', () => {
  const base = [7, 32, 15, 19, 4, 21];
  const d = tick({
    numbers: [3, 26, 0, 12, 35, 14], baseline: base, baselineHash: PA.fingerprint(base),
    unalignedStreak: 4, maxSkips: 5, tableNow: 'Mesa-B', tableAtBaseline: 'Mesa-A'
  });
  assert.equal(d.action, 'rebaseline');
  assert.equal(d.tableChanged, true);
  assert.equal(d.sendHistorico, true);
});

test('decideTick: lista vazia é skip contado, não giro', () => {
  const base = [7, 32, 15];
  const d = tick({ numbers: [], baseline: base, baselineHash: PA.fingerprint(base), unalignedStreak: 2 });
  assert.equal(d.action, 'skip');
  assert.equal(d.streak, 3);
});

test('decideTick strict=false (kill-switch) volta a fabricar o giro — comportamento v3.9.1', () => {
  const base = [7, 32, 15, 19, 4, 21];
  const d = tick({
    numbers: [3, 26, 0, 12, 35, 14], baseline: base, baselineHash: PA.fingerprint(base, 5),
    strict: false
  });
  assert.equal(d.action, 'send', 'é exatamente a regressão que o modo estrito corrige');
  assert.equal(d.k, 1);
});

test('decideTick: baseline sempre truncado a 12 mesmo com leitura maior', () => {
  const nums = Array.from({ length: 20 }, (_, i) => i + 1);
  const d = tick({ numbers: nums, baselineHash: '', baseline: [] });
  assert.equal(d.newBaseline.length, 12);
  assert.equal(d.newHash, PA.fingerprint(nums));
});

// ---------------------------------------------------------------------------
// Primitivas de serialização
// ---------------------------------------------------------------------------

test('createSerialQueue executa uma mutação por vez (sem intercalar)', async () => {
  const q = PA.createSerialQueue();
  const order = [];
  const slow = (id, ms) => q.run(async () => {
    order.push(`in:${id}`);
    await new Promise((r) => setTimeout(r, ms));
    order.push(`out:${id}`);
    return id;
  });
  const all = await Promise.all([slow('a', 20), slow('b', 1), slow('c', 1)]);
  assert.deepEqual(all, ['a', 'b', 'c']);
  assert.deepEqual(order, ['in:a', 'out:a', 'in:b', 'out:b', 'in:c', 'out:c']);
});

test('createSerialQueue sobrevive a uma mutação que lança (a fila não morre)', async () => {
  const q = PA.createSerialQueue();
  await assert.rejects(q.run(async () => { throw new Error('boom'); }));
  assert.equal(await q.run(async () => 'vivo'), 'vivo');
});

test('createReentrancyGuard: o segundo tick DESISTE em vez de enfileirar', async () => {
  const g = PA.createReentrancyGuard();
  let runs = 0;
  const job = () => g.run(async () => {
    runs++;
    await new Promise((r) => setTimeout(r, 15));
    return runs;
  });
  const [a, b] = await Promise.all([job(), job()]);
  assert.equal(runs, 1, 'só UMA execução — enfileirar duplicaria o mesmo giro');
  assert.equal(a.skipped, false);
  assert.equal(b.skipped, true);
  assert.equal(g.isBusy(), false);
  assert.equal(g.skippedCount(), 1);
});

test('createReentrancyGuard libera o busy mesmo em erro', async () => {
  const g = PA.createReentrancyGuard();
  await assert.rejects(g.run(async () => { throw new Error('x'); }));
  assert.equal(g.isBusy(), false);
  const r = await g.run(async () => 'ok');
  assert.equal(r.value, 'ok');
});

test('createHydrationGate carrega UMA vez e degrada com graça se o storage falhar', async () => {
  let calls = 0;
  const gate = PA.createHydrationGate(async () => { calls++; return 'anti-horario'; });
  const [a, b] = await Promise.all([gate.ready(), gate.ready()]);
  assert.equal(calls, 1);
  assert.equal(a, 'anti-horario');
  assert.equal(b, 'anti-horario');

  const bad = PA.createHydrationGate(async () => { throw new Error('storage down'); });
  assert.equal(await bad.ready(), null, 'falha de storage não pode travar o SW');
});
