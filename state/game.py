# Roleta Cloud - Estado do Jogo

import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

from app_config.settings import settings
from .timeline import Timeline
from .bet_advisor import TripleRateAdvisor, BetAdvice



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
    
    @property
    def gale_display(self) -> str:
        """Retorna status no formato 'G1 2/5' (nível + hits/window_count)."""
        return f"G{self.level} {self.window_hits}/{self.window_count}"
    
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
            "multiplier": self.multiplier,
            "gale_display": self.gale_display
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
    
    # Performance SDA17 - SEMPRE que SDA17 recomenda (base para Triple Rate)
    performance_sda17_cw: List[bool] = field(default_factory=list)
    performance_sda17_ccw: List[bool] = field(default_factory=list)
    
    # Performance Apostas - APENAS quando realmente aposta (base para Martingale)
    performance_bet_cw: List[bool] = field(default_factory=list)
    performance_bet_ccw: List[bool] = field(default_factory=list)
    
    # Calibração removida (momentum desabilitado)
    
    # Martingale por direção (janela de 5 jogadas cada)
    martingale_cw: MartingaleState = field(default_factory=MartingaleState)
    martingale_ccw: MartingaleState = field(default_factory=MartingaleState)
    
    # Pendente: última sugestão para verificar no próximo spin
    # Inclui bet_placed=True/False para saber se realmente apostou
    pending_prediction: Dict[str, Any] = field(default_factory=dict)
    
    # Triple Rate Advisor
    bet_advisor: TripleRateAdvisor = field(default_factory=TripleRateAdvisor)
    
    def reset_session(self, keep_last_number: bool = False) -> Dict[str, Any]:
        """
        Reseta estado para nova sessão/dealer.
        
        Deve ser chamado quando:
        - Muda o dealer
        - Muda de mesa
        - Usuário quer começar do zero
        
        Args:
            keep_last_number: Se True, mantém last_number para continuidade
        
        Returns:
            Dict com informações do reset
        """
        old_state = {
            "timeline_cw_size": self.timeline_cw.size,
            "timeline_ccw_size": self.timeline_ccw.size,
            "martingale_cw_level": self.martingale_cw.level,
            "martingale_ccw_level": self.martingale_ccw.level,
            "performance_sda17_cw": len(self.performance_sda17_cw),
            "performance_sda17_ccw": len(self.performance_sda17_ccw),
        }
        
        # Reset Timelines
        self.timeline_cw = Timeline("cw")
        self.timeline_ccw = Timeline("ccw")
        
        # Reset Performance SDA17
        self.performance_sda17_cw = []
        self.performance_sda17_ccw = []
        
        # Reset Performance Apostas
        self.performance_bet_cw = []
        self.performance_bet_ccw = []
        
        # Calibração removida (momentum desabilitado)
        
        # Reset Martingale
        self.martingale_cw = MartingaleState()
        self.martingale_ccw = MartingaleState()
        
        # Reset Prediction pendente
        self.pending_prediction = {}
        
        # Reset último número (opcional)
        if not keep_last_number:
            self.last_number = 0
            self.last_direction = ""
        
        # Salvar estado limpo
        self.save()
        
        return {"reset": True, "old_state": old_state}
    
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
        
        SEPARAÇÃO DE HISTÓRICOS:
        - performance_sda17: SEMPRE registra (usado pelo Triple Rate)
        - performance_bet: APENAS se bet_placed=True (usado pelo Martingale)
        
        Retorna True (hit), False (miss), ou None se não havia predição.
        """
        if not self.pending_prediction:
            return None
        
        pred = self.pending_prediction
        numbers = pred.get("numbers", [])
        direction = pred.get("direction", "")
        predicted_force = pred.get("predicted_force", 0)
        bet_placed = pred.get("bet_placed", False)  # Nova flag
        
        # Verificar se acertou
        hit = actual_number in numbers
        
        # Calibração removida (momentum desabilitado)
        
        # SEMPRE adicionar ao histórico SDA17 (base para Triple Rate)
        if direction in ("cw", "horario"):
            self.performance_sda17_cw.insert(0, hit)
            if len(self.performance_sda17_cw) > 12:
                self.performance_sda17_cw.pop()
        else:
            self.performance_sda17_ccw.insert(0, hit)
            if len(self.performance_sda17_ccw) > 12:
                self.performance_sda17_ccw.pop()
        
        # APENAS adicionar ao histórico BET se realmente apostou
        if bet_placed:
            if direction in ("cw", "horario"):
                self.performance_bet_cw.insert(0, hit)
                if len(self.performance_bet_cw) > 12:
                    self.performance_bet_cw.pop()
            else:
                self.performance_bet_ccw.insert(0, hit)
                if len(self.performance_bet_ccw) > 12:
                    self.performance_bet_ccw.pop()
        
        # Limpar predição pendente
        self.pending_prediction = {}
        
        return hit
    
    # _circular_diff e _update_calibration removidos (momentum desabilitado)
    
    def store_prediction(self, numbers: List[int], direction: str, center: int, 
                         predicted_force: int = 0, bet_placed: bool = False,
                         tr_confidence: str = "", tr_reason: str = "", sda_score: int = 0) -> None:
        """
        Armazena a predição atual para verificar no próximo spin.
        
        Args:
            bet_placed: True se realmente apostou, False se apenas registrando para Triple Rate
            tr_confidence: Nível de confiança do Triple Rate (para tracking)
            tr_reason: Razão do Triple Rate (para tracking)
            sda_score: Score do SDA17 (para tracking)
        """
        self.pending_prediction = {
            "numbers": numbers,
            "direction": direction,
            "center": center,
            "predicted_force": predicted_force,
            "bet_placed": bet_placed,
            "tr_confidence": tr_confidence,
            "tr_reason": tr_reason,
            "sda_score": sda_score
        }
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas de performance para todas as 4 listas.
        
        - performance_sda17: base para Triple Rate (todas recomendações SDA17)
        - performance_bet: base para Martingale (apenas apostas reais)
        """
        def calc_stats(perf_list: List[bool]) -> Dict:
            hits = sum(perf_list) if perf_list else 0
            total = len(perf_list)
            return {
                "results": perf_list,
                "hits": hits,
                "total": total,
                "rate": round(hits / total * 100) if total else 0
            }
        
        return {
            "sda17": {
                "cw": calc_stats(self.performance_sda17_cw),
                "ccw": calc_stats(self.performance_sda17_ccw)
            },
            "bet": {
                "cw": calc_stats(self.performance_bet_cw),
                "ccw": calc_stats(self.performance_bet_ccw)
            },
            "cw": calc_stats(self.performance_sda17_cw),
            "ccw": calc_stats(self.performance_sda17_ccw)
        }
    
    def _calculate_force(self, from_num: int, to_num: int, direction: str) -> int:
        """Calcula a distância (força) entre dois números."""
        try:
            from_pos = settings.game.wheel_sequence.index(from_num)
            to_pos = settings.game.wheel_sequence.index(to_num)
            wheel_size = len(settings.game.wheel_sequence)
            
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
    
    # target_calibration removido (momentum desabilitado)
    
    @property
    def target_performance(self) -> List[bool]:
        """
        Retorna performance SDA17 da direção ALVO (oposta à última).
        Usado pelo Triple Rate Advisor para analisar tendência.
        """
        if self.last_direction == "horario":
            return self.performance_sda17_ccw
        return self.performance_sda17_cw
    
    @property
    def target_martingale(self) -> MartingaleState:
        """
        Retorna Martingale da direção ALVO (oposta à última).
        Usado para atualizar após resultado de aposta.
        """
        if self.last_direction == "horario":
            return self.martingale_ccw
        return self.martingale_cw
    
    def get_bet_advice(self) -> BetAdvice:
        """
        Retorna recomendação de aposta baseada no Triple Rate Advisor.
        Analisa a performance da direção alvo (próxima aposta).
        
        Returns:
            BetAdvice com should_bet, confidence, reason e rates
        """
        return self.bet_advisor.analyze(self.target_performance)
    
    def save(self, path: Optional[Path] = None) -> None:
        """Salva estado em arquivo JSON (v1.5 - sem calibração) com escrita atômica."""
        import os
        import tempfile
        
        path = path or settings.state_file
        data = {
            "version": "1.5.0",
            "last_number": self.last_number,
            "last_direction": self.last_direction,
            "timeline_cw": self.timeline_cw.to_dict(),
            "timeline_ccw": self.timeline_ccw.to_dict(),
            "performance_sda17_cw": self.performance_sda17_cw,
            "performance_sda17_ccw": self.performance_sda17_ccw,
            "performance_bet_cw": self.performance_bet_cw,
            "performance_bet_ccw": self.performance_bet_ccw,
            "martingale_cw": self.martingale_cw.to_dict(),
            "martingale_ccw": self.martingale_ccw.to_dict(),
            "pending_prediction": self.pending_prediction
        }
        
        # Escrita atômica: escreve em temp, depois renomeia
        dir_path = Path(path).parent
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tmp', 
                                          dir=dir_path, delete=False, 
                                          encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            temp_path = f.name
        
        # os.replace é atômico na maioria dos sistemas de arquivos
        os.replace(temp_path, path)

    
    @classmethod
    def load(cls, path: Optional[Path] = None) -> "GameState":
        """
        Carrega estado de arquivo JSON.
        
        MIGRAÇÕES:
        - v1.3 -> v1.4: performance_cw/ccw -> performance_sda17_cw/ccw
        - v1.3 -> v1.4: martingale -> martingale_cw e martingale_ccw (copia para ambos)
        """
        path = path or settings.state_file
        if not path.exists():
            return cls()
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            version = data.get("version", "1.0.0")
            
            # MIGRAÇÃO v1.3 -> v1.4 (legado)
            if version < "1.4.0":
                # Migrar performance antigo para sda17
                perf_cw = data.get("performance_cw", [])
                perf_ccw = data.get("performance_ccw", [])
                
                # Migrar martingale único para ambos
                old_martingale = data.get("martingale", {})
                
                return cls(
                    last_number=data.get("last_number", 0),
                    last_direction=data.get("last_direction", ""),
                    timeline_cw=Timeline.from_dict(data.get("timeline_cw", {})),
                    timeline_ccw=Timeline.from_dict(data.get("timeline_ccw", {})),
                    performance_sda17_cw=perf_cw,
                    performance_sda17_ccw=perf_ccw,
                    performance_bet_cw=[],
                    performance_bet_ccw=[],
                    martingale_cw=MartingaleState.from_dict(old_martingale),
                    martingale_ccw=MartingaleState.from_dict(old_martingale),
                    pending_prediction=data.get("pending_prediction", {})
                )
            
            # v1.4+ / v1.5+ - formato atual (ignora calibração se presente)
            return cls(
                last_number=data.get("last_number", 0),
                last_direction=data.get("last_direction", ""),
                timeline_cw=Timeline.from_dict(data.get("timeline_cw", {})),
                timeline_ccw=Timeline.from_dict(data.get("timeline_ccw", {})),
                performance_sda17_cw=data.get("performance_sda17_cw", []),
                performance_sda17_ccw=data.get("performance_sda17_ccw", []),
                performance_bet_cw=data.get("performance_bet_cw", []),
                performance_bet_ccw=data.get("performance_bet_ccw", []),
                martingale_cw=MartingaleState.from_dict(data.get("martingale_cw", {})),
                martingale_ccw=MartingaleState.from_dict(data.get("martingale_ccw", {})),
                pending_prediction=data.get("pending_prediction", {})
            )
        except Exception:
            return cls()
