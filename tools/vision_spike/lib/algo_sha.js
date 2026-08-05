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
   * Monta o buffer canônico que será hasheado.
   * @param {function(string): Uint8Array} readBytes  leitor síncrono de um arquivo do spike
   */
  function canonicalBytes(readBytes) {
    var chunks = [];
    for (var i = 0; i < ALGORITHM_FILES.length; i++) {
      chunks.push(utf8(ALGORITHM_FILES[i]));
      chunks.push(readBytes(ALGORITHM_FILES[i]));
    }
    return concatBytes(chunks);
  }

  return {
    ALGORITHM_FILES: ALGORITHM_FILES,
    SHA_LENGTH: SHA_LENGTH,
    canonicalBytes: canonicalBytes,
    _utf8: utf8,
    _concatBytes: concatBytes
  };
}));
