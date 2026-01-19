# Roleta Cloud - Estado do Jogo

import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

import config
from .timeline import Timeline


@dataclass
class CalibrationState:
    """Estado de calibração usando Momentum (otimizado após auditoria)."""
    offset: int = 0  # Offset atual aplicado
    error_history: List[int] = field(default_factory=list)  # Histórico de erros para momentum
    
    def to_dict(self) -> Dict:
        return {
            "offset": self.offset,
            "error_history": self.error_history[-5:]  # Guarda últimos 5
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CalibrationState":
        return cls(
            offset=data.get("offset", 0),
            error_history=data.get("error_history", [])
        )


@dataclass
class MartingaleState:
    """
    Sistema de Martingale Inteligente com janela de 5 jogadas.
    
    Lógica:
    - GALE 1 = R$17 (5 jogadas): 3+ acertos → mantém | 2- → GALE 2
    - GALE 2 = R$34 (5 jogadas): 3+ acertos → GALE 1 | 2- → GALE 3
    - GALE 3 = R$68 (5 jogadas): 3+ acertos → GALE 1 | 2- → STOP + reinicia GALE 1
    """
    level: int = 1                    # Nível atual (1, 2 ou 3)
    window_hits: int = 0              # Acertos na janela atual
    window_count: int = 0             # Jogadas na janela atual
    total_stops: int = 0              # Total de stops desde início
    
    # Valores de aposta por nível
    BET_VALUES = {1: 17, 2: 34, 3: 68}
    WINDOW_SIZE = 5                   # Tamanho da janela
    MIN_HITS_TO_PASS = 3              # Mínimo de acertos para passar/manter
    
    @property
    def current_bet(self) -> int:
        """Retorna valor da aposta atual."""
        return self.BET_VALUES.get(self.level, 17)
    
    @property
    def multiplier(self) -> str:
        """Retorna multiplicador como string (ex: '1x', '2x', '4x')."""
        multipliers = {1: "1x", 2: "2x", 3: "4x"}
        return multipliers.get(self.level, "1x")
    
    def update(self, hit: bool) -> Dict[str, Any]:
        """
        Atualiza estado do martingale após um resultado.
        
        Returns:
            Dict com informações da transição
        """
        self.window_count += 1
        if hit:
            self.window_hits += 1
        
        result = {
            "hit": hit,
            "window_count": self.window_count,
            "window_hits": self.window_hits,
            "level_before": self.level,
            "transition": None
        }
        
        # Verificar se completou janela de 5
        if self.window_count >= self.WINDOW_SIZE:
            if self.window_hits >= self.MIN_HITS_TO_PASS:
                # Sucesso! Volta para GALE 1
                if self.level > 1:
                    result["transition"] = f"SUCESSO: Voltando para GALE 1"
                else:
                    result["transition"] = f"SUCESSO: Mantém GALE 1"
                self.level = 1
            else:
                # Falha! Próximo nível ou STOP
                if self.level < 3:
                    self.level += 1
                    result["transition"] = f"SUBINDO: Vai para GALE {self.level}"
                else:
                    # STOP e reinicia
                    self.total_stops += 1
                    result["transition"] = f"STOP #{self.total_stops}: Reiniciando GALE 1"
                    self.level = 1
            
            # Reset da janela
            self.window_hits = 0
            self.window_count = 0
        
        result["level_after"] = self.level
        result["current_bet"] = self.current_bet
        result["multiplier"] = self.multiplier
        
        return result
    
    def to_dict(self) -> Dict:
        return {
            "level": self.level,
            "window_hits": self.window_hits,
            "window_count": self.window_count,
            "total_stops": self.total_stops,
            "current_bet": self.current_bet,
            "multiplier": self.multiplier
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MartingaleState":
        return cls(
            level=data.get("level", 1),
            window_hits=data.get("window_hits", 0),
            window_count=data.get("window_count", 0),
            total_stops=data.get("total_stops", 0)
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
    
    # Calibração por direção (momentum)
    calibration_cw: CalibrationState = field(default_factory=CalibrationState)
    calibration_ccw: CalibrationState = field(default_factory=CalibrationState)
    
    # Martingale inteligente (janela de 5 jogadas)
    martingale: MartingaleState = field(default_factory=MartingaleState)
    
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
        Atualiza calibração usando MOMENTUM.
        
        Calcula offset considerando:
        - 30% do erro atual
        - 20% da aceleração (mudança no erro)
        
        Baseado em auditoria de 90 estratégias que mostrou +80% de melhoria.
        """
        cal = self.calibration_cw if direction in ("cw", "horario") else self.calibration_ccw
        
        # Calcular aceleração (mudança no erro)
        if cal.error_history and len(cal.error_history) > 0:
            accel = error - cal.error_history[-1]
        else:
            accel = 0
        
        # Novo offset = offset atual + (30% do erro) + (20% da aceleração)
        new_offset = cal.offset + int(error * 0.3 + accel * 0.2)
        
        # Limitar a ±8
        cal.offset = max(-8, min(8, new_offset))
        
        # Guardar erro no histórico (máximo 5)
        cal.error_history.append(error)
        if len(cal.error_history) > 5:
            cal.error_history.pop(0)
    
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
            "version": "1.3.0",
            "last_number": self.last_number,
            "last_direction": self.last_direction,
            "timeline_cw": self.timeline_cw.to_dict(),
            "timeline_ccw": self.timeline_ccw.to_dict(),
            "performance_cw": self.performance_cw,
            "performance_ccw": self.performance_ccw,
            "calibration_cw": self.calibration_cw.to_dict(),
            "calibration_ccw": self.calibration_ccw.to_dict(),
            "martingale": self.martingale.to_dict(),
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
                martingale=MartingaleState.from_dict(data.get("martingale", {})),
                pending_prediction=data.get("pending_prediction", {})
            )
        except Exception:
            return cls()
