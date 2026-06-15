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
  function extractSessionData(sessionConfig, opts) {
    const cfg = sessionConfig || {};
    const options = opts || {};
    const doc = options.document
      || (typeof document !== 'undefined' ? document : null);

    const out = {
      dealer: null,
      round_id: null,
      table: null,
      frameUrl: (typeof location !== 'undefined' && location && location.href) || null
    };

    if (!doc) return out;

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

    return out;
  }

  // Combine per-frame results into one session object (first non-null wins).
  // Each frame's result is the output of extractSessionData.
  function combineSessionFrames(frameResults) {
    const out = { dealer: null, round_id: null, table: null, frameUrl: null };
    if (!Array.isArray(frameResults)) return out;
    for (const r of frameResults) {
      const data = (r && typeof r === 'object' && 'result' in r) ? r.result : r;
      if (!data || typeof data !== 'object') continue;
      if (!out.dealer && data.dealer) out.dealer = data.dealer;
      if (!out.round_id && data.round_id) out.round_id = data.round_id;
      if (!out.table && data.table) out.table = data.table;
      if (!out.frameUrl && data.frameUrl) out.frameUrl = data.frameUrl;
      if (out.dealer && out.round_id && out.table) break;
    }
    return out;
  }

  return {
    extractSessionData: extractSessionData,
    combineSessionFrames: combineSessionFrames
  };
});
