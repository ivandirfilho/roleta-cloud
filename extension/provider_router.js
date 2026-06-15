// provider_router.js
// Auto-detecção de provider (zero-upload) — §4.9 de passos_escuta_junho.md.
// Classificador de fingerprint ponderado (estilo Wappalyzer): URL/host primário,
// com gancho para DOM/meta signals. Regra-baseado, determinístico, testável em Node.
//
// Carregado via importScripts em background.js (service worker) e também usável
// no contexto da página. A tabela PROVIDER_DETECTION centraliza o que antes estava
// espalhado em deal_capture.js (host->provider).

(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  Object.assign(root, api);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  // Fonte única da verdade da detecção. hostPatterns vêm de deal_capture.js:18-21.
  // available=true ⇒ existe manifest empacotado em manifestPath.
  const PROVIDER_DETECTION = [
    {
      id: 'evolution',
      displayName: 'Evolution Gaming',
      hostPatterns: ['evo-games', 'evolution'],
      manifestPath: 'providers/evolution.json',
      available: true,
    },
    {
      id: 'pragmatic',
      displayName: 'Pragmatic Play Live',
      hostPatterns: ['pragmatic', 'pragmaticplaylive'],
      manifestPath: 'providers/pragmatic.json',
      available: false,
    },
    {
      id: 'playtech',
      displayName: 'Playtech',
      hostPatterns: ['playtech', 'iconic21'],
      manifestPath: 'providers/playtech.json',
      available: false,
    },
    {
      id: 'imagine',
      displayName: 'Imagine Live',
      hostPatterns: ['imagine'],
      manifestPath: 'providers/imagine.json',
      available: false,
    },
  ];

  // Hosts que claramente não são mesa de cassino — evita falso start (NB-03).
  const IRRELEVANT_HOST_HINTS = [
    'google.', 'gstatic.', 'doubleclick.', 'facebook.', 'fbcdn.',
    'youtube.', 'recaptcha', 'cloudflare', 'hotjar', 'googletagmanager',
  ];

  function hostOf(url) {
    if (!url) return '';
    try {
      return new URL(url).host.toLowerCase();
    } catch (e) {
      return String(url).toLowerCase();
    }
  }

  function isIrrelevantHost(host) {
    const h = (host || '').toLowerCase();
    if (!h) return true;
    return IRRELEVANT_HOST_HINTS.some((hint) => h.includes(hint));
  }

  function getProvider(providerId) {
    return PROVIDER_DETECTION.find((p) => p.id === providerId) || null;
  }

  function manifestPathFor(providerId) {
    const p = getProvider(providerId);
    return p ? p.manifestPath : null;
  }

  // host (string) -> providerId | null
  function matchHostToProvider(host) {
    const h = (host || '').toLowerCase();
    if (!h) return null;
    for (const p of PROVIDER_DETECTION) {
      if (p.hostPatterns.some((pat) => h.includes(pat))) return p.id;
    }
    return null;
  }

  // url (string) -> providerId | null
  function detectFromUrl(url) {
    return matchHostToProvider(hostOf(url));
  }

  // Modelo Wappalyzer-style: combina sinais ponderados em uma confiança 0..1.
  // signals = { url:boolean, dom:number(0..1), meta:boolean }
  function scoreProvider(signals, weights) {
    const w = Object.assign({ url: 5, dom: 3, meta: 2 }, weights || {});
    const s = signals || {};
    const got =
      (s.url ? w.url : 0) +
      (s.dom ? w.dom * Math.min(1, Math.max(0, Number(s.dom) || 0)) : 0) +
      (s.meta ? w.meta : 0);
    const max = w.url + w.dom + w.meta;
    return max ? Math.min(1, got / max) : 0;
  }

  // Recebe a lista de URLs dos frames da aba (webNavigation.getAllFrames) e
  // decide o provider. URL match é o sinal mais forte; exige margem sobre o 2º
  // colocado, senão devolve providerId:null (ambíguo → pedir override). NB-03.
  function detectFromFrames(frameUrls) {
    const urls = (frameUrls || []).filter(Boolean);
    const scores = {}; // providerId -> { count, matchedUrl }

    for (const u of urls) {
      const host = hostOf(u);
      if (isIrrelevantHost(host)) continue;
      const pid = matchHostToProvider(host);
      if (!pid) continue;
      if (!scores[pid]) scores[pid] = { count: 0, matchedUrl: u };
      scores[pid].count += 1;
    }

    const entries = Object.entries(scores);
    if (!entries.length) {
      return { providerId: null, confidence: 0, matchedUrl: null, ambiguous: false, scores };
    }

    entries.sort((a, b) => b[1].count - a[1].count);
    const [bestId, bestVal] = entries[0];
    const secondCount = entries[1] ? entries[1][1].count : 0;

    // Empate entre dois providers distintos ⇒ ambíguo (NB-03).
    const ambiguous = entries.length > 1 && bestVal.count === secondCount;

    // URL match garante confiança base 0.6; cada frame extra reforça.
    const confidence = Math.min(1, 0.6 + 0.1 * (bestVal.count - 1));

    return {
      providerId: ambiguous ? null : bestId,
      confidence: ambiguous ? confidence * 0.5 : confidence,
      matchedUrl: bestVal.matchedUrl,
      ambiguous,
      scores,
    };
  }

  return {
    PROVIDER_DETECTION,
    hostOf,
    isIrrelevantHost,
    getProvider,
    manifestPathFor,
    matchHostToProvider,
    detectFromUrl,
    detectFromFrames,
    scoreProvider,
  };
});
