// SPR-V3 · vision_spike/lib/export_stream.js — transferência de captura com ACK e RETOMADA.
//
// O problema que este módulo resolve
// ----------------------------------
// A captura para o gate de sinal tem ≥250 frames de ROI (~100 MB). A versão anterior
// despejava TODOS os frames de uma vez pelo port, cada um convertido com `Array.from`
// (um array JS de 330 mil números por frame). Sem backpressure, sem ack e sem retomada:
// se o popup fechasse no meio — e o popup fecha ao primeiro clique fora dele — a
// transferência inteira se perdia, e uma coleta de campo de 45 minutos ia junto.
//
// Desenho: o REMETENTE (content script, que tem os pixels) só envia o próximo lote depois
// que o DESTINATÁRIO confirma o anterior. O destinatário guarda o que já recebeu e, se a
// conexão cair, reconecta e pede `resume` a partir do primeiro índice que falta. O
// destinatário durável é uma PÁGINA de extensão (`probe/export.html`), não o popup.
//
// Os frames continuam locais: o destino é um `download` no disco do operador.
//
// Este módulo é PURO (nenhuma API do Chrome), então a interrupção e a retomada são
// testáveis em `node --test` — que é o único jeito de saber que a retomada funciona sem
// depender de alguém fechar um popup na hora certa.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSExportStream = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var DEFAULT_CHUNK = 1;          // frames por mensagem
  var DEFAULT_WINDOW = 2;         // lotes em voo antes de exigir ack (backpressure)
  var DEFAULT_STALL_MS = 8000;

  /**
   * Lado que TEM os pixels.
   * @param {{frames:Array, meta:Object, post:Function, chunkFrames?:number, window?:number}} o
   */
  function createSender(o) {
    var frames = o.frames || [];
    var post = o.post;
    var chunk = Math.max(1, o.chunkFrames || DEFAULT_CHUNK);
    var win = Math.max(1, o.window || DEFAULT_WINDOW);
    var next = 0;
    var inFlight = 0;
    var closed = false;
    var sentBatches = 0;

    function sendBatch() {
      if (closed || next >= frames.length) return false;
      var end = Math.min(frames.length, next + chunk);
      var batch = [];
      for (var i = next; i < end; i++) batch.push({ index: i, data: frames[i] });
      next = end;
      // `inFlight` sobe ANTES do post: num transporte síncrono (ou num teste) o ack pode
      // voltar de dentro do próprio `post`, e incrementar depois deixaria o contador
      // negativo — ou seja, a janela de backpressure deixaria de existir exatamente
      // quando o transporte é mais rápido que ela.
      inFlight++;
      sentBatches++;
      post({ type: 'frames', from: end - batch.length, to: end - 1, frames: batch });
      return true;
    }

    function pump() {
      while (!closed && inFlight < win && next < frames.length) {
        if (!sendBatch()) break;
      }
      if (!closed && next >= frames.length && inFlight === 0) {
        closed = true;
        post({ type: 'end', frameCount: frames.length });
      }
    }

    /** Começa (ou RECOMEÇA) a partir de `from`. Retomada é só isto: mover o cursor. */
    function start(from) {
      next = Math.max(0, from || 0);
      inFlight = 0;
      closed = false;
      post({ type: 'meta', meta: o.meta, frameCount: frames.length, resumedFrom: next });
      pump();
    }

    function onAck(index) {
      if (closed) return;
      if (inFlight > 0) inFlight--;
      void index;
      pump();
    }

    function stats() { return { next: next, inFlight: inFlight, sentBatches: sentBatches, closed: closed }; }

    return { start: start, onAck: onAck, stats: stats };
  }

  /**
   * Lado DURÁVEL (página de extensão). Acumula, confirma e sabe de onde recomeçar.
   * @param {{onNeedResume?:Function, stallMs?:number, now?:Function}} o
   */
  function createAssembler(o) {
    o = o || {};
    var frames = [];               // esparso por índice
    var meta = null;
    var expected = null;
    var received = 0;
    var lastMessageAt = null;
    var complete = false;
    var now = o.now || function () { return Date.now(); };

    /** @returns {Array} mensagens a enviar de volta (acks) */
    function handle(msg) {
      lastMessageAt = now();
      if (!msg) return [];
      if (msg.type === 'meta') {
        meta = msg.meta || meta;
        expected = msg.frameCount;
        return [];
      }
      if (msg.type === 'frames') {
        for (var i = 0; i < msg.frames.length; i++) {
          var f = msg.frames[i];
          if (frames[f.index] === undefined) {
            frames[f.index] = f.data;
            received++;
          }
        }
        return [{ type: 'ack', from: msg.from, to: msg.to }];
      }
      if (msg.type === 'end') {
        expected = msg.frameCount != null ? msg.frameCount : expected;
        complete = (expected != null && received >= expected && missingFrom() === null);
        return [];
      }
      return [];
    }

    /** Primeiro índice ainda ausente — é daqui que a retomada parte. `null` = nada falta. */
    function missingFrom() {
      if (expected == null) return 0;
      for (var i = 0; i < expected; i++) if (frames[i] === undefined) return i;
      return null;
    }

    /**
     * Travou? (nenhuma mensagem há `stallMs`). O relógio é REARMADO a cada mensagem —
     * inclusive depois do `meta`. A versão anterior armava o timeout uma vez e, se o
     * `meta` chegasse, ele nunca mais era rearmado: uma transferência que morresse no
     * meio ficava pendurada para sempre, sem erro e sem arquivo.
     */
    function isStalled(stallMs) {
      var limit = stallMs || o.stallMs || DEFAULT_STALL_MS;
      if (complete || lastMessageAt === null) return false;
      return (now() - lastMessageAt) > limit;
    }

    function progress() {
      return {
        received: received,
        expected: expected,
        missingFrom: missingFrom(),
        complete: complete,
        hasMeta: !!meta
      };
    }

    /** Concatena na ordem. Falha ALTO se faltar frame — captura incompleta não é captura. */
    function assemble() {
      if (expected == null) throw new Error('export sem meta: nada a montar');
      var falta = missingFrom();
      if (falta !== null) throw new Error('export incompleto: falta o frame ' + falta);
      var stride = frames[0].length;
      var out = new Uint8Array(stride * expected);
      for (var i = 0; i < expected; i++) {
        if (frames[i].length !== stride) throw new Error('frame ' + i + ' com tamanho divergente');
        out.set(frames[i], i * stride);
      }
      return { meta: meta, bytes: out, frameCount: expected, stride: stride };
    }

    return {
      handle: handle, missingFrom: missingFrom, isStalled: isStalled,
      progress: progress, assemble: assemble,
      touch: function () { lastMessageAt = now(); }
    };
  }

  /**
   * ORÇAMENTO DE BYTES cumulativo, consultado ANTES de alocar o próximo frame.
   *
   * A versão anterior gravava tudo e só então cortava o excedente — o corte devolvia
   * memória que já tinha sido alocada dentro do renderer de um terceiro, que é
   * exatamente o custo que o teto existia para não pagar. Aqui o teto é um limite de
   * CONSUMO: quando o próximo frame não cabe, a captura para.
   */
  function createByteBudget(maxBytes) {
    var used = 0;
    return {
      fits: function (nextBytes) {
        return !maxBytes || (used + nextBytes) <= maxBytes;
      },
      add: function (nextBytes) { used += nextBytes; return used; },
      used: function () { return used; },
      remaining: function () { return maxBytes ? Math.max(0, maxBytes - used) : Infinity; },
      maxBytes: maxBytes || 0
    };
  }

  return {
    DEFAULT_CHUNK: DEFAULT_CHUNK,
    DEFAULT_WINDOW: DEFAULT_WINDOW,
    DEFAULT_STALL_MS: DEFAULT_STALL_MS,
    createSender: createSender,
    createAssembler: createAssembler,
    createByteBudget: createByteBudget
  };
}));
