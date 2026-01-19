# Roleta Cloud - Tracing Context

import time
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional


def now_ms() -> int:
    """Retorna timestamp atual em milissegundos."""
    return int(time.time() * 1000)


@dataclass
class TraceStep:
    """Um passo no trace."""
    name: str
    t: int = field(default_factory=now_ms)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceContext:
    """
    Contexto de rastreamento para uma operação.
    Registra cada passo com timestamp.
    """
    trace_id: str
    t_start: int = field(default_factory=now_ms)
    steps: List[TraceStep] = field(default_factory=list)
    
    def step(self, name: str, data: Optional[Dict[str, Any]] = None) -> None:
        """Registra um passo no trace."""
        self.steps.append(TraceStep(
            name=name,
            t=now_ms(),
            data=data or {}
        ))
    
    def finish(self) -> Dict[str, Any]:
        """Finaliza e retorna o trace completo."""
        t_end = now_ms()
        return {
            "trace_id": self.trace_id,
            "t_start": self.t_start,
            "t_end": t_end,
            "duration_ms": t_end - self.t_start,
            "steps": [asdict(s) for s in self.steps]
        }
    
    def to_log_line(self) -> str:
        """Gera uma linha de log resumida."""
        duration = now_ms() - self.t_start
        steps_names = " → ".join(s.name for s in self.steps)
        return f"[{self.trace_id}] {duration}ms | {steps_names}"
    
    def total_ms(self) -> int:
        """Retorna duração total em ms."""
        return now_ms() - self.t_start
    
    @property
    def steps_dict(self) -> List[Dict]:
        """Retorna steps como lista de dicts para JSON."""
        return [asdict(s) for s in self.steps]
