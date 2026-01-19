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
