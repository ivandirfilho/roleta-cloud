(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
  Object.assign(root, api);
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function cleanText(value, maxLen = 120) {
    if (value == null) return null;
    const text = String(value).trim();
    return text ? text.slice(0, maxLen) : null;
  }

  function normalizeProviderName(raw) {
    const text = cleanText(raw, 80);
    if (!text) return null;
    const lower = text.toLowerCase();
    if (lower.includes('evolution') || lower.includes('evo-games')) return 'evolution';
    if (lower.includes('playtech') || lower.includes('iconic21')) return 'playtech';
    if (lower.includes('imagine')) return 'imagine';
    if (lower.includes('pragmatic')) return 'pragmatic';
    return lower;
  }

  function getUrlParam(rawUrl, key) {
    const url = cleanText(rawUrl, 2000);
    if (!url) return null;
    const safeKey = String(key).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const pattern = new RegExp(`[?#&]${safeKey}=([^&#]+)`, 'i');
    const match = url.match(pattern);
    if (!match) return null;
    try {
      return decodeURIComponent(match[1]);
    } catch (_) {
      return match[1];
    }
  }

  function scoreFrame(frame) {
    if (!frame || typeof frame !== 'object') return -1;
    const url = cleanText(frame.url, 2000) || '';
    let score = 0;
    if (frame.isPotentialGame) score += 4;
    if (frame.isEvolution || /evo-games|evolution/i.test(url)) score += 5;
    if (!frame.isMainFrame) score += 2;
    if (/table_id=|provider=|game=/.test(url)) score += 3;
    if (/roulette/i.test(url)) score += 1;
    return score;
  }

  function pickGameFrame(frames) {
    if (!Array.isArray(frames) || frames.length === 0) return null;
    return [...frames]
      .filter(Boolean)
      .sort((a, b) => scoreFrame(b) - scoreFrame(a))[0] || null;
  }

  function extractDealMetaFromExtractorData(extractorData) {
    if (!extractorData || typeof extractorData !== 'object') return null;
    const frames = extractorData?._detectedFrames?.frames || [];
    const gameFrame = pickGameFrame(frames);
    const rawUrl = gameFrame?.url || extractorData?._meta?.source?.url || null;
    const provider =
      normalizeProviderName(getUrlParam(rawUrl, 'provider')) ||
      normalizeProviderName(extractorData?._meta?.provider?.name) ||
      null;
    const table =
      cleanText(getUrlParam(rawUrl, 'table_id'), 80) ||
      cleanText(getUrlParam(rawUrl, 'table'), 80) ||
      null;

    // FIX 14/06 (DEAL-AUDIT C2): popular dealer/round_id a partir de
    // data.session quando v18.2+ trouxer essa secao no JSON. Antes ficava
    // hardcoded null e o helper era inerte mesmo com schema novo.
    const session = extractorData?.data?.session || null;
    const dealer = cleanText(
      session?.dealer?.name?.value ??
      session?.dealer?.name?.innerText ??
      session?.dealer?.value ??
      null,
      120,
    );
    const round_id = cleanText(
      session?.round?.id?.value ??
      session?.round?.id?.innerText ??
      session?.round?.value ??
      null,
      80,
    );

    if (!provider && !table && !dealer && !round_id) return null;

    return {
      dealer,
      table,
      provider,
      round_id,
      captured_at: Date.now(),
    };
  }

  function mergeDealMeta(baseMeta, extraMeta) {
    const base = baseMeta && typeof baseMeta === 'object' ? baseMeta : {};
    const extra = extraMeta && typeof extraMeta === 'object' ? extraMeta : {};
    const merged = {
      dealer: cleanText(extra.dealer ?? base.dealer, 120),
      table: cleanText(extra.table ?? base.table, 80),
      provider: cleanText(extra.provider ?? base.provider, 40),
      round_id: cleanText(extra.round_id ?? base.round_id, 80),
      captured_at: extra.captured_at ?? base.captured_at ?? Date.now(),
    };
    return (merged.dealer || merged.table || merged.provider || merged.round_id) ? merged : null;
  }

  return {
    extractDealMetaFromExtractorData,
    mergeDealMeta,
    normalizeProviderName,
  };
});
