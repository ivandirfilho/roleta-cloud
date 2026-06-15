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
  // FIX 14/06 (DEAL-AUDIT C1): incluir 'evo-games' (dominio real do iframe
  // Evolution, e.g. a8-latam.evo-games.com). Sem isso, o provider ficava
  // 'null' dentro do iframe do jogo e dealer nunca era capturado.
  const HOST = (location.host || '').toLowerCase();
  let provider = null;
  if (HOST.includes('evolution') || HOST.includes('evo-games')) provider = 'evolution';
  else if (HOST.includes('playtech') || HOST.includes('iconic21')) provider = 'playtech';
  else if (HOST.includes('imagine')) provider = 'imagine';
  else if (HOST.includes('pragmatic')) provider = 'pragmatic';
  // Fallback: usa host como provider para permitir rastreio mesmo em
  // dominios novos (operador pode adicionar regra depois). DEAL audit 27/05.
  const PROVIDER_FALLBACK = provider || (HOST ? `host:${HOST}` : 'unknown');

  // FIX 14/06 (DEAL-AUDIT A1/A5): nao instalar observer/interval em frames
  // que claramente nao tem dealer (analytics, sw_iframe, about:blank).
  // Reduz custo de CPU em ~9 frames por aba para 1-2 frames relevantes.
  const IS_IRRELEVANT_FRAME = !provider && (
    HOST === '' ||
    HOST.includes('uol.com.br') ||
    HOST.includes('amazonaws.com') ||
    HOST.includes('sst.') ||
    HOST.includes('googletagmanager') ||
    HOST.includes('google-analytics')
  );

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
    const cfg = (provider && PROVIDER_SELECTORS[provider]) || {};
    const meta = {
      provider: PROVIDER_FALLBACK,
      dealer:   pick(cfg.dealer),
      table:    pick(cfg.table),
      round_id: pick(cfg.round),
      captured_at: Date.now(),
    };
    // Sempre publica (mesmo so com provider) para o server saber a origem.
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
      // FIX 14/06 (DEAL-AUDIT B2): log so quando mudar (lastJson ja garante
      // que so chegamos aqui em mudancas reais).
      console.log('[deal_capture] published', meta);
    } catch (_) { /* extension context invalido */ }
  }

  // FIX 14/06 (DEAL-AUDIT A1): throttle de 500ms no publish para evitar
  // centenas de calls/seg quando timer da roleta atualiza characterData.
  let pubTimer = null;
  let pubPending = false;
  function scheduledPublish() {
    if (pubTimer) { pubPending = true; return; }
    publish();
    pubTimer = setTimeout(() => {
      pubTimer = null;
      if (pubPending) { pubPending = false; scheduledPublish(); }
    }, 500);
  }

  // FIX 14/06 (DEAL-AUDIT A1/A5): pular observer/interval em frames sem
  // dealer (analytics, sw, blank). Custo zero nestes frames.
  if (IS_IRRELEVANT_FRAME) {
    return;
  }

  // Observa mudancas no body para capturar mudancas de dealer/mesa.
  try {
    const obs = new MutationObserver(() => { scheduledPublish(); });
    obs.observe(document.body || document.documentElement, {
      subtree: true, childList: true, characterData: true,
    });
  } catch (_) { /* DOM nao disponivel ainda */ }

  // Polling defensivo a cada 3s para casos onde MutationObserver perde eventos.
  setInterval(scheduledPublish, 3000);
  publish();
})();
