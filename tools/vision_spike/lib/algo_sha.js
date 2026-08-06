// SPR-V3 · vision_spike/lib/algo_sha.js — a MESMA receita de `algorithm_sha` nos dois mundos.
//
// Por que existe
// -------------
// `RESULTADO.md` exige que cada número de gate cite o SHA do algoritmo que o produziu, e
// `replay.js` avisa quando a captura foi gravada com outro algoritmo. Isso só funciona se
// quem GRAVA (navegador) e quem ANALISA (Node) computarem o mesmo hash — uma receita
// duplicada em dois arquivos vira, mais cedo ou mais tarde, dois hashes diferentes e um
// aviso permanente que todo mundo aprende a ignorar.
//
// A receita: para cada arquivo, na ordem de `ALGORITHM_FILES`, alimente o SHA-256 com o
// CAMINHO (UTF-8) e depois com os BYTES do arquivo. Devolva os 16 primeiros hex.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSAlgoSha = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var ALGORITHM_FILES = [
    'lib/unwrap.js', 'lib/ellipse.js', 'lib/direction_core.js', 'lib/pipeline.js'
  ];
  var SHA_LENGTH = 16;

  function concatBytes(chunks) {
    var total = 0, i;
    for (i = 0; i < chunks.length; i++) total += chunks[i].length;
    var out = new Uint8Array(total);
    var off = 0;
    for (i = 0; i < chunks.length; i++) { out.set(chunks[i], off); off += chunks[i].length; }
    return out;
  }

  function utf8(s) {
    if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(s);
    return new Uint8Array(Buffer.from(s, 'utf8'));
  }

  /**
   * Normaliza CRLF → LF **antes** de hashear.
   *
   * Sem isto o `algorithm_sha` não é o mesmo em máquinas diferentes: com
   * `core.autocrlf=true` (padrão do Git no Windows) o blob é LF mas a cópia de trabalho é
   * CRLF, então o mesmo commit produzia `fc91867da0601918` no Windows e outro hash no
   * Linux/CI. Um identificador de algoritmo que muda com o sistema operacional não
   * identifica algoritmo nenhum — e o aviso de divergência do `replay.js` viraria ruído
   * permanente, que é como uma trava morre.
   *
   * Só CRLF vira LF; um CR solto (Mac clássico) é preservado, porque mexer nele mudaria
   * bytes que não são fim de linha em nenhuma plataforma viva.
   */
  function normalizeEol(bytes) {
    var out = new Uint8Array(bytes.length);
    var n = 0;
    for (var i = 0; i < bytes.length; i++) {
      if (bytes[i] === 0x0D && bytes[i + 1] === 0x0A) continue;   // descarta o CR de CRLF
      out[n++] = bytes[i];
    }
    return out.subarray(0, n);
  }

  /**
   * Monta o buffer canônico que será hasheado: para cada arquivo, o CAMINHO (UTF-8) e
   * depois os BYTES **com EOL normalizado**.
   * @param {function(string): Uint8Array} readBytes  leitor síncrono de um arquivo do spike
   */
  function canonicalBytes(readBytes) {
    var chunks = [];
    for (var i = 0; i < ALGORITHM_FILES.length; i++) {
      chunks.push(utf8(ALGORITHM_FILES[i]));
      chunks.push(normalizeEol(readBytes(ALGORITHM_FILES[i])));
    }
    return concatBytes(chunks);
  }

  return {
    ALGORITHM_FILES: ALGORITHM_FILES,
    SHA_LENGTH: SHA_LENGTH,
    canonicalBytes: canonicalBytes,
    normalizeEol: normalizeEol,
    _utf8: utf8,
    _concatBytes: concatBytes
  };
}));
