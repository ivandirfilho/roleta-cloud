// SPR-V3 · vision_spike/probe/calibrate.js — calibração persistida com assinatura de cena.
//
// Entrega desta tela (DoD E1):
//   • ajuste de ELIPSE (centro + >=4 pontos da borda EXTERNA do rotor) — sem Hough;
//   • persistência da calibração COM thumbnail da cena;
//   • assinatura numérica do anel ESTÁTICO (fora do rotor) para invalidação automática
//     por NCC < 0,6.
// A thumbnail vai junto para o humano reconhecer a cena; quem invalida é o NCC, que é
// número. Não guardamos só a imagem: imagem não dispara guard.
'use strict';

const cv = document.getElementById('cv');
const ctx = cv.getContext('2d', { willReadFrequently: true });
const out = document.getElementById('out');
const stepEl = document.getElementById('step');

let snapshot = null;      // {width,height,dataUrl}
let img = null;
let center = null;
let points = [];
let fitted = null;

function log(html) { out.innerHTML = html; }

async function targetTabId() {
  // NÃO usar `tabs.query({active:true})`: esta página FOI aberta com `chrome.tabs.create`,
  // então ela própria é a aba ativa, e o snapshot seria pedido a uma página
  // `chrome-extension://` — onde content script nenhum é injetado. O popup guarda o id da
  // aba da mesa antes de abrir a calibração.
  const s = await chrome.storage.local.get('vsTargetTabId');
  return s.vsTargetTabId;
}

document.getElementById('snap').onclick = async () => {
  const tabId = await targetTabId();
  if (tabId == null) {
    return log('<span class="bad">aba da mesa desconhecida</span> — abra esta tela pelo ' +
      'popup da extensão <b>com a aba da mesa em primeiro plano</b>.');
  }
  chrome.tabs.sendMessage(tabId, { type: 'vs_collector', action: 'snapshot' }, (resp) => {
    if (chrome.runtime.lastError) return log('<span class="bad">' + chrome.runtime.lastError.message +
      '</span> — nenhum frame daquela aba tem <code>&lt;video&gt;</code>, ou as probes estão desarmadas.');
    if (!resp || !resp.ok) {
      return log('<span class="bad">snapshot falhou: ' + JSON.stringify(resp) + '</span>' +
        (resp && resp.tainted ? '<br>SecurityError = canvas manchado ⇒ o caminho de vídeo NÃO existe nesta mesa (resultado E0 válido e importante).' : ''));
    }
    snapshot = resp;
    img = new Image();
    img.onload = () => {
      cv.width = resp.width; cv.height = resp.height;
      redraw();
      stepEl.innerHTML = '2) Clique no <b>CENTRO</b> da roda. 3) Clique em <b>4 a 8 pontos</b> ' +
        'na BORDA EXTERNA do disco de bolsos (o rotor), um por quadrante.';
      log(`snapshot ${resp.width}×${resp.height} (coordenadas intrínsecas do vídeo)`);
    };
    img.src = resp.dataUrl;
  });
};

function redraw() {
  if (!img) return;
  ctx.drawImage(img, 0, 0);
  if (center) {
    ctx.strokeStyle = '#7fe0a0'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(center.x - 8, center.y); ctx.lineTo(center.x + 8, center.y);
    ctx.moveTo(center.x, center.y - 8); ctx.lineTo(center.x, center.y + 8); ctx.stroke();
  }
  ctx.fillStyle = '#8fb7ff';
  points.forEach(p => { ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, 6.283); ctx.fill(); });
  if (fitted && fitted.ok) {
    ctx.strokeStyle = '#ffd479'; ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i <= 180; i++) {
      const t = (i / 180) * Math.PI * 2;
      const ex = fitted.a * Math.cos(t), ey = fitted.b * Math.sin(t);
      const x = fitted.center.x + ex * Math.cos(fitted.phi) - ey * Math.sin(fitted.phi);
      const y = fitted.center.y + ex * Math.sin(fitted.phi) + ey * Math.cos(fitted.phi);
      i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.closePath(); ctx.stroke();
  }
}

cv.onclick = (e) => {
  if (!img) return;
  const r = cv.getBoundingClientRect();
  // O canvas é desenhado 1:1; ainda assim normalizamos pelo rect para o caso de zoom
  // do navegador. Sem isto a calibração muda quando o operador dá Ctrl+".
  const x = (e.clientX - r.left) * (cv.width / r.width);
  const y = (e.clientY - r.top) * (cv.height / r.height);
  if (!center) center = { x, y }; else points.push({ x, y });
  fitted = null;
  redraw();
  log(`centro: ${center ? `(${center.x.toFixed(1)}, ${center.y.toFixed(1)})` : '—'} · pontos: ${points.length}` +
    (points.length < VSEllipse.MIN_POINTS ? ` <span class="bad">(mínimo ${VSEllipse.MIN_POINTS})</span>` : ''));
};

document.getElementById('reset').onclick = () => {
  center = null; points = []; fitted = null;
  document.getElementById('save').disabled = true;
  redraw(); log('cliques zerados');
};

document.getElementById('fit').onclick = () => {
  if (!center) return log('<span class="bad">clique o centro primeiro</span>');
  fitted = VSEllipse.fitEllipseFixedCenter(center, points);
  redraw();
  if (!fitted.ok) {
    document.getElementById('save').disabled = true;
    return log(`<span class="bad">ajuste rejeitado: ${fitted.reason}</span>` +
      (fitted.reason === 'too_few_points' ? ` (tem ${fitted.have}, precisa ${fitted.need})` : ''));
  }
  const w = fitted.warnings;
  document.getElementById('save').disabled = false;
  log(
    `<span class="ok">elipse ajustada</span>\n` +
    `semi-eixos      : a=${fitted.a.toFixed(1)}  b=${fitted.b.toFixed(1)}  (razão ${fitted.axisRatio.toFixed(3)})\n` +
    `rotação φ       : ${(fitted.phi * 180 / Math.PI).toFixed(2)}°\n` +
    `resíduo RMS     : ${fitted.residualRms.toFixed(4)}   (limite ${VSEllipse.MAX_RESIDUAL_RMS})\n` +
    `condição        : ${fitted.condition.toFixed(1)}      (limite ${VSEllipse.MAX_CONDITION})\n` +
    `maior lacuna    : ${fitted.angularGapDeg.toFixed(1)}° (limite ${VSEllipse.MAX_ANGULAR_GAP_DEG}°)\n` +
    `pontos          : ${fitted.pointCount}\n` +
    (w.length ? `<span class="bad">avisos: ${w.join(', ')}</span>\n  → resíduo alto costuma ser CENTRO errado; recomece.` : 'sem avisos')
  );
};

document.getElementById('save').onclick = async () => {
  if (!fitted || !fitted.ok) return;
  const frame = { width: cv.width, height: cv.height, data: ctx.getImageData(0, 0, cv.width, cv.height).data };
  const calib = {
    version: 1,
    created_at: new Date().toISOString(),
    calibration_id: 'cal-' + Date.now().toString(36),
    center: fitted.center,
    a: fitted.a, b: fitted.b, phi: fitted.phi,
    rotorBand: VSUnwrap.ROTOR_BAND,
    sceneBand: VSUnwrap.SCENE_BAND,
    degPerBin: 360 / VSUnwrap.ANGLES,
    // Espelhamento do feed: o rótulo CW/CCW é "na tela"; a arbitragem física é a anotação
    // humana do V3-B. Marque aqui só se souber que o feed está espelhado.
    mirrored: false,
    video: { width: snapshot.width, height: snapshot.height },
    fit_quality: {
      residualRms: fitted.residualRms, condition: fitted.condition,
      angularGapDeg: fitted.angularGapDeg, pointCount: fitted.pointCount,
      warnings: fitted.warnings
    },
    edge_points: points,
    thumbnail: makeThumb()
  };
  const sig = VSUnwrap.sceneSignature(frame, calib);
  if (!sig.ok) return log('<span class="bad">assinatura de cena falhou: ' + sig.reason + '</span>');
  if (sig.invalidFrac > 0.02) {
    return log('<span class="bad">o anel estático (ρ 1,15-1,45) sai do quadro (' +
      (sig.invalidFrac * 100).toFixed(1) + '% inválido). Reenquadre a mesa ou recalibre com a roda menor no quadro.</span>');
  }
  calib.sceneSignature = Array.from(sig.signature);
  await chrome.storage.local.set({ vsCalibration: calib });
  log('<span class="ok">calibração salva</span> (' + calib.calibration_id +
    ') — assinatura de cena com ' + calib.sceneSignature.length + ' bins; invalidação automática por NCC < 0,6.');
};

function makeThumb() {
  const t = document.createElement('canvas');
  const s = Math.min(1, 240 / cv.width);
  t.width = Math.round(cv.width * s); t.height = Math.round(cv.height * s);
  t.getContext('2d').drawImage(cv, 0, 0, t.width, t.height);
  return t.toDataURL('image/jpeg', 0.6);
}
