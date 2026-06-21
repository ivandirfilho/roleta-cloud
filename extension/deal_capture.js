// SP-11 DEAL-01 (27/05) — captura DOM de dealer/table/provider via MutationObserver.
// Estrutura intencionalmente desacoplada: cada provider tem selectors em
// PROVIDER_SELECTORS. Persiste em chrome.storage.local.dealMeta para o
// background.js incluir no payload `novo_resultado` (SP-12).
//
// NOTA: Este script roda em paginas alvo. Adicionar match patterns em
// manifest.json (futuro). Por ora, importavel em content.js via <script>.

// BUG-1 FIX 21/06 (auditoria_pos_foto): provider normalization PURA e testável.
// Antes, o fallback emitia `host:<dominio>` para frames sem marca conhecida —
// frames de analytics (googletagmanager/doubleclick/youtube) e o proprio
// dashboard (roleta.xma-ia.com) vazavam como "provider" e poluiam
// decisions.provider (~2100 linhas). Agora: recupera a marca pelo dominio do
// iframe (evo-games -> evolution) e, se nao reconhecer, emite 'unknown' (nunca
// host:*). Espelha o guard server-side (models/input.py sanitize_provider) na
// ORIGEM. UMD: usavel no content script (self.DealProvider) e testavel via node.
(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.DealProvider = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  // marca canonica <- keywords de dominio (inclui o dominio real do iframe).
  const PROVIDER_DOMAIN_KEYWORDS = [
    ['evolution', ['evolution', 'evo-games']],
    ['playtech', ['playtech', 'iconic21']],
    ['pragmatic', ['pragmatic']],
    ['imagine', ['imagine']],
    ['ezugi', ['ezugi']],
  ];
  function matchHostBrand(host) {
    const h = (host || '').toLowerCase();
    if (!h) return null;
    for (const pair of PROVIDER_DOMAIN_KEYWORDS) {
      const brand = pair[0], kws = pair[1];
      if (kws.some(function (k) { return h.indexOf(k) !== -1; })) return brand;
    }
    return null;
  }
  function normalizeProvider(host, rawProvider) {
    // marca limpa ja informada passa intacta; host:* nunca passa.
    if (rawProvider && String(rawProvider).toLowerCase().indexOf('host:') !== 0) {
      return rawProvider;
    }
    return matchHostBrand(host) || 'unknown';
  }
  // BUG-5 FIX 21/06 (auditoria pos-reload): um frame so deve publicar dealMeta se
  // carrega SINAL REAL — marca de provider reconhecida OU dealer/table/round. Frames
  // de analytics (doubleclick/youtube/instagram/fls) e o proprio dashboard tem
  // provider='unknown' e nada mais: NAO podem publicar (senao vencem a corrida do
  // chrome.storage.local.dealMeta e sobrescrevem o 'evolution' do frame do jogo).
  function hasUsefulSignal(meta) {
    if (!meta) return false;
    var known = meta.provider && String(meta.provider).toLowerCase() !== 'unknown';
    return !!(known || meta.dealer || meta.table || meta.round_id);
  }
  return { PROVIDER_DOMAIN_KEYWORDS: PROVIDER_DOMAIN_KEYWORDS, matchHostBrand: matchHostBrand, normalizeProvider: normalizeProvider, hasUsefulSignal: hasUsefulSignal };
});

(function () {
  'use strict';

  // Guard de ambiente: este IIFE e' content-script (depende de location/document).
  // Sob node/require (testes do helper UMD acima) ele NAO deve rodar.
  if (typeof location === 'undefined' || typeof document === 'undefined') return;

  // Detecta provider pela URL/host via helper compartilhado (BUG-1 fix 21/06).
  const HOST = (location.host || '').toLowerCase();
  const _DP = (typeof self !== 'undefined' && self.DealProvider) ||
    (typeof DealProvider !== 'undefined' ? DealProvider : null);
  // marca reconhecida (ou null) — usada p/ selectors + deteccao de frame irrelevante.
  const provider = _DP ? _DP.matchHostBrand(HOST) : null;
  // valor enviado ao server: marca|unknown, NUNCA host:* (BUG-1 fix 21/06).
  const PROVIDER_FALLBACK = _DP ? _DP.normalizeProvider(HOST, null) : (provider || 'unknown');

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
    // BUG-5 FIX 21/06: frame sem sinal real (analytics/dashboard) nao publica —
    // evita sobrescrever o provider do frame do jogo na corrida do dealMeta.
    if (_DP && !_DP.hasUsefulSignal(meta)) return;
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
