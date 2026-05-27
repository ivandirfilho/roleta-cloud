// SP-11 DEAL-01 (27/05) — captura DOM de dealer/table/provider via MutationObserver.
// Estrutura intencionalmente desacoplada: cada provider tem selectors em
// PROVIDER_SELECTORS. Persiste em chrome.storage.local.dealMeta para o
// background.js incluir no payload `novo_resultado` (SP-12).
//
// NOTA: Este script roda em paginas alvo. Adicionar match patterns em
// manifest.json (futuro). Por ora, importavel em content.js via <script>.

(function () {
  'use strict';

  // Detecta provider pela URL/host.
  const HOST = (location.host || '').toLowerCase();
  let provider = null;
  if (HOST.includes('evolution')) provider = 'evolution';
  else if (HOST.includes('playtech') || HOST.includes('iconic21')) provider = 'playtech';
  else if (HOST.includes('imagine')) provider = 'imagine';
  else if (HOST.includes('pragmatic')) provider = 'pragmatic';

  // Selectors por provider (atualizar conforme DOM real). Cada entrada:
  //  - dealer: CSS selector para nome do dealer
  //  - table:  CSS selector ou regex sobre URL para id da mesa
  //  - round:  CSS selector para id do round
  const PROVIDER_SELECTORS = {
    evolution: {
      dealer: '[data-role="dealer-name"], .dealer-name, [class*="dealerName"]',
      table:  '[data-role="game-title"], .game-title, [class*="tableName"]',
      round:  '[data-role="game-id"], .game-id',
    },
    playtech: {
      dealer: '.dealer__name, .game-info__dealer',
      table:  '.game-info__title',
      round:  '.game-info__round-id',
    },
    imagine: {
      dealer: '.dealer-info-name',
      table:  '.table-info-name',
      round:  '.round-info-id',
    },
    pragmatic: {
      dealer: '[data-test="dealer-name"]',
      table:  '[data-test="game-title"]',
      round:  '[data-test="round-id"]',
    },
  };

  function pick(sel) {
    if (!sel) return null;
    try {
      const el = document.querySelector(sel);
      return el ? (el.textContent || '').trim().slice(0, 120) || null : null;
    } catch (_) { return null; }
  }

  function snapshot() {
    if (!provider) return null;
    const cfg = PROVIDER_SELECTORS[provider] || {};
    const meta = {
      provider,
      dealer:   pick(cfg.dealer),
      table:    pick(cfg.table),
      round_id: pick(cfg.round),
      captured_at: Date.now(),
    };
    if (!meta.dealer && !meta.table && !meta.round_id) return null;
    return meta;
  }

  let lastJson = '';
  function publish() {
    const meta = snapshot();
    if (!meta) return;
    const j = JSON.stringify(meta);
    if (j === lastJson) return;
    lastJson = j;
    try {
      chrome.storage && chrome.storage.local && chrome.storage.local.set({ dealMeta: meta });
      chrome.runtime && chrome.runtime.sendMessage &&
        chrome.runtime.sendMessage({ action: 'dealMetaUpdate', dealMeta: meta });
    } catch (_) { /* extension context invalido — ignora */ }
  }

  // Observa mudancas no body para capturar mudancas de dealer/mesa.
  try {
    const obs = new MutationObserver(() => { publish(); });
    obs.observe(document.body || document.documentElement, {
      subtree: true, childList: true, characterData: true,
    });
  } catch (_) { /* DOM nao disponivel ainda */ }

  // Polling defensivo a cada 3s para casos onde MutationObserver perde eventos.
  setInterval(publish, 3000);
  publish();
})();
