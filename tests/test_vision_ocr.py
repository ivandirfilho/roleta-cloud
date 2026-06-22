"""Tests Vision OCR (foto_roleta_junho.md): foto -> dados, de verdade.

Gera uma imagem com texto conhecido (PIL) e prova que server/vision_ocr.py
extrai o texto via RapidOCR (PaddleOCR-ONNX). Skip gracioso se a lib não estiver
instalada (ex.: ambiente sem rapidocr) — em produção o Dockerfile a instala.
"""
import base64
import io
import os

import pytest

from server import vision_ocr


def _img_with_text(text: str, size=(440, 90)) -> bytes:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", size, (15, 15, 20))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 34)
    except Exception:
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 34)
        except Exception:
            font = ImageFont.load_default()
    d.text((12, 26), text, fill=(240, 240, 240), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


ocr_required = pytest.mark.skipif(
    not vision_ocr.is_available(),
    reason="rapidocr-onnxruntime não instalado (instalado no container de produção)",
)


def test_module_api_exists():
    for name in ("extract", "is_available", "is_enabled", "mark_frame", "mark_persisted"):
        assert hasattr(vision_ocr, name)


def test_metrics_increment_does_not_raise():
    """mark_frame/mark_persisted nunca levantam (no-op se prometheus ausente)."""
    vision_ocr.mark_frame("ok")
    vision_ocr.mark_frame("busy")
    vision_ocr.mark_persisted()


def test_disabled_flag_returns_gracefully(monkeypatch):
    """SDA_VISION_OCR=0 → extract não processa, retorna enabled=False sem quebrar."""
    monkeypatch.setenv("SDA_VISION_OCR", "0")
    out = vision_ocr.extract(_img_with_text("Dealer Maria"))
    assert out["ok"] is False
    assert out["enabled"] is False


def test_invalid_image_does_not_raise(monkeypatch):
    """Entrada inválida nunca derruba o server (degradação graciosa)."""
    monkeypatch.setenv("SDA_VISION_OCR", "1")
    out = vision_ocr.extract("não é base64 válido @@@")
    assert out["ok"] is False  # erro tratado, sem exceção


@ocr_required
def test_extract_reads_dealer_name(monkeypatch):
    """PROVA foto->dados: imagem 'Dealer Maria' → OCR extrai o texto e o dealer."""
    monkeypatch.setenv("SDA_VISION_OCR", "1")
    png = _img_with_text("Dealer Maria")
    out = vision_ocr.extract(png)
    assert out["ok"] is True
    full = out["full_text"].lower()
    assert "maria" in full
    assert out["dealer"] is not None and "maria" in out["dealer"].lower()
    assert out["confidence"] > 0.3


@ocr_required
def test_extract_accepts_base64_with_prefix(monkeypatch):
    """Aceita data:image/png;base64,... (formato do captureVisibleTab)."""
    monkeypatch.setenv("SDA_VISION_OCR", "1")
    png = _img_with_text("Lightning Roulette")
    b64 = "data:image/png;base64," + base64.b64encode(png).decode()
    out = vision_ocr.extract(b64)
    assert out["ok"] is True
    assert "lightning" in out["full_text"].lower()
    # wheel_model casa keyword conhecida ('lightning'/'roulette')
    assert out["wheel_model"] is not None
    # provider INFERIDO pelo nome da mesa (lightning -> evolution)
    assert out["provider"] == "evolution"


@ocr_required
def test_extract_provider_direct_brand(monkeypatch):
    """Provider DIRETO via OCR: a marca em CAIXA ALTA aparece na foto."""
    monkeypatch.setenv("SDA_VISION_OCR", "1")
    out = vision_ocr.extract(_img_with_text("PRAGMATIC"))
    assert out["ok"] is True
    assert out["provider"] == "pragmatic"


def test_parse_fields_extracts_all_three():
    """Lógica de parsing (independente do OCR): dealer + wheel_model + provider da foto."""
    dealer, wheel, provider = vision_ocr._parse_fields(["Dealer Maria", "Pragmatic Play", "Mega Roulette"])
    assert dealer is not None and "maria" in dealer.lower()
    assert wheel is not None and "roulette" in wheel.lower()
    assert provider == "pragmatic"  # marca direta


def test_parse_fields_dealer_in_separate_region():
    """OCR quebra 'Dealer' e o nome em regiões separadas → ainda extrai o dealer."""
    dealer, _w, _p = vision_ocr._parse_fields(["Dealer", "LEVI", "Roleta ao Vivo"])
    assert dealer == "LEVI"
    # rótulo seguido de número não vira dealer
    dealer2, _w2, _p2 = vision_ocr._parse_fields(["Dealer", "12345"])
    assert dealer2 is None


def test_dealer_normalized_uppercase():
    """Dealer canonicalizado em CAIXA ALTA (Levi/levi/LEVI agrupam)."""
    d1, _, _ = vision_ocr._parse_fields(["Dealer Levi"])
    d2, _, _ = vision_ocr._parse_fields(["Dealer  levi "])
    assert d1 == "LEVI" and d2 == "LEVI"


def test_model_normalized_title_case_and_whitespace():
    """Modelo desconhecido: espaços colapsados + Title Case (variantes de espaço agrupam)."""
    _d, w1, _ = vision_ocr._parse_fields(["Speed  Auto   Roulette"])
    assert w1 == "Speed Auto Roulette"


def test_model_alias_merges_ocr_variants(monkeypatch):
    """Alias funde 'Roleta aoVivo' e 'Roleta ao Vivo' no mesmo canônico."""
    monkeypatch.setenv("SDA_VISION_MODEL_ALIASES", "roletaaovivo=Roleta ao Vivo")
    _d1, w1, _ = vision_ocr._parse_fields(["Roleta aoVivo"])
    _d2, w2, _ = vision_ocr._parse_fields(["Roleta ao Vivo"])
    assert w1 == "Roleta ao Vivo" and w2 == "Roleta ao Vivo"


def test_model_merges_variants_without_env(monkeypatch):
    """BUG-FIX 21/06: default embutido funde as variantes do label conhecido MESMO
    sem SDA_VISION_MODEL_ALIASES (antes fragmentava em 3: 'Roleta Aovivo' etc.)."""
    monkeypatch.delenv("SDA_VISION_MODEL_ALIASES", raising=False)
    outs = {
        vision_ocr._parse_fields([v])[1]
        for v in ("Roleta aoVivo", "Roleta ao Vivo", "RoletaaoVivo", "ROLETA AOVIVO")
    }
    assert outs == {"Roleta ao Vivo"}


def test_parse_fields_rejects_self_dashboard():
    """BUG-FIX 21/06: OCR da PRÓPRIA aba do dashboard ('Roleta Cloud'/'xma-ia') não
    vira mesa nem dealer (falso-positivo) — mas dealers reais na mesma foto ficam."""
    _d, wheel, _p = vision_ocr._parse_fields(["Roleta Cloud", "Dealer LEVI"])
    assert wheel is None and _d == "LEVI"
    # dealer == identidade própria também é rejeitado
    dealer2, _w2, _p2 = vision_ocr._parse_fields(["Dealer Roleta Cloud"])
    assert dealer2 is None
    # BUG-6 (22/06): variantes SEM espaço / com hífen que escapavam do match antigo
    for variant in ("Roletacloud", "roleta-cloud", "ROLETACLOUD", "xma-ia"):
        assert vision_ocr._is_self(variant) is True, variant
    # roleta REAL não é falso-positivo
    assert vision_ocr._is_self("Roleta ao Vivo") is False
    assert vision_ocr._is_self("Lightning Roulette") is False


def test_parse_fields_infers_provider_from_wheel():
    """Provider INFERIDO pelo nome da mesa quando a marca não aparece."""
    _dealer, wheel, provider = vision_ocr._parse_fields(["Immersive Roulette", "Dealer Joao"])
    assert provider == "evolution"  # immersive -> evolution
    assert wheel is not None


@ocr_required
def test_roi_crop_runs(monkeypatch):
    """ROI fracionária recorta sem quebrar e ainda extrai."""
    monkeypatch.setenv("SDA_VISION_OCR", "1")
    png = _img_with_text("Dealer Joao")
    out = vision_ocr.extract(png, roi={"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0})
    assert out["ok"] is True
