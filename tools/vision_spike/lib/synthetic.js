// SPR-V3 · vision_spike/lib/synthetic.js — gerador determinístico de cena de roda.
//
// ⚠️ FRONTEIRA DE EVIDÊNCIA — leia antes de usar qualquer número daqui ⚠️
// ----------------------------------------------------------------------
// Tudo que sai deste arquivo carrega `evidence_class: 'synthetic'` e
// `eligible_for_go_gates: false`. É teste do CÓDIGO, nunca prova do MUNDO:
//   • valida que o pipeline mede o que diz medir e que os guards disparam quando devem;
//   • NÃO valida que a mesa Evolution se parece com isto, nem a cobertura, nem a acurácia.
// Um estimador que acerta o próprio modelo que o gerou é "inverse crime", não evidência.
// Nenhum gate de GO do SPR-V3 pode ser preenchido com saída sintética.
//
// Casos adversariais embutidos (o gerador tem de conseguir DERRUBAR o estimador):
//   noGreen, staticOverlay, occlusion, lowLuma, noise, blur, mirror, sceneChange.
(function (root, factory) {
  'use strict';
  if (typeof module === 'object' && module && module.exports) module.exports = factory();
  else root.VSSynthetic = factory();
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var EVIDENCE_CLASS = 'synthetic';
  var POCKETS = 37;

  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  var DEFAULT_SCENE = {
    // A imagem precisa conter a SCENE_BAND (ρ até 1,45) inteira, senão o unwrap sai do
    // quadro e o guard `roi_out_of_bounds` dispara — que é o comportamento certo, mas
    // inútil como cenário-controle.
    width: 320,
    height: 260,
    center: { x: 160, y: 130 },
    a: 90,          // semi-eixo maior (px) da BORDA EXTERNA do rotor
    b: 60,          // semi-eixo menor — vista oblíqua
    phi: 0.15,      // leve rotação da elipse
    seed: 20260805
  };

  var COLORS = {
    felt: [12, 60, 32],
    stator: [150, 140, 120],
    statorDark: [90, 84, 72],
    hub: [60, 55, 50],
    red: [170, 30, 30],
    black: [25, 25, 25],
    green: [20, 140, 60],
    overlay: [235, 235, 245]
  };

  function defaultCalibration(scene) {
    scene = scene || DEFAULT_SCENE;
    return {
      version: 1,
      center: { x: scene.center.x, y: scene.center.y },
      a: scene.a,
      b: scene.b,
      phi: scene.phi,
      rotorBand: [0.55, 0.95],
      sceneBand: [1.15, 1.45],
      degPerBin: 0.5,
      mirrored: false
    };
  }

  /**
   * Renderiza UM frame da roda sintética.
   * @param {number} rotationDeg  rotação do PADRÃO. Crescente ⇒ perfil migra para θ maior
   *                              ⇒ "horário na tela" (mesma convenção de unwrap.js).
   */
  function renderWheelFrame(rotationDeg, opts) {
    opts = opts || {};
    var s = Object.assign({}, DEFAULT_SCENE, opts.scene || {});
    var rnd = mulberry32((opts.seed || s.seed) + Math.round(rotationDeg * 1000));
    var w = s.width, h = s.height;
    var data = new Uint8ClampedArray(w * h * 4);
    var cosP = Math.cos(s.phi), sinP = Math.sin(s.phi);
    var noise = opts.noise || 0;
    var lumaScale = opts.lowLuma ? 0.06 : 1;
    var mirror = opts.mirror === true;

    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var dx = x - s.center.x, dy = y - s.center.y;
        // volta ao referencial da elipse
        var ex = dx * cosP + dy * sinP;
        var ey = -dx * sinP + dy * cosP;
        var u = ex / s.a, v = ey / s.b;
        var rho = Math.hypot(u, v);
        var th = Math.atan2(v, u) * 180 / Math.PI;
        if (th < 0) th += 360;
        if (mirror) th = (360 - th) % 360;

        var col;
        if (rho > 1.5) col = COLORS.felt;
        else if (rho > 1.05) {
          // anel ESTÁTICO (estator/mesa) — é ele que sustenta o NCC de cena
          col = (Math.floor(th / 12) % 2 === 0) ? COLORS.stator : COLORS.statorDark;
        } else if (rho > 0.5) {
          var pat = th - rotationDeg;
          pat = ((pat % 360) + 360) % 360;
          var pocket = Math.floor(pat / (360 / POCKETS));
          if (pocket === 0 && !opts.noGreen) col = COLORS.green;
          else col = (pocket % 2 === 1) ? COLORS.red : COLORS.black;
        } else col = COLORS.hub;

        var i = (y * w + x) * 4;
        var n = noise ? (rnd() - 0.5) * 2 * noise : 0;
        data[i] = (col[0] + n) * lumaScale;
        data[i + 1] = (col[1] + n) * lumaScale;
        data[i + 2] = (col[2] + n) * lumaScale;
        data[i + 3] = 255;
      }
    }

    var frame = { width: w, height: h, data: data };

    // overlay ESTÁTICO (banner de UI) sobre a BORDA da ROI: o high-pass temporal tem de
    // matá-lo na correlação. Ele ocluí parte do rotor de propósito — quando o zero verde
    // passa por baixo, `zero_landmark_missing` dispara e o estimador ABSTÉM. Isso não é
    // defeito do teste: é o custo de cobertura que o V3-B vai medir em campo.
    if (opts.staticOverlay) {
      paintRect(frame, Math.round(s.center.x - s.a * 1.1), Math.round(s.center.y - s.b * 1.05),
        Math.round(s.a * 2.2), Math.round(s.b * 0.30), COLORS.overlay);
    }
    // OCLUSÃO estática sobre o ROTOR (mão do dealer parada / pop-up). NÃO toca o anel
    // estático de propósito: assim testa-se que o NCC de cena não é o guard que pega isto.
    if (opts.occlusion) {
      // Mantida DENTRO de ρ<1,1 (não encosta na SCENE_BAND que começa em 1,15): a oclusão
      // do rotor tem de ser pega por landmark/alias, não pelo NCC de cena.
      paintRect(frame, Math.round(s.center.x - s.a * 0.85), Math.round(s.center.y - s.b * 0.5),
        Math.round(s.a * 1.10), Math.round(s.b * 1.0), [8, 8, 8]);
    }
    // MUDANÇA DE CENA: cobre também o anel estático (janela movida, layout trocado,
    // banner novo). É ESTE caso que o NCC contra a calibração tem de pegar.
    if (opts.sceneOcclusion) {
      paintRect(frame, 0, 0, Math.round(s.center.x - s.a * 0.2), h, [200, 190, 175]);
    }
    if (opts.blur) boxBlur(frame, opts.blur | 0);
    return frame;
  }

  function paintRect(frame, x0, y0, rw, rh, col) {
    for (var y = y0; y < y0 + rh; y++) {
      if (y < 0 || y >= frame.height) continue;
      for (var x = x0; x < x0 + rw; x++) {
        if (x < 0 || x >= frame.width) continue;
        var i = (y * frame.width + x) * 4;
        frame.data[i] = col[0]; frame.data[i + 1] = col[1]; frame.data[i + 2] = col[2];
      }
    }
  }

  function boxBlur(frame, radius) {
    if (!(radius > 0)) return;
    var w = frame.width, h = frame.height;
    var src = frame.data.slice(0);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var acc = [0, 0, 0], c = 0;
        for (var dy = -radius; dy <= radius; dy++) {
          for (var dx = -radius; dx <= radius; dx++) {
            var xx = x + dx, yy = y + dy;
            if (xx < 0 || yy < 0 || xx >= w || yy >= h) continue;
            var j = (yy * w + xx) * 4;
            acc[0] += src[j]; acc[1] += src[j + 1]; acc[2] += src[j + 2]; c++;
          }
        }
        var i = (y * w + x) * 4;
        frame.data[i] = acc[0] / c; frame.data[i + 1] = acc[1] / c; frame.data[i + 2] = acc[2] / c;
      }
    }
  }

  /**
   * Sequência determinística de frames.
   * @param {Object} o `{direction:'cw'|'ccw'|'static', revPerS, fps, count, ...adversariais}`
   * @returns {{evidenceClass:string, eligibleForGoGates:false, frames:Array, calibration:Object}}
   */
  function makeSequence(o) {
    o = o || {};
    var direction = o.direction || 'cw';
    var revPerS = o.revPerS == null ? 0.35 : o.revPerS;
    var fps = o.fps || 10;
    var count = o.count || 8;
    var sign = direction === 'ccw' ? -1 : (direction === 'static' ? 0 : 1);
    var scene = Object.assign({}, DEFAULT_SCENE, o.scene || {});
    var frames = [];
    // Jitter determinístico de chegada de frame (fração do intervalo nominal). Um stream
    // real não entrega em grade perfeita, e a decimação tem de sobreviver a isso.
    var jitter = o.jitterFrac || 0;
    var jrnd = mulberry32((o.seed || scene.seed) ^ 0x5EED);
    var tPrev = -1;
    for (var i = 0; i < count; i++) {
      var tS = i / fps;
      if (jitter) {
        tS += (jrnd() - 0.5) * 2 * jitter / fps;
        if (tS <= tPrev) tS = tPrev + 1e-4;      // tempo nunca anda para trás
      }
      tPrev = tS;
      // A rotação é derivada do tempo REAL do frame: com jitter, a cena continua
      // fisicamente coerente com o timestamp que o estimador vai usar.
      var rot = sign * revPerS * 360 * tS;
      // Deriva de cena a partir de um índice (para testar o guard de NCC): usa
      // `sceneOcclusion`, que é o único que encosta na SCENE_BAND. `occlusion` cobre só o
      // rotor de propósito e produziria um falso negativo do guard de NCC.
      var sceneOpts = Object.assign({}, o);
      if (o.sceneChangeAt != null && i >= o.sceneChangeAt) sceneOpts.sceneOcclusion = true;
      frames.push({
        index: i,
        wallMs: Math.round(tS * 1000),
        mediaTimeS: tS,
        trueRotationDeg: rot,
        frame: renderWheelFrame(rot, Object.assign({ scene: scene }, sceneOpts))
      });
    }
    return {
      evidenceClass: EVIDENCE_CLASS,
      eligibleForGoGates: false,
      truth: { direction: direction, revPerS: revPerS, fps: fps },
      calibration: Object.assign(defaultCalibration(scene), { mirrored: o.mirror === true }),
      frames: frames
    };
  }

  return {
    EVIDENCE_CLASS: EVIDENCE_CLASS,
    POCKETS: POCKETS,
    DEFAULT_SCENE: DEFAULT_SCENE,
    COLORS: COLORS,
    defaultCalibration: defaultCalibration,
    renderWheelFrame: renderWheelFrame,
    makeSequence: makeSequence,
    _mulberry32: mulberry32
  };
}));
