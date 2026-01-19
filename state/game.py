# Roleta Cloud - Estado do Jogo

import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

import config
from .timeline import Timeline


@dataclass
class CalibrationState:
    """Estado de calibração para fine-tuning de uma direção."""
    state: str = "normal"  # normal, atento, confirmado
    first_error: Optional[int] = None  # Primeiro erro observado
    offset: int = 0  # Offset atual aplicado
    
    def to_dict(self) -> Dict:
        return {"state": self.state, "first_error": self.first_error, "offset": self.offset}
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CalibrationState":
        return cls(
            state=data.get("state", "normal"),
            first_error=data.get("first_error"),
            offset=data.get("offset", 0)
        )


@dataclass
class GameState:
    """
    Estado completo do jogo.
    Mantém duas timelines (horário e anti-horário) + último spin.
    Inclui tracking de performance e calibração por direção.
    """
    # Último spin
    last_number: int = 0
    last_direction: str = ""
    
    # Duas linhas temporais
    timeline_cw: Timeline = field(default_factory=lambda: Timeline("cw"))
    timeline_ccw: Timeline = field(default_factory=lambda: Timeline("ccw"))
    
    # Performance tracking (últimos 12 por direção)
    performance_cw: List[bool] = field(default_factory=list)
    performance_ccw: List[bool] = field(default_factory=list)
    
    # Calibração por direção (fine-tuning 3 etapas)
    calibration_cw: CalibrationState = field(default_factory=CalibrationState)
    calibration_ccw: CalibrationState = field(default_factory=CalibrationState)
    
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
        predicted_force = pred.get("predicted_force", 0)
        
        # Verificar se acertou
        hit = actual_number in numbers
        
        # Calcular erro para calibração (se errou)
        if not hit and predicted_force > 0:
            actual_force = self._calculate_force(
                self.last_number, actual_number, 
                "horario" if direction in ("cw", "horario") else "anti-horario"
            )
            error = self._circular_diff(actual_force, predicted_force)
            self._update_calibration(direction, error)
        elif hit:
            # Acertou - manter calibração atual
            pass
        
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
    
    def _circular_diff(self, a: int, b: int, universe: int = 37) -> int:
        """Diferença circular com sinal (a - b) no universo circular."""
        diff = a - b
        if diff > universe // 2:
            diff -= universe
        elif diff < -universe // 2:
            diff += universe
        return diff
    
    def _update_calibration(self, direction: str, error: int) -> None:
        """
        Atualiza calibração em 3 etapas:
        1. NORMAL → ATENTO: primeiro erro, anota
        2. ATENTO → CONFIRMADO: segundo erro na mesma direção, calcula offset
        3. Se erro na direção oposta → volta para NORMAL
        """
        cal = self.calibration_cw if direction in ("cw", "horario") else self.calibration_ccw
        
        if cal.state == "normal":
            # Etapa 1: primeiro erro → atenção
            cal.state = "atento"
            cal.first_error = error
            
        elif cal.state == "atento":
            # Etapa 2: verificar se confirma ou cancela
            if cal.first_error is not None:
                # Mesmo sinal = confirma
                if (error > 0 and cal.first_error > 0) or (error < 0 and cal.first_error < 0):
                    # Confirma! Calcula offset (média dos dois erros)
                    new_offset = (cal.first_error + error) // 2
                    # Limitar a ±8
                    cal.offset = max(-8, min(8, new_offset))
                    cal.state = "confirmado"
                else:
                    # Direção oposta = outlier, cancela
                    cal.state = "normal"
                    cal.first_error = None
                    
        elif cal.state == "confirmado":
            # Já tem offset aplicado, continua ajustando suavemente
            if (error > 0 and cal.offset >= 0) or (error < 0 and cal.offset <= 0):
                # Erro na mesma direção do offset - ajustar um pouco mais
                adjustment = 1 if error > 0 else -1
                cal.offset = max(-8, min(8, cal.offset + adjustment))
            else:
                # Erro na direção oposta - reduzir offset
                if cal.offset > 0:
                    cal.offset -= 1
                elif cal.offset < 0:
                    cal.offset += 1
                if cal.offset == 0:
                    cal.state = "normal"
    
    def store_prediction(self, numbers: List[int], direction: str, center: int, predicted_force: int = 0) -> None:
        """Armazena a predição atual para verificar no próximo spin."""
        self.pending_prediction = {
            "numbers": numbers,
            "direction": direction,
            "center": center,
            "predicted_force": predicted_force
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
    
    @property
    def target_calibration(self) -> int:
        """Offset de calibração para a direção alvo."""
        if self.last_direction == "horario":
            return self.calibration_ccw.offset
        return self.calibration_cw.offset
    
    def save(self, path: Optional[Path] = None) -> None:
        """Salva estado em arquivo JSON."""
        path = path or config.STATE_FILE
        data = {
            "version": "1.2.0",
            "last_number": self.last_number,
            "last_direction": self.last_direction,
            "timeline_cw": self.timeline_cw.to_dict(),
            "timeline_ccw": self.timeline_ccw.to_dict(),
            "performance_cw": self.performance_cw,
            "performance_ccw": self.performance_ccw,
            "calibration_cw": self.calibration_cw.to_dict(),
            "calibration_ccw": self.calibration_ccw.to_dict(),
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
                calibration_cw=CalibrationState.from_dict(data.get("calibration_cw", {})),
                calibration_ccw=CalibrationState.from_dict(data.get("calibration_ccw", {})),
                pending_prediction=data.get("pending_prediction", {})
            )
        except Exception:
            return cls()
