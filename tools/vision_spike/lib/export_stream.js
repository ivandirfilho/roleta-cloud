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
// ⚠️ O FIO É JSON — e isso decide o formato ⚠️
// `chrome.runtime.Port.postMessage` **serializa em JSON**. Um `Uint8ClampedArray` mandado
// cru chega do outro lado como `{"0":12,"1":34,…}`: um objeto **sem `.length`**. A versão
// anterior deste módulo fazia exatamente isso, e o estrago era silencioso — `stride` virava
// `undefined`, `new Uint8Array(NaN)` dava comprimento 0, nada lançava, e o operador salvava
// um `frames.bin` de **0 byte** com a interface dizendo "300 frames, completo". Um arquivo
// vazio que se declara completo é pior que um erro: a coleta de campo só seria descoberta
// perdida na hora de rodar o replay, com a mesa já fechada.
// Por isso o wire é **base64** (1,33× o payload, contra ~3,5× de um array de números em
// JSON), com codificação/decodificação próprias — sem `btoa`/`atob`/`Buffer`, para que o
// MESMO código rode no navegador e no `node --test`. Nada aqui depende de structured clone,
// que não está garantido no Chrome suportado.
//
// Os frames continuam locais: o destino é um `download` no disco do operador.
//
// Este módulo é PURO (nenhuma API do Chrome), então a interrupção, a retomada e **a
// travessia do JSON** são testáveis em `node --test`.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSExportStream = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var DEFAULT_CHUNK = 1;          // frames por mensagem
  var DEFAULT_WINDOW = 2;         // lotes em voo antes de exigir ack (backpressure)
  var DEFAULT_STALL_MS = 8000;
  var WIRE = 'base64';            // versão do formato do fio; o receptor recusa o que não conhece

  var B64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  var B64_LOOKUP = (function () {
    var t = new Int16Array(256);
    for (var i = 0; i < 256; i++) t[i] = -1;
    for (var j = 0; j < B64_CHARS.length; j++) t[B64_CHARS.charCodeAt(j)] = j;
    return t;
  }());

  /** bytes → base64. Sem `btoa`: o mesmo código roda no SW, na página e no Node. */
  function toBase64(bytes) {
    var out = '';
    var i = 0;
    var n = bytes.length;
    var parts = [];
    for (; i + 2 < n; i += 3) {
      var v = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
      out += B64_CHARS[(v >> 18) & 63] + B64_CHARS[(v >> 12) & 63] +
        B64_CHARS[(v >> 6) & 63] + B64_CHARS[v & 63];
      if (out.length >= 8192) { parts.push(out); out = ''; }   // evita string gigante única
    }
    var rest = n - i;
    if (rest === 1) {
      var a = bytes[i] << 16;
      out += B64_CHARS[(a >> 18) & 63] + B64_CHARS[(a >> 12) & 63] + '==';
    } else if (rest === 2) {
      var b = (bytes[i] << 16) | (bytes[i + 1] << 8);
      out += B64_CHARS[(b >> 18) & 63] + B64_CHARS[(b >> 12) & 63] + B64_CHARS[(b >> 6) & 63] + '=';
    }
    parts.push(out);
    return parts.join('');
  }

  /** base64 → Uint8Array. Recusa caractere inválido em vez de produzir lixo silencioso. */
  function fromBase64(str) {
    if (typeof str !== 'string') throw new Error('base64 invalido: nao e string');
    var clean = str.length;
    while (clean > 0 && str.charCodeAt(clean - 1) === 61 /* '=' */) clean--;
    var out = new Uint8Array((clean * 3) >> 2);
    var acc = 0, bits = 0, o = 0;
    for (var i = 0; i < clean; i++) {
      var d = B64_LOOKUP[str.charCodeAt(i)];
      if (d < 0) throw new Error('base64 invalido: caractere na posicao ' + i);
      acc = (acc << 6) | d;
      bits += 6;
      if (bits >= 8) {
        bits -= 8;
        out[o++] = (acc >> bits) & 0xFF;
      }
    }
    return o === out.length ? out : out.subarray(0, o);
  }

  function isBytes(x) {
    return !!x && typeof x.length === 'number' && x.length >= 0 &&
      (x instanceof Uint8Array || x instanceof Uint8ClampedArray);
  }

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
      for (var i = next; i < end; i++) {
        var f = frames[i];
        if (!isBytes(f)) throw new Error('frame ' + i + ' nao e Uint8Array/Uint8ClampedArray');
        // base64 + `length` explícito: o receptor valida o que decodificou contra o que
        // foi declarado. Mandar a typed array crua faria o JSON do port entregar um
        // objeto sem `.length` do outro lado.
        batch.push({ index: i, b64: toBase64(f), length: f.length });
      }
      next = end;
      // `inFlight` sobe ANTES do post: num transporte síncrono (ou num teste) o ack pode
      // voltar de dentro do próprio `post`, e incrementar depois deixaria o contador
      // negativo — ou seja, a janela de backpressure deixaria de existir exatamente
      // quando o transporte é mais rápido que ela.
      inFlight++;
      sentBatches++;
      post({ type: 'frames', wire: WIRE, from: end - batch.length, to: end - 1, frames: batch });
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
      post({ type: 'meta', wire: WIRE, meta: o.meta, frameCount: frames.length, resumedFrom: next });
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
    var frames = [];               // esparso por índice, SEMPRE Uint8Array
    var meta = null;
    var expected = null;
    var received = 0;
    var lastMessageAt = null;
    var complete = false;
    var rejected = [];             // {index, reason} — nunca somem em silêncio
    var now = o.now || function () { return Date.now(); };

    /**
     * Decodifica UM frame do fio. Recusa tudo que não for base64 com `length` declarado —
     * inclusive o formato antigo (typed array crua), que atravessava o JSON do port como
     * `{"0":12,…}` e chegava aqui sem `.length`.
     */
    function decodeFrame(f) {
      if (!f || typeof f !== 'object') throw new Error('frame nao e objeto');
      if (typeof f.index !== 'number' || !(f.index >= 0)) throw new Error('frame sem index valido');
      if (typeof f.b64 !== 'string') {
        throw new Error('frame ' + f.index + ' sem campo `b64` (wire antigo? typed array crua ' +
          'nao sobrevive ao JSON do chrome.runtime.Port)');
      }
      if (typeof f.length !== 'number' || !(f.length > 0) || (f.length | 0) !== f.length) {
        throw new Error('frame ' + f.index + ' sem `length` declarado valido');
      }
      var bytes = fromBase64(f.b64);
      if (bytes.length !== f.length) {
        throw new Error('frame ' + f.index + ': decodificou ' + bytes.length +
          ' bytes, declarado ' + f.length);
      }
      return bytes;
    }

    /** @returns {Array} mensagens a enviar de volta (acks) */
    function handle(msg) {
      lastMessageAt = now();
      if (!msg) return [];
      if (msg.type === 'meta') {
        if (msg.wire && msg.wire !== WIRE) {
          throw new Error('wire desconhecido: ' + msg.wire + ' (esperado ' + WIRE + ')');
        }
        meta = msg.meta || meta;
        expected = msg.frameCount;
        return [];
      }
      if (msg.type === 'frames') {
        if (msg.wire && msg.wire !== WIRE) {
          throw new Error('wire desconhecido: ' + msg.wire + ' (esperado ' + WIRE + ')');
        }
        if (!Array.isArray(msg.frames)) throw new Error('lote sem array de frames');
        var ok = 0;
        for (var i = 0; i < msg.frames.length; i++) {
          var f = msg.frames[i];
          var idx = (f && typeof f.index === 'number') ? f.index : null;
          try {
            var bytes = decodeFrame(f);
            if (frames[f.index] === undefined) {
              frames[f.index] = bytes;
              received++;
            }
            ok++;
          } catch (e) {
            // Frame inválido NÃO é armazenado e NÃO é confirmado: ele continua "faltando",
            // então `complete` nunca vira true e `assemble()` recusa. Silenciar aqui seria
            // reintroduzir o arquivo de 0 byte que se declara completo.
            rejected.push({ index: idx, reason: e.message });
          }
        }
        // Só confirma o lote se TUDO nele entrou. Ack parcial faria o remetente seguir em
        // frente deixando buracos que só apareceriam no fim.
        return ok === msg.frames.length ? [{ type: 'ack', from: msg.from, to: msg.to }] : [];
      }
      if (msg.type === 'end') {
        expected = msg.frameCount != null ? msg.frameCount : expected;
        complete = (expected != null && expected > 0 && received >= expected &&
          missingFrom() === null && rejected.length === 0);
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
        hasMeta: !!meta,
        rejected: rejected.length,
        rejectedDetail: rejected.slice(0, 5)
      };
    }

    /**
     * Concatena na ordem. Falha ALTO em qualquer anomalia — captura incompleta não é
     * captura, e um arquivo de 0 byte que se diz completo é o pior resultado possível:
     * o operador só descobre a perda ao rodar o replay, com a mesa já fechada.
     */
    function assemble() {
      if (expected == null) throw new Error('export sem meta: nada a montar');
      if (!(expected > 0)) throw new Error('export com 0 frames: nada a montar');
      if (rejected.length) {
        throw new Error('export com ' + rejected.length + ' frame(s) recusado(s): ' +
          rejected.slice(0, 3).map(function (r) { return '#' + r.index + ' ' + r.reason; }).join(' · '));
      }
      var falta = missingFrom();
      if (falta !== null) throw new Error('export incompleto: falta o frame ' + falta);

      if (!isBytes(frames[0])) throw new Error('frame 0 nao e typed array (wire corrompido)');
      var stride = frames[0].length;
      if (!(stride > 0) || (stride | 0) !== stride) {
        throw new Error('stride invalido: ' + stride);
      }
      var out = new Uint8Array(stride * expected);
      for (var i = 0; i < expected; i++) {
        if (!isBytes(frames[i])) throw new Error('frame ' + i + ' nao e typed array');
        if (frames[i].length !== stride) throw new Error('frame ' + i + ' com tamanho divergente');
        out.set(frames[i], i * stride);
      }
      if (out.length === 0) throw new Error('montagem resultou em 0 bytes');
      return { meta: meta, bytes: out, frameCount: expected, stride: stride };
    }

    return {
      handle: handle, missingFrom: missingFrom, isStalled: isStalled,
      progress: progress, assemble: assemble,
      rejected: function () { return rejected.slice(); },
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
    WIRE: WIRE,
    toBase64: toBase64,
    fromBase64: fromBase64,
    createSender: createSender,
    createAssembler: createAssembler,
    createByteBudget: createByteBudget
  };
}));
