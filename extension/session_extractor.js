// session_extractor.js
// Data-driven extraction of dealer/round/table from the live page.
// Loaded via importScripts in background.js (service worker context).
// Also injected via chrome.scripting.executeScript {func: extractSessionData}
// in the page context (all frames) — the function is self-contained.

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  Object.assign(root, api);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Extract dealer/round/table from a config block matching data.session
  // in extrator_completo.json schema v18.2.
  //
  // sessionConfig shape (all fields optional, all fallbackSelectors arrays):
  //   {
  //     dealer: { name: { selector, fallbackSelectors[], attribute, maxLen } },
  //     round:  { id:   { selector, fallbackSelectors[], attribute, maxLen } },
  //     table:  { name: { selector, fallbackSelectors[], attribute, maxLen } }
  //   }
  //
  // Returns: { dealer, round_id, table, frameUrl } (any field may be null)
  //
  // IMPORTANT — MV3 self-containment (DEAL-AUDIT 15/06): this function is injected
  // verbatim via chrome.scripting.executeScript({ func: extractSessionData }). Chrome
  // serialises ONLY this function body (Function.prototype.toString); helpers from the
  // surrounding module closure are NOT shipped. Referencing an outer helper makes the
  // page context throw "ReferenceError: <helper> is not defined", and the caller's
  // try/catch swallows it — so dealer/round/table silently come back null forever.
  // Therefore cleanText/probeSelectors MUST stay declared INSIDE this function body.
  function extractSessionData(sessionConfig, opts) {
    function cleanText(value, maxLen) {
      if (value == null) return null;
      const text = String(value).trim();
      if (!text) return null;
      return text.slice(0, Math.max(1, Number(maxLen) || 120));
    }

    function probeSelectors(doc, sels, attr, maxLen) {
      if (!doc || !sels || !sels.length) return null;
      const safeAttr = (attr || 'innerText');
      for (const sel of sels) {
        if (!sel) continue;
        try {
          const el = doc.querySelector(sel);
          if (!el) continue;
          let raw = '';
          if (safeAttr === 'innerText') {
            raw = el.innerText || el.textContent || '';
          } else if (safeAttr === 'textContent') {
            raw = el.textContent || '';
          } else {
            raw = (typeof el.getAttribute === 'function')
              ? (el.getAttribute(safeAttr) || '')
              : '';
          }
          const v = cleanText(raw, maxLen);
          if (v) return v;
        } catch (_) { /* try next selector */ }
      }
      return null;
    }

    const cfg = sessionConfig || {};
    const options = opts || {};
    const doc = options.document
      || (typeof document !== 'undefined' ? document : null);

    const out = {
      dealer: null,
      round_id: null,
      table: null,
      frameUrl: (typeof location !== 'undefined' && location && location.href) || null,
      isGameFrame: false
    };

    if (!doc) return out;

    // DEAL-AUDIT 15/06: marca se ESTE frame contem o jogo real (numeros da roleta),
    // usando o mesmo seletor que extractResultsFromPage. combineSessionFrames usa isso
    // para priorizar o frame do jogo e NAO capturar title/round/dealer de um frame de
    // lobby ou cross-sell (bug observado em prod: table='Blackjack Silver D' numa
    // sessao de roleta 'PorROU0000000001'). Self-contained (so querySelector nativo).
    try {
      out.isGameFrame = !!doc.querySelector('[data-role="recent-number"]');
    } catch (_) { /* querySelector pode lancar em selector raro */ }

    const blocks = [
      { key: 'dealer',   path: cfg.dealer && cfg.dealer.name },
      { key: 'round_id', path: cfg.round  && cfg.round.id   },
      { key: 'table',    path: cfg.table  && cfg.table.name }
    ];

    for (const b of blocks) {
      const node = b.path || {};
      const sels = [node.selector].concat(Array.isArray(node.fallbackSelectors) ? node.fallbackSelectors : []);
      out[b.key] = probeSelectors(doc, sels, node.attribute, node.maxLen);
    }

    // DEAL-AUDIT 15/06 — diagnostico opcional: quando o dealer NAO casa nenhum
    // seletor (caso real em prod: table casa mas dealer/round nao), varre o DOM por
    // elementos-folha cuja classe/atributo sugira nome de crupie/host/presenter e
    // devolve ate 8 candidatos {cls, role, txt}. Serve para o operador/telemetria
    // descobrir o seletor real sem chutar. Self-contained (sem closure); so roda
    // sob demanda (options.collectCandidates) para nao custar CPU em todo tick.
    if (options.collectCandidates && (!out.dealer || !out.round_id)) {
      try {
        const kw = /dealer|croupier|presenter|host[\s_-]?name|hostName/i;
        const cands = [];
        const all = doc.querySelectorAll('*');
        const limit = Math.min(all.length, 5000);
        for (let i = 0; i < limit && cands.length < 8; i++) {
          const el = all[i];
          if (el.children && el.children.length) continue;
          const cls = (el.className && el.className.toString) ? el.className.toString() : '';
          const role = (typeof el.getAttribute === 'function') ? (el.getAttribute('data-role') || '') : '';
          if (!kw.test(cls) && !kw.test(role)) continue;
          const txt = ((el.innerText || el.textContent || '') + '').trim();
          if (!txt) continue;
          cands.push({ cls: cls.slice(0, 60), role: role.slice(0, 40), txt: txt.slice(0, 40) });
        }
        if (cands.length) out.dealerCandidates = cands;
      } catch (_) { /* best-effort diagnostics */ }
    }

    return out;
  }

  // Combine per-frame results into one session object.
  // Each frame's result is the output of extractSessionData.
  // DEAL-AUDIT 15/06: frames do jogo (isGameFrame=true) tem PRIORIDADE sobre frames
  // de lobby/cross-sell, para nao capturar title/round/dealer de outra mesa. Entre
  // frames da mesma categoria mantem-se a ordem original (Array.sort estavel) =>
  // comportamento "first non-null wins" preservado dentro de cada categoria.
  function combineSessionFrames(frameResults) {
    const out = { dealer: null, round_id: null, table: null, frameUrl: null };
    if (!Array.isArray(frameResults)) return out;
    const frames = [];
    for (const r of frameResults) {
      const data = (r && typeof r === 'object' && 'result' in r) ? r.result : r;
      if (data && typeof data === 'object') frames.push(data);
    }
    frames.sort(function (a, b) {
      return (b && b.isGameFrame ? 1 : 0) - (a && a.isGameFrame ? 1 : 0);
    });
    for (const data of frames) {
      if (!out.dealer && data.dealer) out.dealer = data.dealer;
      if (!out.round_id && data.round_id) out.round_id = data.round_id;
      if (!out.table && data.table) out.table = data.table;
      if (!out.frameUrl && data.frameUrl) out.frameUrl = data.frameUrl;
      if (Array.isArray(data.dealerCandidates) && data.dealerCandidates.length) {
        out.dealerCandidates = (out.dealerCandidates || []).concat(data.dealerCandidates).slice(0, 8);
      }
      if (out.dealer && out.round_id && out.table) break;
    }
    return out;
  }

  return {
    extractSessionData: extractSessionData,
    combineSessionFrames: combineSessionFrames
  };
});
