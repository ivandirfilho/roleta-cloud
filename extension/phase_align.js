// SPR-V2 (DIR20) — Alinhamento de fase: LÓGICA PURA, sem nenhuma API do Chrome.
//
// Por que este arquivo existe
// ---------------------------
// O service worker MV3 lê o DOM da mesa a cada ~2s. Com a janela minimizada o Chrome
// pausa rAF e faz throttling dos timers da página: o DOM fica em estados intermediários.
// O algoritmo antigo (`countNewSpins` com `return 1` conservador) transformava CADA
// leitura parcial em "1 giro novo" — fabricando um giro fantasma e invertendo a fase.
//
// Disciplina de evidência (a mesma do servidor em `state/phase.py`):
//   • `k = 0` existe (re-render idêntico = NENHUM giro novo);
//   • um alinhamento com `k >= 1` só é aceito com **overlap >= 2** — 1 número de prova
//     é 1/37 de coincidência, ou seja, ruído;
//   • sem alinhamento NÃO se inventa `k`: devolve-se `matched:false` e o chamador
//     não envia, não flipa e não mexe no baseline.
//
// Este módulo é UMD: `importScripts('phase_align.js')` no service worker (expõe
// `globalThis.PhaseAlign`) e `require('../../extension/phase_align.js')` no `node --test`.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) {
    module.exports = factory();
  } else {
    root.PhaseAlign = factory();
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Janela do fingerprint = janela do payload (`allNumbers.slice(0, 12)`). O baseline
  // precisa ser validado sobre EXATAMENTE os números que o servidor vai alinhar; com
  // hash de 5 o servidor comparava 12 contra uma prova de 5.
  var FP_WINDOW = 12;
  // Janela do hash legado v3.9.1 (5) — a raiz do desalinhamento: o servidor recebia 12
  // números mas a prova de identidade cobria só 5. Preservada para o kill-switch.
  var LEGACY_FP_WINDOW = 5;
  var MAX_K = 12;
  // Overlap mínimo para aceitar um deslocamento (k >= 1). Ver "disciplina de evidência".
  var MIN_OVERLAP = 2;
  // Skips consecutivos tolerados antes de re-ancorar o baseline (≈10s no tick de 2s).
  var DEFAULT_MAX_SKIPS = 5;

  var REASON = {
    INVALID_INPUT: 'invalid_input',
    EMPTY_NEW: 'empty_new',
    EMPTY_OLD: 'empty_old',
    ALIGNED: 'aligned',
    IDENTICAL: 'identical',
    NO_ALIGNMENT: 'no_alignment',
    LEGACY_ASSUMED: 'legacy_assumed'
  };

  function isNumberList(arr) {
    if (!Array.isArray(arr)) return false;
    for (var i = 0; i < arr.length; i++) {
      var v = arr[i];
      if (typeof v !== 'number' || !isFinite(v)) return false;
    }
    return true;
  }

  // Fingerprint dos 12 números que o alinhamento (cliente e servidor) usa de fato.
  // Entrada inválida devolve '' — string vazia é o sentinela de "sem baseline".
  function fingerprint(numbers, window) {
    if (!isNumberList(numbers) || numbers.length === 0) return '';
    var w = (typeof window === 'number' && window > 0) ? window : FP_WINDOW;
    return numbers.slice(0, w).join(',');
  }

  /**
   * Conta quantos giros NOVOS entraram no topo da leitura, alinhando a cauda da
   * leitura nova com a cabeça da anterior (subsequência ORDENADA e POSICIONAL —
   * robusto a números repetidos, que são a norma em 37 casas).
   *
   * @param {boolean} [strict=true] Disciplina de evidência SPR-V2. `false` reproduz
   *   BIT A BIT o algoritmo v3.9.1 (sem k=0, sem overlap mínimo, "1 conservador"
   *   quando nada alinha) — é o rollback de 1ª camada (`DIR20_ENABLED=false`),
   *   mantido aqui para ser TESTÁVEL em vez de código morto no service worker.
   * @returns {{k:number, matched:boolean, overlap:number, reason:string}}
   *   `matched:false` significa LEITURA SUSPEITA, nunca "1 giro novo".
   */
  function countNewSpins(newArr, oldArr, strict) {
    var isStrict = (strict === undefined) ? true : !!strict;

    if (!isNumberList(newArr) || !isNumberList(oldArr)) {
      return isStrict
        ? { k: 0, matched: false, overlap: 0, reason: REASON.INVALID_INPUT }
        : { k: 1, matched: true, overlap: 0, reason: REASON.LEGACY_ASSUMED };
    }
    if (newArr.length === 0) {
      return isStrict
        ? { k: 0, matched: false, overlap: 0, reason: REASON.EMPTY_NEW }
        : { k: 1, matched: true, overlap: 0, reason: REASON.LEGACY_ASSUMED };
    }
    if (oldArr.length === 0) {
      return isStrict
        ? { k: 0, matched: false, overlap: 0, reason: REASON.EMPTY_OLD }
        : { k: 1, matched: true, overlap: 0, reason: REASON.LEGACY_ASSUMED };
    }

    var maxK = Math.min(newArr.length, MAX_K);
    for (var k = isStrict ? 0 : 1; k <= maxK; k++) {
      var overlapLen = Math.min(oldArr.length, newArr.length - k);
      if (overlapLen <= 0) break;
      // k=0 é noop absoluto (nada é enviado, nada flipa): overlap curto é inofensivo.
      // k>=1 move a fase — exige prova real.
      if (isStrict && k >= 1 && overlapLen < MIN_OVERLAP) break;

      var match = true;
      for (var i = 0; i < overlapLen; i++) {
        if (newArr[k + i] !== oldArr[i]) { match = false; break; }
      }
      if (match) {
        return {
          k: k,
          matched: true,
          overlap: overlapLen,
          reason: k === 0 ? REASON.IDENTICAL : REASON.ALIGNED
        };
      }
    }
    return isStrict
      ? { k: 0, matched: false, overlap: 0, reason: REASON.NO_ALIGNMENT }
      : { k: 1, matched: true, overlap: 0, reason: REASON.LEGACY_ASSUMED };
  }

  // Após N skips consecutivos a leitura deixa de ser "ruído" e vira "outra realidade":
  // re-ancora o baseline SEM enviar giro (o servidor recupera o gap — SPR-V1).
  function decideRebaseline(streak, maxSkips) {
    var limit = (typeof maxSkips === 'number' && maxSkips > 0) ? maxSkips : DEFAULT_MAX_SKIPS;
    return (typeof streak === 'number' && isFinite(streak)) ? streak >= limit : false;
  }

  function phaseFlip(d) { return d === 'horario' ? 'anti-horario' : 'horario'; }

  /**
   * Decisão PURA de um tick de leitura. O background só executa efeitos.
   * Isto é o que torna a DoD ("não alinhou ⇒ zero envio, zero flip, baseline intacto")
   * verificável de forma determinística em `node --test`.
   *
   * @param {object} input
   *   numbers          Array<number> lido do frame escolhido (mais recente no índice 0)
   *   baseline         Array<number> baseline anterior (state.results)
   *   baselineHash     string fingerprint anterior (state.lastHash)
   *   currentDirection 'horario' | 'anti-horario'  (fase do PRÓXIMO giro)
   *   unalignedStreak  number  skips consecutivos acumulados
   *   maxSkips         number  limite de skips antes do re-baseline
   *   tableNow         string|null  mesa lida agora
   *   tableAtBaseline  string|null  mesa registrada quando o baseline foi ancorado
   *   strict           boolean      false = modo legado v3.9.1 (kill-switch)
   * @returns {{action:string, k:number, overlap:number, reason:string,
   *            sendDir:string|null, nextDir:string|null, streak:number,
   *            newBaseline:Array<number>|null, newHash:string|null,
   *            sendHistorico:boolean, tableChanged:boolean}}
   */
  function decideTick(input) {
    var opt = input || {};
    var numbers = Array.isArray(opt.numbers) ? opt.numbers : [];
    var baseline = Array.isArray(opt.baseline) ? opt.baseline : [];
    var baselineHash = typeof opt.baselineHash === 'string' ? opt.baselineHash : '';
    var dir = (opt.currentDirection === 'anti-horario') ? 'anti-horario' : 'horario';
    var streak = (typeof opt.unalignedStreak === 'number' && opt.unalignedStreak >= 0)
      ? opt.unalignedStreak : 0;
    var maxSkips = opt.maxSkips;
    var tableNow = opt.tableNow || null;
    var tableAtBaseline = opt.tableAtBaseline || null;
    var isStrict = (opt.strict === undefined) ? true : !!opt.strict;

    var out = {
      action: 'noop',
      k: 0,
      overlap: 0,
      reason: '',
      sendDir: null,
      nextDir: null,
      streak: streak,
      newBaseline: null,
      newHash: null,
      sendHistorico: false,
      tableChanged: false
    };

    if (!isNumberList(numbers) || numbers.length === 0) {
      out.action = 'skip';
      out.reason = REASON.EMPTY_NEW;
      out.streak = streak + 1;
      return out;
    }

    var newHash = fingerprint(numbers, isStrict ? FP_WINDOW : LEGACY_FP_WINDOW);
    var window12 = numbers.slice(0, FP_WINDOW);

    // Primeira leitura da vida (ou pós-reset): ancora sem inventar giro.
    if (baselineHash === '' || baseline.length === 0) {
      out.action = 'baseline_init';
      out.reason = 'baseline_init';
      out.newBaseline = window12;
      out.newHash = newHash;
      out.streak = 0;
      out.sendHistorico = true;
      return out;
    }

    // Fingerprint idêntico: o DOM não mudou. Nada a decidir.
    if (newHash === baselineHash) {
      out.action = 'noop';
      out.reason = REASON.IDENTICAL;
      out.k = 0;
      out.overlap = Math.min(baseline.length, numbers.length);
      out.streak = 0;
      return out;
    }

    var res = countNewSpins(numbers, baseline, isStrict);
    out.k = res.k;
    out.overlap = res.overlap;
    out.reason = res.reason;

    if (!res.matched) {
      out.streak = streak + 1;
      if (decideRebaseline(out.streak, maxSkips)) {
        // Troca de mesa é a ÚNICA evidência que autoriza `historico_inicial`; um gap
        // na mesma mesa é re-baseline silencioso (o servidor já tem o histórico).
        out.tableChanged = !!(tableNow && tableAtBaseline && tableNow !== tableAtBaseline);
        out.action = 'rebaseline';
        out.newBaseline = window12;
        out.newHash = newHash;
        out.sendHistorico = out.tableChanged;
        out.streak = 0;
        return out;
      }
      out.action = 'skip';
      return out;
    }

    if (res.k === 0) {
      // Re-render posicionalmente idêntico com fingerprint diferente = leitura truncada
      // (o DOM devolveu menos números). Noop absoluto: NÃO empobrece o baseline.
      out.action = 'noop';
      out.reason = 'truncated_same_prefix';
      out.streak = 0;
      return out;
    }

    // k >= 1 com prova suficiente: giro(s) real(is).
    out.action = 'send';
    out.sendDir = (res.k % 2 === 1) ? dir : phaseFlip(dir);
    out.nextDir = phaseFlip(out.sendDir);
    out.newBaseline = window12;
    out.newHash = newHash;
    out.streak = 0;
    return out;
  }

  // ---------------------------------------------------------------------------
  // Primitivas de serialização (puras, sem Chrome) usadas pelo background.
  // ---------------------------------------------------------------------------

  // Fila serial: garante que todo read-modify-write do state aconteça um de cada vez.
  // Sem isto, "último a escrever ganha" apaga baseline/contadores de outro fluxo.
  function createSerialQueue() {
    var chain = Promise.resolve();
    function run(fn) {
      var result = chain.then(function () { return fn(); });
      // A cadeia NUNCA pode morrer por rejeição: o próximo mutador ficaria órfão.
      chain = result.then(function () { }, function () { });
      return result;
    }
    return { run: run };
  }

  // Guard de reentrância: o tick anterior ainda rodando ⇒ o novo desiste (não enfileira),
  // porque enfileirar leituras atrasadas só multiplica envios do mesmo giro.
  function createReentrancyGuard() {
    var busy = false;
    var skipped = 0;
    function run(fn) {
      if (busy) {
        skipped++;
        return Promise.resolve({ skipped: true, value: undefined });
      }
      busy = true;
      var p;
      try {
        p = Promise.resolve(fn());
      } catch (e) {
        busy = false;
        return Promise.reject(e);
      }
      return p.then(function (value) {
        busy = false;
        return { skipped: false, value: value };
      }, function (err) {
        busy = false;
        throw err;
      });
    }
    return {
      run: run,
      isBusy: function () { return busy; },
      skippedCount: function () { return skipped; }
    };
  }

  // Gate de re-hidratação: promise de topo, criada uma vez por wake do service worker.
  // Todo consumidor da FASE espera por ela — senão o 1º tick pós-wake envia a literal
  // 'horario' em vez da fase persistida.
  function createHydrationGate(loader) {
    var promise = null;
    function ready() {
      if (!promise) {
        promise = Promise.resolve()
          .then(function () { return loader(); })
          // Falha de storage não pode travar o SW para sempre: degrada com graça.
          .then(function (v) { return v; }, function () { return null; });
      }
      return promise;
    }
    function reset() { promise = null; }
    return { ready: ready, reset: reset };
  }

  return {
    FP_WINDOW: FP_WINDOW,
    LEGACY_FP_WINDOW: LEGACY_FP_WINDOW,
    MAX_K: MAX_K,
    MIN_OVERLAP: MIN_OVERLAP,
    DEFAULT_MAX_SKIPS: DEFAULT_MAX_SKIPS,
    REASON: REASON,
    fingerprint: fingerprint,
    countNewSpins: countNewSpins,
    decideRebaseline: decideRebaseline,
    decideTick: decideTick,
    phaseFlip: phaseFlip,
    createSerialQueue: createSerialQueue,
    createReentrancyGuard: createReentrancyGuard,
    createHydrationGate: createHydrationGate
  };
}));
