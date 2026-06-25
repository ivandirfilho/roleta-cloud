# Roleta Cloud - Modelos de Entrada (Pydantic)

from pydantic import BaseModel, Field, field_validator
from typing import Literal


# BUG-FIX 21/06 (auditoria pos-foto): a extensao (deal_capture.js) usa fallback
# `host:<dominio>` quando nao reconhece a marca do provider. Frames de analytics
# (googletagmanager/doubleclick/youtube) vazavam como 'provider' e poluiam o
# agrupamento. Mapa marca<-keyword de dominio: recupera a marca real
# (ex.: evo-games -> evolution) e descarta o resto.
_PROVIDER_BRAND_KEYWORDS: dict[str, tuple[str, ...]] = {
    "evolution": ("evolution", "evo-games", "evogames", "evo gaming"),
    "pragmatic": ("pragmatic",),
    "playtech": ("playtech",),
    "ezugi": ("ezugi",),
    "imagine": ("imagine",),
}


class SpinInput(BaseModel):
    """
    Dados que chegam da extensão Escuta Beat.
    Pydantic valida automaticamente.
    """
    numero: int = Field(ge=0, le=36, description="Número sorteado (0-36)")
    direcao: Literal["horario", "anti-horario"] = Field(description="Direção do giro")
    trace_id: str = Field(min_length=4, max_length=36, description="ID de rastreamento")
    t_client: int = Field(description="Timestamp do cliente em ms")
    # SP-12 DEAL-02 (27/05): metadata opcional capturado pelo extension (DOM).
    # Backwards-compatible: payloads antigos sem esses campos seguem validos.
    dealer: str | None = Field(default=None, max_length=120, description="Nome do dealer (DOM)")
    table: str | None = Field(default=None, max_length=80, description="Identificador da mesa")
    provider: str | None = Field(default=None, max_length=40, description="Provider: evolution|playtech|imagine|...")
    round_id: str | None = Field(default=None, max_length=80, description="ID do round (deduplicacao)")
    # Vision (foto_roleta_junho.md Parte 4): metadata opcional vindo do motor de visao
    # (foto->dados). Fundido DOM-first na extensao. Backwards-compatible: payloads
    # sem esses campos seguem validos. wheel_model = modelo fisico da roleta.
    wheel_model: str | None = Field(default=None, max_length=80, description="Modelo da roleta (visao)")
    vision_confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confianca do motor de visao (0..1)")
    vision_source: str | None = Field(default=None, max_length=20, description="Origem do dado: vision|dom|fused")
    # DIR3 (sentido-fase): sinais opcionais de direção/sequência (aditivo, backward-compat).
    direction_source: str | None = Field(default=None, max_length=24, description="Origem do sentido: operator_seed|deterministic_toggle|vision|dom_hint|manual_fix")
    # DIR15 (25/06): RESERVADO — cliente ainda nao envia client_spin_seq. Aceito por
    # backward-compat e como ponto de extensao para DIR21+ (cliente pode passar a
    # enviar contador local para cross-validacao com spin_seq do servidor).
    client_spin_seq: int | None = Field(default=None, description="RESERVADO (DIR21+): Sequência de fase prevista pelo cliente")
    direction_confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Confiança da fonte de direção (0..1)")
    
    @field_validator('numero')
    @classmethod
    def validate_numero(cls, v: int) -> int:
        if not 0 <= v <= 36:
            raise ValueError('Número deve estar entre 0 e 36')
        return v

    @field_validator('provider')
    @classmethod
    def sanitize_provider(cls, v: str | None) -> str | None:
        """BUG-FIX 21/06 (auditoria pos-foto): higieniza o provider.

        A extensao envia `host:<dominio>` como fallback quando nao reconhece a
        marca; frames de analytics (doubleclick/googletagmanager/youtube) vazavam
        como provider e poluiam o agrupamento. Recupera a marca pelo dominio
        quando possivel (evo-games -> evolution); senao descarta (None) para nao
        contaminar perfis por provider. Marcas limpas passam intactas.
        """
        if not v:
            return v
        s = v.strip()
        if not s.lower().startswith("host:"):
            return s
        host = s.lower()[len("host:"):]
        for brand, kws in _PROVIDER_BRAND_KEYWORDS.items():
            if any(kw in host for kw in kws):
                return brand
        return None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "numero": 17,
                    "direcao": "horario",
                    "trace_id": "abc12345",
                    "t_client": 1705571100000
                }
            ]
        }
    }
