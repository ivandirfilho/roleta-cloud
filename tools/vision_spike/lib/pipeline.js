// SPR-V3 · vision_spike/lib/pipeline.js — cola entre frames crus e o estimador.
//
// frames → unwrap elíptico (perfil cromático do rotor) + assinatura de cena (NCC)
//        → janelas deslizantes → `direction_core.analyzeWindow`
//        → sumário com DENOMINADORES EXPLÍCITOS.
//
// Percentual sem denominador não conta (regra dos gates do brief). Por isso `summarize`
// devolve numerador e denominador de cada taxa, e nunca uma taxa solta.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) {
    module.exports = factory(
      require('./unwrap.js'), require('./ellipse.js'), require('./direction_core.js'));
  } else {
    root.VSPipeline = factory(root.VSUnwrap, root.VSEllipse, root.VSDirection);
  }
}(typeof globalThis !== 'undefined' ? globalThis : this, function (Unwrap, Ellipse, Direction) {
  'use strict';

  var DEFAULT_WINDOW = 6;   // 6 frames + stride 3 = 3 pares

  /**
   * Converte frames crus em perfis prontos para o estimador.
   *
   * A assinatura de cena de REFERÊNCIA deve vir da CALIBRAÇÃO (thumbnail salva pelo
   * operador). Quando ela falta há dois comportamentos, e a diferença importa:
   *
   *  • `failClosedScene: true` (o COLETOR usa isto) — nenhuma referência é inventada:
   *    `ncc` vira `NaN`, o guard `scene_ncc_low` dispara e o veredito é abstenção. Sem
   *    isso o coletor rodaria com o anti-cena **desligado em silêncio** e emitiria
   *    vereditos que *parecem* totalmente guardados.
   *  • `false` (o REPLAY usa isto) — cai no primeiro frame para permitir iterar offline,
   *    e marca `sceneRefSource: 'first_frame'`. Cada janela carrega `sceneReference`,
   *    então nenhum resultado sai por aí sem dizer contra o que a cena foi comparada.
   */
  function buildProfiles(frames, calibration, options) {
    options = options || {};
    var hasCalibScene = !!(calibration && calibration.sceneSignature);
    var failClosed = options.failClosedScene === true;
    var sceneRef = hasCalibScene ? Float64Array.from(calibration.sceneSignature) : null;
    var sceneRefSource = hasCalibScene
      ? 'calibration'
      : (failClosed ? 'missing_calibration' : 'first_frame');
    var profiles = [];
    var warnings = [];

    for (var i = 0; i < frames.length; i++) {
      var item = frames[i];
      var raw = item.frame || item;
      var un = Unwrap.unwrapRotor(raw, calibration, options.unwrap);
      var sc = Unwrap.sceneSignature(raw, calibration, options.scene);
      if (!un.ok || !sc.ok) {
        profiles.push({
          index: item.index != null ? item.index : i,
          tMs: item.wallMs, mediaTimeS: item.mediaTimeS,
          chroma: new Float64Array(0), meanLuma: NaN, invalidFrac: 1, ncc: NaN,
          sceneRefSource: sceneRefSource,
          error: (un.reason || sc.reason)
        });
        continue;
      }
      if (!sceneRef && !failClosed) sceneRef = Float64Array.from(sc.signature);
      profiles.push({
        index: item.index != null ? item.index : i,
        tMs: item.wallMs,
        mediaTimeS: item.mediaTimeS,
        chroma: un.chroma,
        luma: un.luma,
        meanLuma: un.meanLuma,
        invalidFrac: Math.max(un.invalidFrac, sc.invalidFrac),
        // Sem referência de calibração em modo fail-closed, `ncc` é NaN = "não sei" —
        // e "não sei" é guard, nunca aprovação.
        ncc: sceneRef ? Ellipse.ncc(sceneRef, sc.signature) : NaN,
        sceneRefSource: sceneRefSource,
        sceneSignature: sc.signature
      });
    }
    if (sceneRefSource === 'first_frame') {
      warnings.push('scene_reference_from_first_frame_not_calibration');
    } else if (sceneRefSource === 'missing_calibration') {
      warnings.push('scene_reference_missing_calibration_fail_closed');
    }
    return { profiles: profiles, sceneRefSource: sceneRefSource, warnings: warnings };
  }

  /** Janelas deslizantes de 1 frame de passo. Cada frame a partir do índice W−1 FECHA uma janela. */
  function runSlidingWindows(profiles, calibration, options) {
    options = options || {};
    var W = options.windowSize || DEFAULT_WINDOW;
    var out = [];
    for (var end = W - 1; end < profiles.length; end++) {
      var win = profiles.slice(end - W + 1, end + 1);
      var r = Direction.analyzeWindow(win, calibration, options.direction);
      out.push({
        closingFrameIndex: profiles[end].index,
        startFrameIndex: profiles[end - W + 1].index,
        direction: r.direction,
        emitted: r.emitted,
        confidence: r.confidence,
        guards: r.guards,
        // Nenhum veredito sai sem dizer contra O QUE a cena foi comparada. Um resultado
        // com `first_frame` ou `missing_calibration` NÃO está totalmente guardado.
        sceneReference: (win[0] && win[0].sceneRefSource) || 'unknown',
        degreesPerSecond: r.degreesPerSecond,
        aliasMargin: r.aliasMargin,
        evidence: r.evidence
      });
    }
    return out;
  }

  /**
   * Sumário com numerador E denominador de cada taxa.
   *
   * DEFINIÇÕES CONGELADAS (citadas em RESULTADO.md — mudar aqui é mudar o gate):
   *  • `frames_processed`  = perfis que entraram no pipeline (inclui o aquecimento).
   *  • `warmup_frames`     = W−1 primeiros: nunca fecham janela ⇒ nunca entram no numerador.
   *  • `windows_evaluated` = frames_processed − W + 1.
   *  • `sinal` = (janelas que EMITIRAM e acertaram) / frames_processed.
   *              Denominador propositalmente inclui o aquecimento: assim o gate não pode
   *              ser satisfeito com captura curta. Teto = (n−W+1)/n ⇒ para ≥98% é preciso
   *              n ≥ 250 frames com W=6. Captura curta ⇒ gate INVÁLIDO, não "quase lá".
   *  • `acuracia_replay` = acertos / EMITIDOS (denominador diferente — reportado à parte).
   *  • `abstencao` = janelas sem emissão / windows_evaluated.
   */
  function summarize(windows, truthDirection, framesProcessed, windowSize) {
    var W = windowSize || DEFAULT_WINDOW;
    var emitted = 0, correct = 0, wrong = 0, abstained = 0;
    var guardHist = {};
    for (var i = 0; i < windows.length; i++) {
      var w = windows[i];
      if (w.emitted) {
        emitted++;
        if (truthDirection && w.direction === truthDirection) correct++;
        else if (truthDirection) wrong++;
      } else {
        abstained++;
      }
      for (var g = 0; g < w.guards.length; g++) {
        guardHist[w.guards[g]] = (guardHist[w.guards[g]] || 0) + 1;
      }
    }
    var n = framesProcessed;
    return {
      frames_processed: n,
      warmup_frames: Math.min(W - 1, n),
      windows_evaluated: windows.length,
      emitted: emitted,
      abstained: abstained,
      correct: truthDirection ? correct : null,
      wrong: truthDirection ? wrong : null,
      sinal: truthDirection && n > 0
        ? { numerador: correct, denominador: n, valor: correct / n }
        : null,
      sinal_teto_da_captura: n > 0 ? { numerador: Math.max(0, n - W + 1), denominador: n, valor: Math.max(0, n - W + 1) / n } : null,
      acuracia_replay: truthDirection && emitted > 0
        ? { numerador: correct, denominador: emitted, valor: correct / emitted }
        : null,
      abstencao: windows.length > 0
        ? { numerador: abstained, denominador: windows.length, valor: abstained / windows.length }
        : null,
      guards: guardHist
    };
  }

  function run(frames, calibration, options) {
    options = options || {};
    var now = (typeof performance !== 'undefined' && performance.now)
      ? function () { return performance.now(); }
      : function () { return Date.now(); };

    // Custo separado de propósito: o unwrap roda POR FRAME (é ele que tem de caber no
    // orçamento de 1-3 ms do renderer); a correlação roda POR MEDIÇÃO (uma por giro no
    // sensor real, mesmo que o replay deslize janela a janela).
    var t0 = now();
    var built = buildProfiles(frames, calibration, options);
    var t1 = now();
    var windows = runSlidingWindows(built.profiles, calibration, options);
    var t2 = now();

    return {
      profiles: built.profiles.length,
      sceneRefSource: built.sceneRefSource,
      warnings: built.warnings,
      windows: windows,
      cost: {
        unwrapMsPerFrame: built.profiles.length ? (t1 - t0) / built.profiles.length : null,
        analyzeMsPerWindow: windows.length ? (t2 - t1) / windows.length : null,
        totalMs: t2 - t0
      },
      summary: summarize(windows, options.truthDirection || null,
        built.profiles.length, options.windowSize || DEFAULT_WINDOW)
    };
  }

  return {
    DEFAULT_WINDOW: DEFAULT_WINDOW,
    buildProfiles: buildProfiles,
    runSlidingWindows: runSlidingWindows,
    summarize: summarize,
    run: run
  };
}));
