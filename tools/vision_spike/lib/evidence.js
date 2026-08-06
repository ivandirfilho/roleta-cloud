// SPR-V3 · vision_spike/lib/evidence.js — envelope de evidência do spike.
//
// Existe por UMA razão: impedir que um número de bancada seja lido como número de campo.
// Todo artefato do spike carrega:
//   • `evidence_class` — 'synthetic' | 'fixture' | 'field'
//   • `eligible_for_go_gates` — só `field` é elegível
//   • `spike_version`, `format_version`, `captured_at`
//
// Regra que o `RESULTADO.md` cita: **nenhum gate de GO pode ser preenchido com
// `eligible_for_go_gates: false`.** Não é convenção de estilo; é o que separa o spike de
// uma profecia auto-realizável.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSEvidence = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var SPIKE_VERSION = 'v3a-1';
  var FORMAT_VERSION = 1;

  var CLASS = {
    SYNTHETIC: 'synthetic',  // gerado por lib/synthetic.js — testa o CÓDIGO
    FIXTURE: 'fixture',      // <video> local (probe/fixture_video.html) — testa a PLATAFORMA local
    FIELD: 'field'           // mesa Evolution ao vivo, com operador — única elegível aos gates
  };

  function eligible(evidenceClass) { return evidenceClass === CLASS.FIELD; }

  /**
   * @param {string} kind  'E0' | 'E0b' | 'E1' | 'capture' | 'collector'
   */
  function envelope(kind, evidenceClass, payload, extra) {
    if (Object.keys(CLASS).map(function (k) { return CLASS[k]; }).indexOf(evidenceClass) < 0) {
      throw new Error('evidence_class invalido: ' + evidenceClass);
    }
    return Object.assign({
      format: 'vision_spike_evidence',
      format_version: FORMAT_VERSION,
      spike_version: SPIKE_VERSION,
      kind: kind,
      evidence_class: evidenceClass,
      eligible_for_go_gates: eligible(evidenceClass),
      captured_at: new Date().toISOString(),
      payload: payload
    }, extra || {});
  }

  return {
    SPIKE_VERSION: SPIKE_VERSION,
    FORMAT_VERSION: FORMAT_VERSION,
    CLASS: CLASS,
    eligible: eligible,
    envelope: envelope
  };
}));
