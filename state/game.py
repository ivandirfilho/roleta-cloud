# Roleta Cloud - Estado do Jogo

import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

import config
from .timeline import Timeline


@dataclass
class GameState:
    """
    Estado completo do jogo.
    Mantém duas timelines (horário e anti-horário) + último spin.
    Inclui tracking de performance por direção.
    """
    # Último spin
    last_number: int = 0
    last_direction: str = ""
    
    # Duas linhas temporais
    timeline_cw: Timeline = field(default_factory=lambda: Timeline("cw"))
    timeline_ccw: Timeline = field(default_factory=lambda: Timeline("ccw"))
    
    # Performance tracking (últimos 12 por direção)
    performance_cw: List[bool] = field(default_factory=list)  # True=hit, False=miss
    performance_ccw: List[bool] = field(default_factory=list)
    
    # Pendente: última sugestão para verificar no próximo spin
    pending_prediction: Dict[str, Any] = field(default_factory=dict)
    
    def process_spin(self, numero: int, direcao: str) -> int:
        """
        Processa um novo spin:
        1. Calcula a força (distância do anterior)
        2. Adiciona à timeline correta
        3. Atualiza último spin
        
        Retorna: força calculada
        """
        force = 0
        
        if self.last_number > 0 or self.last_number == 0:  # Tem número anterior
            force = self._calculate_force(self.last_number, numero, direcao)
            
            # Adiciona à timeline correta
            if direcao == "horario":
                self.timeline_cw.add(force)
            else:
                self.timeline_ccw.add(force)
        
        # Atualiza último spin
        self.last_number = numero
        self.last_direction = direcao
        
        return force
    
    def check_prediction(self, actual_number: int) -> Optional[bool]:
        """
        Verifica se a predição anterior foi acertada.
        Retorna True (hit), False (miss), ou None se não havia predição.
        """
        if not self.pending_prediction:
            return None
        
        pred = self.pending_prediction
        numbers = pred.get("numbers", [])
        direction = pred.get("direction", "")
        
        # Verificar se acertou
        hit = actual_number in numbers
        
        # Adicionar ao tracking da direção correspondente
        if direction in ("cw", "horario"):
            self.performance_cw.insert(0, hit)
            if len(self.performance_cw) > 12:
                self.performance_cw.pop()
        else:
            self.performance_ccw.insert(0, hit)
            if len(self.performance_ccw) > 12:
                self.performance_ccw.pop()
        
        # Limpar predição pendente
        self.pending_prediction = {}
        
        return hit
    
    def store_prediction(self, numbers: List[int], direction: str, center: int) -> None:
        """Armazena a predição atual para verificar no próximo spin."""
        self.pending_prediction = {
            "numbers": numbers,
            "direction": direction,
            "center": center
        }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas de performance."""
        cw_hits = sum(self.performance_cw) if self.performance_cw else 0
        cw_total = len(self.performance_cw)
        ccw_hits = sum(self.performance_ccw) if self.performance_ccw else 0
        ccw_total = len(self.performance_ccw)
        
        return {
            "cw": {
                "results": self.performance_cw,
                "hits": cw_hits,
                "total": cw_total,
                "rate": round(cw_hits / cw_total * 100) if cw_total else 0
            },
            "ccw": {
                "results": self.performance_ccw,
                "hits": ccw_hits,
                "total": ccw_total,
                "rate": round(ccw_hits / ccw_total * 100) if ccw_total else 0
            }
        }
    
    def _calculate_force(self, from_num: int, to_num: int, direction: str) -> int:
        """Calcula a distância (força) entre dois números."""
        try:
            from_pos = config.WHEEL_SEQUENCE.index(from_num)
            to_pos = config.WHEEL_SEQUENCE.index(to_num)
            wheel_size = len(config.WHEEL_SEQUENCE)
            
            if direction == "horario":
                force = (to_pos - from_pos) % wheel_size
            else:
                force = (from_pos - to_pos) % wheel_size
            
            # Força 0 significa volta completa
            if force == 0 and from_num != to_num:
                force = wheel_size
            
            return force
        except ValueError:
            return 0
    
    @property
    def target_direction(self) -> str:
        """Direção alvo (oposta à última)."""
        if self.last_direction == "horario":
            return "anti-horario"
        return "horario"
    
    @property
    def target_timeline(self) -> Timeline:
        """Timeline alvo para análise (oposta à última direção)."""
        if self.last_direction == "horario":
            return self.timeline_ccw
        return self.timeline_cw
    
    def save(self, path: Optional[Path] = None) -> None:
        """Salva estado em arquivo JSON."""
        path = path or config.STATE_FILE
        data = {
            "version": "1.1.0",
            "last_number": self.last_number,
            "last_direction": self.last_direction,
            "timeline_cw": self.timeline_cw.to_dict(),
            "timeline_ccw": self.timeline_ccw.to_dict(),
            "performance_cw": self.performance_cw,
            "performance_ccw": self.performance_ccw,
            "pending_prediction": self.pending_prediction
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "GameState":
        """Carrega estado de arquivo JSON."""
        path = path or config.STATE_FILE
        if not path.exists():
            return cls()
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            return cls(
                last_number=data.get("last_number", 0),
                last_direction=data.get("last_direction", ""),
                timeline_cw=Timeline.from_dict(data.get("timeline_cw", {})),
                timeline_ccw=Timeline.from_dict(data.get("timeline_ccw", {})),
                performance_cw=data.get("performance_cw", []),
                performance_ccw=data.get("performance_ccw", []),
                pending_prediction=data.get("pending_prediction", {})
            )
        except Exception:
            return cls()
