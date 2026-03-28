# Roleta Cloud - Estado do Jogo

import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, ClassVar
from pathlib import Path

logger = logging.getLogger(__name__)

from app_config.settings import settings
from core.roulette import roulette
from .timeline import Timeline
from .bet_advisor import TripleRateAdvisor, BetAdvice



@dataclass
class MartingaleState:
    """
    Smart Gale v5 — Anti-Martingale com Take-Profit.
    
    Gales: 1× (R$21), 2× (R$42), 3× (R$63). SEMPRE aposta.
    
    Regra 1 — Teto por Score SDA:
      Score 1-2 → max 1× | Score 3-4 → max 2× | Score 5-6 → max 3×
    Regra 2 — Anti-Martingale com Streak Global:
      0-1 global streak → 1× | 2 global streak → 2× | 3+ global streak → 3×
    Regra 3 — Reset após MISS: qualquer miss → volta 1× imediatamente
    Regra 4 — Gale Advisor: C4 rate < 15% → forçar teto 1×
    Regra 5 — Take-Profit: G3 + HIT → lock profit, reset G1
    """
    level: int = 1
    consecutive_hits: int = 0
    global_consecutive_hits: int = 0
    total_bets: int = 0
    
    BET_VALUES: ClassVar[Dict[int, int]] = {1: 21, 2: 42, 3: 63}
    
    @property
    def current_bet(self) -> int:
        return self.BET_VALUES.get(self.level, 21)
    
    @property
    def multiplier(self) -> str:
        multipliers = {1: "1x", 2: "2x", 3: "3x"}
        return multipliers.get(self.level, "1x")
    
    @property
    def gale_display(self) -> str:
        return f"G{self.level} S{self.consecutive_hits} GS{self.global_consecutive_hits}"
    
    def get_gale(self, score: int = 3, c4_rate: float = 0.5) -> int:
        """SmartGale v5: Anti-Martingale com streak global. Retorna 1, 2 ou 3."""
        # Regra 1 — Teto por Score (mantida)
        if score <= 2:
            max_gale = 1
        elif score <= 4:
            max_gale = 2
        else:
            max_gale = 3
        
        # Regra 4 — C4 advisor (threshold ajustado 0.25→0.15)
        if c4_rate < 0.15:
            max_gale = 1
        
        # Regra 2 — Anti-Martingale: streak global decide escalação
        streak = self.global_consecutive_hits
        if streak >= 3:
            desired = 3
        elif streak >= 2:
            desired = 2
        else:
            desired = 1
        
        self.level = min(desired, max_gale)
        return self.level
    
    def update(self, hit: bool, global_hit: bool = None) -> Dict[str, Any]:
        """Atualiza estado após resultado. Inclui take-profit em G3."""
        level_before = self.level
        self.total_bets += 1
        
        if hit:
            self.consecutive_hits += 1
            # Regra 5 — Take-Profit: G3 + HIT → lock profit, reset
            if level_before == 3:
                self.level = 1
                self.consecutive_hits = 0
        else:
            self.consecutive_hits = 0
            self.level = 1
        
        # Streak global (cross-direction)
        if global_hit is not None:
            if global_hit:
                self.global_consecutive_hits += 1
            else:
                self.global_consecutive_hits = 0
        
        transition = None
        if hit and level_before == 3:
            transition = f"💰 TAKE-PROFIT: G3 HIT → lock, reset G1"
        elif hit and self.global_consecutive_hits >= 2:
            transition = f"🔥 GLOBAL STREAK {self.global_consecutive_hits}: escalação liberada"
        elif not hit and level_before > 1:
            transition = f"↩️ RESET: G{level_before} → G1"
        
        return {
            "hit": hit,
            "consecutive_hits": self.consecutive_hits,
            "global_consecutive_hits": self.global_consecutive_hits,
            "level_before": level_before,
            "level_after": self.level,
            "current_bet": self.current_bet,
            "multiplier": self.multiplier,
            "transition": transition
        }
    
    def sync_global(self, global_hit: bool):
        """Sincroniza streak global sem alterar estado local da direção."""
        if global_hit:
            self.global_consecutive_hits += 1
        else:
            self.global_consecutive_hits = 0
    
    def to_dict(self) -> Dict:
        return {
            "level": self.level,
            "consecutive_hits": self.consecutive_hits,
            "global_consecutive_hits": self.global_consecutive_hits,
            "total_bets": self.total_bets
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "MartingaleState":
        obj = cls(
            level=data.get("level", 1),
            consecutive_hits=data.get("consecutive_hits", 0),
            total_bets=data.get("total_bets", data.get("window_count", 0) + data.get("total_stops", 0) * 5)
        )
        obj.global_consecutive_hits = data.get("global_consecutive_hits", 0)
        return obj


@dataclass
class GameState:
    """
    Estado completo do jogo.
    Mantém duas timelines (horário e anti-horário) + último spin.
    Inclui tracking de performance e calibração por direção.
    """
    # 🔧 TASK-04: ClassVar para evitar recriação a cada chamada
    _VALID_DIRECTIONS: ClassVar[set] = {"horario", "anti-horario"}

    # Último spin
    last_number: int = 0
    last_direction: str = ""
    
    # Duas linhas temporais
    timeline_cw: Timeline = field(default_factory=lambda: Timeline("cw"))
    timeline_ccw: Timeline = field(default_factory=lambda: Timeline("ccw"))
    
    # Performance SDA17 - SEMPRE que SDA17 recomenda (base para Triple Rate)
    performance_sda17_cw: deque = field(default_factory=lambda: deque(maxlen=12))
    performance_sda17_ccw: deque = field(default_factory=lambda: deque(maxlen=12))
    
    # Performance Apostas - APENAS quando realmente aposta (base para Martingale)
    performance_bet_cw: deque = field(default_factory=lambda: deque(maxlen=12))
    performance_bet_ccw: deque = field(default_factory=lambda: deque(maxlen=12))
    
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
        self.performance_sda17_cw = deque(maxlen=12)
        self.performance_sda17_ccw = deque(maxlen=12)
        
        # Reset Performance Apostas
        self.performance_bet_cw = deque(maxlen=12)
        self.performance_bet_ccw = deque(maxlen=12)
        
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
        # 🔧 BUG-011: validar direcao
        if direcao not in self._VALID_DIRECTIONS:
            logger.warning(f"⚠️ Direção inválida ignorada: '{direcao}' (esperado: {self._VALID_DIRECTIONS})")
            return 0
        
        force = 0
        
        if self.last_direction:  # Tem spin anterior válido
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
            self.performance_sda17_cw.appendleft(hit)
        else:
            self.performance_sda17_ccw.appendleft(hit)
        
        # APENAS adicionar ao histórico BET se realmente apostou
        if bet_placed:
            if direction in ("cw", "horario"):
                self.performance_bet_cw.appendleft(hit)
            else:
                self.performance_bet_ccw.appendleft(hit)
        
        # Limpar predição pendente
        self.pending_prediction = {}
        
        return hit
    
    # _circular_diff e _update_calibration removidos (momentum desabilitado)
    
    def store_prediction(self, numbers: List[int], direction: str, center: int, 
                         predicted_force: int = 0, bet_placed: bool = False,
                         tr_confidence: str = "", tr_reason: str = "", sda_score: int = 0,
                         sda_centers: List[int] = None) -> None:
        """
        Armazena a predição atual para verificar no próximo spin.
        
        Args:
            bet_placed: True se realmente apostou, False se apenas registrando para Triple Rate
            tr_confidence: Nível de confiança do Triple Rate (para tracking)
            tr_reason: Razão do Triple Rate (para tracking)
            sda_score: Score do SDA (para tracking)
            sda_centers: Lista de centros [C1, C2, C3] — SDA-21
        """
        self.pending_prediction = {
            "numbers": numbers,
            "direction": direction,
            "center": center,
            "centers": sda_centers or [center],
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
        def calc_stats(perf_list) -> Dict:
            hits = sum(perf_list) if perf_list else 0
            total = len(perf_list)
            return {
                "results": list(perf_list),
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
            }
        }
    
    def _calculate_force(self, from_num: int, to_num: int, direction: str) -> int:
        """Calcula a distância (força) entre dois números."""
        try:
            from_pos = roulette.WHEEL_SEQUENCE.index(from_num)
            to_pos = roulette.WHEEL_SEQUENCE.index(to_num)
            wheel_size = len(roulette.WHEEL_SEQUENCE)
            
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
        Usado pelo Triple Rate Advisor (Kill Switch) para analisar tendência.
        Retorna list (não deque) para compatibilidade com slicing.
        """
        if self.last_direction == "horario":
            return list(self.performance_sda17_ccw)
        return list(self.performance_sda17_cw)
    
    @property
    def target_performance_bet(self) -> List[bool]:
        """
        Retorna performance de APOSTAS REAIS da direção ALVO.
        Usado pelo SmartGaleV4 para c4_rate (BUG-28-03 fix).
        """
        if self.last_direction == "horario":
            return list(self.performance_bet_ccw)
        return list(self.performance_bet_cw)
    
    def get_bet_c4_rate(self) -> float:
        """
        C4 rate baseado em apostas reais (para SmartGaleV4).
        Usa performance_bet em vez de performance_sda17.
        """
        perf = self.target_performance_bet
        if len(perf) == 0:
            return 0.5
        if len(perf) < 4:
            return sum(perf) / len(perf)
        return sum(perf[:4]) / 4
    
    @property
    def target_martingale(self) -> MartingaleState:
        """
        Retorna Martingale da direção ALVO (oposta à última).
        Usado para atualizar após resultado de aposta.
        """
        if self.last_direction == "horario":
            return self.martingale_ccw
        return self.martingale_cw
    
    def get_bet_advice(self, sda_score: int = 3) -> BetAdvice:
        """
        Retorna recomendação de aposta baseada no Kill Switch Advisor.
        Analisa a performance da direção alvo + qualidade dos dados SDA.
        
        Args:
            sda_score: Score de confiança do SDA17-R (1-6)
        
        Returns:
            BetAdvice com should_bet, confidence, reason e rates
        """
        return self.bet_advisor.analyze(self.target_performance, sda_score=sda_score)
    
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
            "performance_sda17_cw": list(self.performance_sda17_cw),
            "performance_sda17_ccw": list(self.performance_sda17_ccw),
            "performance_bet_cw": list(self.performance_bet_cw),
            "performance_bet_ccw": list(self.performance_bet_ccw),
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
        
        try:
            os.replace(temp_path, path)
        except OSError:
            try:
                with open(path, 'w', encoding='utf-8') as target:
                    with open(temp_path, 'r', encoding='utf-8') as source:
                        target.write(source.read())
            finally:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    
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
            try:
                version_tuple = tuple(map(int, str(version).split(".")))
            except (ValueError, AttributeError):
                version_tuple = (1, 0, 0)
            
            # MIGRAÇÃO v1.3 -> v1.4 (legado)
            if version_tuple < (1, 4, 0):
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
                    performance_sda17_cw=deque(perf_cw, maxlen=12),
                    performance_sda17_ccw=deque(perf_ccw, maxlen=12),
                    performance_bet_cw=deque(maxlen=12),
                    performance_bet_ccw=deque(maxlen=12),
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
                performance_sda17_cw=deque(data.get("performance_sda17_cw", []), maxlen=12),
                performance_sda17_ccw=deque(data.get("performance_sda17_ccw", []), maxlen=12),
                performance_bet_cw=deque(data.get("performance_bet_cw", []), maxlen=12),
                performance_bet_ccw=deque(data.get("performance_bet_ccw", []), maxlen=12),
                martingale_cw=MartingaleState.from_dict(data.get("martingale_cw", {})),
                martingale_ccw=MartingaleState.from_dict(data.get("martingale_ccw", {})),
                pending_prediction=data.get("pending_prediction", {})
            )
        except Exception as e:
            logger.error(f"Falha ao carregar state.json: {e}")
            try:
                import shutil
                backup = Path(str(path) + '.corrupted')
                shutil.copy2(path, backup)
                logger.info(f"Backup do state corrompido salvo em: {backup}")
            except Exception:
                pass
            return cls()
