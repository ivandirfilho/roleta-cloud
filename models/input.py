# Roleta Cloud - Modelos de Entrada (Pydantic)

from pydantic import BaseModel, Field, field_validator
from typing import Literal


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
    
    @field_validator('numero')
    @classmethod
    def validate_numero(cls, v: int) -> int:
        if not 0 <= v <= 36:
            raise ValueError('Número deve estar entre 0 e 36')
        return v
    
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
