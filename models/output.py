# Roleta Cloud - Modelos de Saída (Pydantic)

from pydantic import BaseModel, Field
from typing import List, Literal


class SuggestionOutput(BaseModel):
    """
    Sugestão enviada para o overlay na extensão.
    """
    trace_id: str = Field(description="ID de rastreamento (mesmo do input)")
    acao: Literal["APOSTAR", "PULAR", "AGUARDAR"] = Field(description="Ação recomendada")
    numeros: List[int] = Field(default_factory=list, description="Números para apostar")
    centro: int = Field(default=0, description="Número central da aposta")
    regiao_visual: str = Field(default="", description="Representação visual ex: '4, [2], 17'")
    estrategia: str = Field(default="", description="Nome da estratégia usada")
    score: int = Field(default=0, ge=0, le=6, description="Score de confiança 0-6")
    t_server: int = Field(description="Timestamp do servidor em ms")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "trace_id": "abc12345",
                    "acao": "APOSTAR",
                    "numeros": [4, 21, 2, 25, 17],
                    "centro": 2,
                    "regiao_visual": "4, 21, [2], 25, 17",
                    "estrategia": "SDA-11",
                    "score": 4,
                    "t_server": 1705571100050
                }
            ]
        }
    }


class AckOutput(BaseModel):
    """ACK de recebimento de mensagem."""
    type: Literal["ack"] = "ack"
    trace_id: str
    t_server: int


class ErrorOutput(BaseModel):
    """Mensagem de erro."""
    type: Literal["error"] = "error"
    trace_id: str
    code: int
    message: str
    t_server: int
