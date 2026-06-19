"""Vision OCR (foto_roleta_junho.md): foto -> dados.

Motor de visao server-side que recebe um frame (capturado pela extensao via
chrome.tabs.captureVisibleTab) e extrai texto/parametros (dealer, modelo da
roleta) via OCR. Usa rapidocr-onnxruntime (PaddleOCR-ONNX, CPU, self-contained
— alinhado a foto_roleta_junho.md Parte 2).

Design:
  - Singleton lazy do RapidOCR (init ~0.4s, custo unico).
  - Degradacao graciosa: se a lib nao estiver instalada, is_available()=False e
    extract() devolve {ok:False} sem quebrar (server nunca cai por causa de OCR).
  - Flag SDA_VISION_OCR (env, default '1'): quando '0', extract() devolve disabled.
  - Sem efeito no caminho de aposta: este modulo so e chamado pelo handler
    foto_frame, que so recebe frame se a extensao optar por enviar.
"""
from __future__ import annotations

import base64
import io
import os
import re
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_OCR = None              # singleton RapidOCR
_OCR_TRIED = False       # ja tentamos importar/instanciar?
_IMPORT_OK = False

# Palavras-chave de modelos de roleta conhecidos (lower). Configuravel via env
# SDA_VISION_WHEEL_KEYWORDS="immersive,auto,lightning,...".
_DEFAULT_WHEEL_KEYWORDS = [
    "immersive", "auto", "lightning", "speed", "vip", "classic",
    "instant", "xxxtreme", "gold", "ruleta", "roulette",
]


def is_enabled() -> bool:
    return os.environ.get("SDA_VISION_OCR", "1") not in ("0", "false", "False", "")


def _wheel_keywords() -> list[str]:
    raw = os.environ.get("SDA_VISION_WHEEL_KEYWORDS", "")
    if raw.strip():
        return [k.strip().lower() for k in raw.split(",") if k.strip()]
    return _DEFAULT_WHEEL_KEYWORDS


def _get_ocr():
    """Instancia (lazy) o RapidOCR uma unica vez. None se indisponivel."""
    global _OCR, _OCR_TRIED, _IMPORT_OK
    if _OCR_TRIED:
        return _OCR
    _OCR_TRIED = True
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
        _OCR = RapidOCR()
        _IMPORT_OK = True
        logger.info("[vision_ocr] RapidOCR inicializado")
    except Exception as e:  # noqa: BLE001
        _OCR = None
        _IMPORT_OK = False
        logger.warning("[vision_ocr] RapidOCR indisponivel (%s); OCR desabilitado", e)
    return _OCR


def is_available() -> bool:
    """True se o motor de OCR pode rodar (lib instalada e instanciavel)."""
    _get_ocr()
    return _IMPORT_OK


def _decode_image(image: "str | bytes"):
    """Aceita base64 (com ou sem prefixo data:) ou bytes -> numpy array RGB."""
    import numpy as np  # local: numpy vem com onnxruntime/opencv
    from PIL import Image

    if isinstance(image, str):
        # remove prefixo data:image/...;base64,
        if "," in image and image.strip().lower().startswith("data:"):
            image = image.split(",", 1)[1]
        raw = base64.b64decode(image)
    elif isinstance(image, (bytes, bytearray)):
        raw = bytes(image)
    else:
        raise TypeError("image deve ser base64 str ou bytes")

    pil = Image.open(io.BytesIO(raw)).convert("RGB")
    return np.array(pil)


def _crop(arr, roi: Optional[dict]):
    """ROI opcional {x,y,w,h} em fracao 0..1 ou pixels."""
    if not roi:
        return arr
    h, w = arr.shape[:2]

    def _px(v, total):
        v = float(v)
        return int(v * total) if 0.0 <= v <= 1.0 else int(v)

    x = max(0, _px(roi.get("x", 0), w))
    y = max(0, _px(roi.get("y", 0), h))
    cw = _px(roi.get("w", 1.0), w)
    ch = _px(roi.get("h", 1.0), h)
    x2 = min(w, x + cw)
    y2 = min(h, y + ch)
    if x2 <= x or y2 <= y:
        return arr
    return arr[y:y2, x:x2]


def _parse_fields(texts: list[str]):
    """Heuristica leve: extrai dealer e wheel_model das linhas reconhecidas."""
    dealer = None
    wheel_model = None
    keywords = _wheel_keywords()

    for t in texts:
        low = t.lower()
        # dealer: linha que contem 'dealer'/'crupie' -> pega o resto
        m = re.search(r"(?:dealer|crupi[eê]|croupier)\s*[:\-]?\s*(.+)", low)
        if m and not dealer:
            name = m.group(1).strip()
            # recupera capitalizacao do texto original
            idx = low.find(name)
            dealer = t[idx:idx + len(name)].strip() if idx >= 0 else name.title()
        # wheel_model: linha que casa keyword conhecida
        if not wheel_model:
            for kw in keywords:
                if kw in low:
                    wheel_model = t.strip()
                    break
    return dealer, wheel_model


def extract(image: "str | bytes", roi: Optional[dict] = None) -> dict:
    """Foto -> dados. Retorna dict serializavel:
    {ok, enabled, available, texts, full_text, dealer, wheel_model, confidence, ms}.
    Nunca levanta por causa de OCR (degradacao graciosa)."""
    t0 = time.time()
    out = {
        "ok": False, "enabled": is_enabled(), "available": False,
        "texts": [], "full_text": "", "dealer": None, "wheel_model": None,
        "confidence": 0.0, "ms": 0,
    }
    if not is_enabled():
        out["ms"] = int((time.time() - t0) * 1000)
        return out

    ocr = _get_ocr()
    out["available"] = _IMPORT_OK
    if ocr is None:
        out["ms"] = int((time.time() - t0) * 1000)
        return out

    try:
        arr = _decode_image(image)
        arr = _crop(arr, roi)
        result, _elapse = ocr(arr)
        texts, confs = [], []
        for row in (result or []):
            # row = [box, text, conf]
            if len(row) >= 3 and row[1]:
                texts.append(str(row[1]).strip())
                try:
                    confs.append(float(row[2]))
                except (TypeError, ValueError):
                    pass
        dealer, wheel_model = _parse_fields(texts)
        out.update({
            "ok": True,
            "texts": texts,
            "full_text": " ".join(texts),
            "dealer": dealer,
            "wheel_model": wheel_model,
            "confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("[vision_ocr] falha no extract: %s", e)
        out["error"] = str(e)
    out["ms"] = int((time.time() - t0) * 1000)
    return out
