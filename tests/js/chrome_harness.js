'use strict';
// Harness do SPR-V2: carrega o `background.js` REAL do service worker dentro de um
// `node:vm` com um fake mínimo da API `chrome`.
//
// Por que carregar o arquivo de verdade em vez de testar só o módulo puro:
// o bug do sprint não estava na aritmética do alinhamento — estava na COREOGRAFIA
// (reentrância do alarme, corrida do boot, quem escreve o estado). Testar só
// `phase_align.js` deixaria exatamente a parte que quebrou sem cobertura.

const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

const EXT_DIR = path.join(__dirname, '..', '..', 'extension');

function deepClone(v) {
  return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
}

function makeEvent() {
  const listeners = [];
  return {
    addListener: (fn) => listeners.push(fn),
    removeListener: (fn) => {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    },
    hasListener: (fn) => listeners.includes(fn),
    _listeners: listeners,
    async _emit(...args) {
      const out = [];
      for (const fn of listeners.slice()) out.push(await fn(...args));
      return out;
    }
  };
}

/**
 * @param {object} opts
 *   storage         estado inicial de chrome.storage.local
 *   storageDelayMs  atraso artificial do storage.local.get (simula o boot lento do SW)
 *   injectionDelayMs atraso do executeScript (permite sobrepor dois ticks)
 *   manifestVersion versão devolvida por chrome.runtime.getManifest()
 *   blockImports    lista de arquivos que devem falhar no importScripts
 */
function loadBackground(opts = {}) {
  const store = deepClone(opts.storage || {});
  const sessionStore = {};
  const sent = [];          // payloads passados ao WebSocket.send
  const alarms = new Map();
  const logs = [];
  let storageGetCount = 0;
  let storageSetCount = 0;

  const delay = (ms) => new Promise((r) => setTimeout(r, ms));
  const storageDelayMs = opts.storageDelayMs || 0;

  function localGet(keys, cb) {
    storageGetCount++;
    const run = () => {
      const out = {};
      const list = keys === null || keys === undefined
        ? Object.keys(store)
        : (Array.isArray(keys) ? keys : (typeof keys === 'string' ? [keys] : Object.keys(keys)));
      for (const k of list) if (k in store) out[k] = deepClone(store[k]);
      if (typeof cb === 'function') cb(out);
      return out;
    };
    if (typeof cb === 'function') {
      if (storageDelayMs) setTimeout(run, storageDelayMs);
      else run();
      return undefined;
    }
    return storageDelayMs ? delay(storageDelayMs).then(run) : Promise.resolve(run());
  }

  function localSet(items, cb) {
    storageSetCount++;
    for (const [k, v] of Object.entries(items)) store[k] = deepClone(v);
    if (typeof cb === 'function') { cb(); return undefined; }
    return Promise.resolve();
  }

  const onAlarm = makeEvent();
  const onMessage = makeEvent();
  const onInstalled = makeEvent();
  const onStartup = makeEvent();
  const onRemoved = makeEvent();

  // Cada teste declara o que cada injeção devolve (array ou função).
  const injections = { results: [], monitoring: [], session: [] };
  const injectionCalls = [];

  const chrome = {
    runtime: {
      lastError: null,
      getManifest: () => ({ version: opts.manifestVersion || '3.10.0' }),
      getURL: (p) => `chrome-extension://test/${p}`,
      sendMessage: () => Promise.resolve(),
      onMessage,
      onInstalled,
      onStartup,
      // Simula uma mensagem do popup/content chegando ao worker; resolve com a resposta
      // do handler (o `sendResponse` do MV3), para que o teste possa aguardá-la.
      __send: (message, sender = {}) => new Promise((resolve) => {
        const results = onMessage._listeners.map((fn) => fn(message, sender, resolve));
        if (!results.some((r) => r === true)) resolve(undefined);
      })
    },
    storage: {
      local: { get: localGet, set: localSet, remove: () => Promise.resolve() },
      session: {
        get: () => Promise.resolve({}),
        set: (i) => { Object.assign(sessionStore, i); return Promise.resolve(); }
      }
    },
    alarms: {
      create: (name, info) => alarms.set(name, info),
      clear: (name) => { alarms.delete(name); return Promise.resolve(true); },
      getAll: () => Promise.resolve([...alarms.entries()].map(([name, i]) => ({ name, ...i }))),
      onAlarm
    },
    tabs: {
      get: (id) => (opts.missingTab
        ? Promise.reject(new Error('No tab'))
        : Promise.resolve({ id, url: 'https://casino.example/game', title: 'Mesa' })),
      query: () => Promise.resolve([]),
      sendMessage: () => Promise.resolve(),
      captureVisibleTab: () => Promise.resolve('data:image/jpeg;base64,'),
      onRemoved
    },
    scripting: {
      executeScript: async (cfg) => {
        const fnName = cfg.func && cfg.func.name;
        let kind = 'results';
        if (fnName === 'extractMonitoringData') kind = 'monitoring';
        else if (fnName === 'extractSessionData') kind = 'session';
        injectionCalls.push(kind);
        if (opts.injectionDelayMs) await delay(opts.injectionDelayMs);
        const provider = injections[kind];
        const value = typeof provider === 'function'
          ? provider(injectionCalls.filter((k) => k === kind).length)
          : provider;
        return deepClone(value) || [];
      },
      insertCSS: () => Promise.resolve()
    },
    action: { setBadgeText: () => { }, setBadgeBackgroundColor: () => { } },
    webNavigation: {
      getAllFrames: () => Promise.resolve([]),
      onCompleted: makeEvent(),
      onHistoryStateUpdated: makeEvent()
    }
  };

  // WebSocket fake: registra tudo que sai e nunca abre sozinho (os testes controlam).
  const sockets = [];
  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      this.readyState = FakeWebSocket.CONNECTING;
      this.onopen = null; this.onmessage = null; this.onerror = null; this.onclose = null;
      sockets.push(this);
    }
    send(raw) { sent.push(JSON.parse(raw)); }
    close() { this.readyState = FakeWebSocket.CLOSED; }
    _open() { this.readyState = FakeWebSocket.OPEN; if (this.onopen) return this.onopen(); }
    _recv(obj) { if (this.onmessage) return this.onmessage({ data: JSON.stringify(obj) }); }
  }
  FakeWebSocket.CONNECTING = 0; FakeWebSocket.OPEN = 1;
  FakeWebSocket.CLOSING = 2; FakeWebSocket.CLOSED = 3;

  const sandbox = {
    chrome,
    WebSocket: FakeWebSocket,
    console: {
      log: (...a) => logs.push(['log', ...a]),
      warn: (...a) => logs.push(['warn', ...a]),
      error: (...a) => logs.push(['error', ...a])
    },
    setTimeout, clearTimeout, setInterval, clearInterval, setImmediate, queueMicrotask,
    Promise, Date, Math, JSON, Object, Array, String, Number, Boolean, Error, Map, Set,
    isNaN, isFinite, parseInt, parseFloat, encodeURIComponent, decodeURIComponent,
    URL, TextEncoder, TextDecoder,
    fetch: () => Promise.reject(new Error('offline')),
    crypto: { randomUUID: () => 'test-uuid-0000-0000-0000-000000000000', getRandomValues: (a) => a },
    btoa: (s) => Buffer.from(s, 'binary').toString('base64'),
    atob: (s) => Buffer.from(s, 'base64').toString('binary')
  };
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;

  const context = vm.createContext(sandbox);

  // `importScripts` do service worker: avalia o arquivo no MESMO contexto.
  const loaded = [];
  sandbox.importScripts = function (...files) {
    for (const f of files) {
      if (opts.blockImports && opts.blockImports.includes(f)) throw new Error(`blocked: ${f}`);
      const full = path.join(EXT_DIR, f);
      if (!fs.existsSync(full)) throw new Error(`importScripts: ${f} not found`);
      vm.runInContext(fs.readFileSync(full, 'utf8'), context, { filename: full });
      loaded.push(f);
    }
  };

  vm.runInContext(
    fs.readFileSync(path.join(EXT_DIR, 'background.js'), 'utf8'),
    context,
    { filename: 'background.js' }
  );

  return {
    context, sandbox, chrome, store, sent, sockets, logs, alarms, injections,
    injectionCalls, loaded,
    counts: () => ({ get: storageGetCount, set: storageSetCount }),
    get state() { return store.escutaState; },
    // Acesso a símbolos internos do worker (globals do script, não `globalThis`).
    evalIn: (expr) => vm.runInContext(expr, context),
    fireAlarm: (name) => onAlarm._emit({ name }),
    onMessage, onInstalled, onRemoved,
    flush: async (n = 8) => { for (let i = 0; i < n; i++) await new Promise((r) => setImmediate(r)); }
  };
}

// Molde de um resultado de `chrome.scripting.executeScript` para os números.
function frame(frameId, numbers) {
  return { frameId, result: { numbers, elementsFound: numbers.length } };
}

module.exports = { loadBackground, makeEvent, frame };
