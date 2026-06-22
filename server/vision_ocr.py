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

# Métricas Prometheus (foto_roleta) — observabilidade da cobertura foto->dados.
# No-op se prometheus_client ausente. Expostas em /metrics (registry default).
try:
    from prometheus_client import Counter as _PromCounter
    _vision_frames = _PromCounter(
        "vision_frames_total",
        "Frames de foto recebidos pelo handler, por resultado",
        ["result"],  # ok|busy|empty|error|disabled
    )
    _vision_persisted = _PromCounter(
        "vision_persisted_total",
        "Resultados de OCR persistidos em uma decision",
    )
except ImportError:
    class _NoOpMetric:
        def labels(self, *_a, **_k):
            return self

        def inc(self, *_a, **_k):
            pass
    _vision_frames = _NoOpMetric()
    _vision_persisted = _NoOpMetric()


def mark_frame(result: str) -> None:
    """Incrementa o contador de frames por resultado (ok/busy/empty/error/disabled)."""
    try:
        _vision_frames.labels(result=result).inc()
    except (ValueError, RuntimeError):
        pass


def mark_persisted() -> None:
    try:
        _vision_persisted.inc()
    except (ValueError, RuntimeError):
        pass


_OCR = None              # singleton RapidOCR
_OCR_TRIED = False       # ja tentamos importar/instanciar?
_IMPORT_OK = False

# Palavras-chave de modelos de roleta conhecidos (lower). Configuravel via env
# SDA_VISION_WHEEL_KEYWORDS="immersive,auto,lightning,...".
_DEFAULT_WHEEL_KEYWORDS = [
    "immersive", "auto", "lightning", "speed", "vip", "classic",
    "instant", "xxxtreme", "gold", "mega", "ruleta", "roulette", "roleta",
]

# Provider: marca/keyword que pode aparecer escrita na tela (logo/rodape) +
# inferencia pelo nome da mesa (wheel_model) -> provider. So da FOTO (sem DOM).
_PROVIDER_KEYWORDS = {
    "evolution": ["evolution", "evo gaming", "evo-games"],
    "pragmatic": ["pragmatic"],
    "playtech": ["playtech"],
    "ezugi": ["ezugi"],
    "imagine": ["imagine"],
}
# Inferencia: keyword no nome da mesa -> provider (quando a marca nao aparece).
_WHEEL_TO_PROVIDER = {
    "immersive": "evolution", "lightning": "evolution", "xxxtreme": "evolution",
    "auto-roulette": "evolution", "speed auto": "evolution", "instant": "evolution",
    "mega": "pragmatic", "powerup": "pragmatic", "auto mega": "pragmatic",
}


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
    # Downscale: OCR de tela cheia (1920px) no CPU QEMU leva ~8s. Reduzir a maior
    # dimensao a SDA_VISION_MAX_DIM (default 1500px) acelera ~2x e mantem legivel o
    # texto pequeno do nome do dealer (1100px perdia o dealer). O single-flight no
    # handler ja evita o empilhamento que causava travada, entao priorizamos leitura.
    try:
        max_dim = int(os.environ.get("SDA_VISION_MAX_DIM", "1500"))
    except (TypeError, ValueError):
        max_dim = 1500
    if max_dim > 0:
        w, h = pil.size
        big = max(w, h)
        if big > max_dim:
            scale = max_dim / float(big)
            pil = pil.resize((max(1, int(w * scale)), max(1, int(h * scale))))
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


# BUG-FIX 21/06 (auditoria pos-foto): identidade do PROPRIO produto/dashboard.
# O OCR as vezes pega a aba do dashboard ('Roleta Cloud' / 'roleta.xma-ia.com')
# em vez da mesa do cassino -> falso-positivo de wheel_model/dealer. Rejeitamos.
# BUG-6 22/06 (auditoria profunda pos-reload): o OCR tambem le SEM espaco
# ('Roletacloud') -> o match por substring com espaco falhava e vazava. Agora
# normalizamos (remove nao-alfanumerico) p/ pegar todas as variantes de grafia.
_SELF_TOKENS = ("roletacloud", "xmaia", "escutabeat")


def _is_self(text: Optional[str]) -> bool:
    """True se o texto e' a identidade do proprio app (nao uma mesa/dealer real).
    Normaliza removendo nao-alfanumerico p/ casar 'Roleta Cloud', 'Roletacloud',
    'roleta-cloud', 'xma-ia', 'xma ia' no mesmo token. BUG-6 (22/06)."""
    if not text:
        return False
    norm = re.sub(r"[^a-z0-9]", "", text.lower())
    return any(tok in norm for tok in _SELF_TOKENS)


def _parse_fields(texts: list[str]):
    """Heuristica leve: extrai dealer, wheel_model e provider das linhas do OCR.
    Tudo vem da FOTO (sem DOM). Retorna (dealer, wheel_model, provider)."""
    dealer = None
    wheel_model = None
    provider = None
    keywords = _wheel_keywords()
    full_low = " ".join(texts).lower()
    _DEALER_RE = re.compile(r"(?:dealer|crupi[eê]|croupier)\s*[:\-]?\s*(.*)", re.IGNORECASE)

    for i, t in enumerate(texts):
        low = t.lower()
        # dealer: 'dealer'/'crupie' + nome. O OCR pode quebrar em regioes
        # separadas ("Dealer" numa, "LEVI" na seguinte) — tratamos os dois casos.
        if not dealer:
            m = _DEALER_RE.search(t)
            if m:
                name = m.group(1).strip(" :-\t")
                if not name and i + 1 < len(texts):
                    name = texts[i + 1].strip(" :-\t")  # nome na proxima regiao
                # ignora se o "nome" for so um rotulo/numero
                if name and not name.isdigit() and len(name) >= 2:
                    dealer = name[:120]
        # wheel_model: linha que casa keyword de mesa conhecida
        if not wheel_model:
            for kw in keywords:
                if kw in low:
                    wheel_model = t.strip()
                    break

    # BUG-FIX 21/06: rejeita captura do PROPRIO dashboard (falso-positivo). Se o
    # OCR pegou a aba 'Roleta Cloud'/'xma-ia' em vez da mesa do cassino, descarta
    # antes de inferir provider (evita propagar o lixo para provider tambem).
    if _is_self(wheel_model):
        wheel_model = None
    if _is_self(dealer):
        dealer = None

    # provider DIRETO: marca aparece escrita na foto (logo/rodape)
    for prov, kws in _PROVIDER_KEYWORDS.items():
        if any(kw in full_low for kw in kws):
            provider = prov
            break
    # provider INFERIDO pelo nome da mesa (quando a marca nao aparece)
    if not provider and wheel_model:
        wl = wheel_model.lower()
        for kw, prov in _WHEEL_TO_PROVIDER.items():
            if kw in wl:
                provider = prov
                break

    return _norm_dealer(dealer), _norm_model(wheel_model), provider


def _norm_ws(s: str) -> str:
    """Colapsa espacos repetidos e remove bordas."""
    return re.sub(r"\s+", " ", s).strip()


def _norm_dealer(name: Optional[str]) -> Optional[str]:
    """Canonicaliza + VALIDA o nome do dealer. Agrupa variantes (Levi->LEVI) e
    REJEITA lixo de OCR (BUG 22/06: '/CROUPIEREEXPERIMENTE(E)' virava dealer e era
    propagado). Retorna None se implausível → o fill-forward mantém o último válido."""
    if not name:
        return name
    return _clean_dealer(name)


# Palavras que NUNCA fazem parte de um nome de dealer (rótulos/UI capturados junto).
_DEALER_LABEL_WORDS = (
    "CROUPIER", "CRUPIE", "DEALER", "EXPERIMENTE", "EXPERIMENT",
    "MESA", "TABLE", "ROLETA", "ROULETTE", "VIVO", "AOVIVO",
)


def _clean_dealer(name: Optional[str]) -> Optional[str]:
    """Valida plausibilidade de um nome de dealer (1-2 palavras só de letras,
    2-16 chars, sem rótulos de UI). Devolve em CAIXA ALTA, ou None se for lixo."""
    if not name:
        return None
    # troca tudo que não é letra (com acento) por espaço; colapsa
    core = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ ]", " ", str(name))
    core = re.sub(r"\s+", " ", core).strip()
    if not (2 <= len(core) <= 16):
        return None
    up = core.upper()
    if any(w in up for w in _DEALER_LABEL_WORDS):
        return None
    if len(core.split()) > 2:
        return None
    return up


# BUG-FIX 21/06 (auditoria pos-foto): defaults EMBUTIDOS p/ canonizar variantes de
# OCR mesmo SEM SDA_VISION_MODEL_ALIASES setado. Antes, sem o env, o fallback
# .title() era sensivel a espaco e fragmentava o mesmo rotulo em 3 ('Roleta Aovivo'
# /'Roleta Ao Vivo'/'Roletaaovivo'). Chave = label sem espacos/caixa. O env tem
# prioridade (override), entao operadores ainda customizam.
_DEFAULT_MODEL_ALIASES = {
    "roletaaovivo": "Roleta ao Vivo",
}


def _model_aliases() -> dict:
    """Mapa OCR-variante -> nome canonico: defaults embutidos + env
    SDA_VISION_MODEL_ALIASES ('roleta aovivo=Roleta ao Vivo,...'), env sobrepoe.
    Chave comparada sem espacos/caixa."""
    out = dict(_DEFAULT_MODEL_ALIASES)
    raw = os.environ.get("SDA_VISION_MODEL_ALIASES", "")
    for pair in raw.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            key = re.sub(r"[^a-z0-9]", "", k.strip().lower())
            if key:
                out[key] = v.strip()
    return out


def _norm_model(model: Optional[str]) -> Optional[str]:
    """Canonicaliza o modelo da roleta p/ agrupar variantes de OCR.
    1) colapsa espacos + Title Case; 2) aplica alias (chave sem espacos/caixa)
    p/ fundir 'Roleta ao Vivo' e 'Roleta aoVivo' no mesmo canonico."""
    if not model:
        return model
    cleaned = _norm_ws(model)
    if not cleaned:
        return None
    key = re.sub(r"[^a-z0-9]", "", cleaned.lower())
    aliases = _model_aliases()
    if key in aliases:
        return aliases[key]
    return cleaned.title()


def extract(image: "str | bytes", roi: Optional[dict] = None) -> dict:
    """Foto -> dados. Retorna dict serializavel:
    {ok, enabled, available, texts, full_text, dealer, wheel_model, provider, confidence, ms}.
    Nunca levanta por causa de OCR (degradacao graciosa)."""
    t0 = time.time()
    out = {
        "ok": False, "enabled": is_enabled(), "available": False,
        "texts": [], "full_text": "", "dealer": None, "wheel_model": None,
        "provider": None, "confidence": 0.0, "ms": 0,
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
        dealer, wheel_model, provider = _parse_fields(texts)
        out.update({
            "ok": True,
            "texts": texts,
            "full_text": " ".join(texts),
            "dealer": dealer,
            "wheel_model": wheel_model,
            "provider": provider,
            "confidence": round(sum(confs) / len(confs), 4) if confs else 0.0,
        })
    except Exception as e:  # noqa: BLE001
        logger.warning("[vision_ocr] falha no extract: %s", e)
        out["error"] = str(e)
    out["ms"] = int((time.time() - t0) * 1000)
    return out
