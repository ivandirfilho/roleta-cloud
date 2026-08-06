# Roleta Cloud - Estado do Jogo

import json
import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, ClassVar, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

from app_config.settings import settings
from core.roulette import roulette
from .timeline import Timeline
from .bet_advisor import TripleRateAdvisor, BetAdvice
# Implantação C1/C2 variável + Block-Gale (17/06) — motores isolados, gated por flag.
from strategies.c_selection import CSelectionEngine
from state.block_gale import BlockGaleEngine, BLOCK_SIZE



@dataclass
class MartingaleState:
    """
    Smart Gale v6 — Anti-Martingale com Confiança.
    
    Gales: 1× (R$17), 2× (R$34), 3× (R$51). SEMPRE aposta.
    
    Regra 6 — Proteção por Confiança:
      "alta" (spike) → max 1× | "baixa" → max 1× | "media" → max 3×
    Regra 4 — Gale Advisor: C4 rate < 15% → forçar teto 1×
    Regra 2 — Anti-Martingale com Streak Global:
      0-1 global streak → 1× | 2 global streak → 2× | 3+ global streak → 3×
    Regra 3 — Reset após MISS: qualquer miss → volta 1× imediatamente
    Regra 5 — Take-Profit: G3 + HIT → lock profit, reset G1
    """
    level: int = 1
    consecutive_hits: int = 0
    global_consecutive_hits: int = 0
    total_bets: int = 0
    
    BET_VALUES: ClassVar[Dict[int, int]] = {1: 17, 2: 34, 3: 51}
    
    @property
    def current_bet(self) -> int:
        return self.BET_VALUES.get(self.level, 17)
    
    @property
    def multiplier(self) -> str:
        multipliers = {1: "1x", 2: "2x", 3: "3x"}
        return multipliers.get(self.level, "1x")
    
    @property
    def gale_display(self) -> str:
        return f"G{self.level} S{self.consecutive_hits} GS{self.global_consecutive_hits}"
    
    def get_gale(self, score: int = 3, c4_rate: float = 0.5, confidence: str = "media") -> int:
        """SmartGale v7 (S-STRAT-2): Anti-Martingale com escalação por streak.
        
        Mudança v6→v7: removido bloqueio `confidence==alta → max_gale=1` que
        prendia 94.7% das apostas em G1. Estudo live (260 decisões, 2026-05-25)
        mostrou que com confidence=alta o Anti-Martingale nunca escalava.
        
        Nova lógica:
        - max_gale=1 se sinal fraco (c4 < 0.25 OU sda_score < 3 OU confidence==baixa)
        - Caso contrário, max_gale=3 e o nível efetivo segue o streak global
        - Streak global cross-direction continua sendo o gatilho (>=2 → G2, >=3 → G3)
        """
        max_gale = 3
        
        # S-STRAT-2: Proteção só em sinais REALMENTE fracos.
        if confidence == "baixa":
            max_gale = 1
        if c4_rate < 0.25:
            max_gale = 1
        if score < 3:
            max_gale = 1

        # B5 CUT-POLICY v1 (12/06): gale máx 2 — gale 3 custa −6.60u/aposta
        # (hit 44.9% no dobro do stake); walk-forward valida gale<=2.
        try:
            from app_config.settings import profit_cut_v1_enabled
            if profit_cut_v1_enabled():
                max_gale = min(max_gale, 2)
        except Exception:
            pass
        
        # Regra 2 — Anti-Martingale: streak global decide escalação
        streak = self.global_consecutive_hits
        if streak >= 3:
            desired = 3
        elif streak >= 2:
            desired = 2
        else:
            desired = 1
        
        self.level = min(desired, max_gale)
        # Canary estruturado para grep em produção (decisao auditavel).
        try:
            import logging as _lg
            _lg.getLogger(__name__).info(
                "mg_gale_decided desired=%d max=%d applied=%d streak=%d c4=%.2f score=%d conf=%s",
                desired, max_gale, self.level, streak, c4_rate, score, confidence
            )
        except Exception:
            pass
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
            "total_bets": self.total_bets,
            # Campos esperados pelo dashboard frontend (app.js)
            "current_bet": self.current_bet,
            "gale_display": self.gale_display,
            "window_hits": self.consecutive_hits,
            "window_count": self.total_bets,
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

    # S-STRAT-10 v2 / S-STRAT-13 — Shadow grid: 4 challengers paralelos com
    # rotações distintas no wheel europeu (off-by-N hypothesis sweep).
    shadow_hits_cw: deque = field(default_factory=lambda: deque(maxlen=100))
    shadow_hits_ccw: deque = field(default_factory=lambda: deque(maxlen=100))
    # Cada shift mantém deque cw + ccw (maxlen=100). Inicializado em __post_init__.
    shadow_grid: Dict[int, Dict[str, deque]] = field(default_factory=dict)
    # BUG-A24-V3-17: incumbent paralelo com mesma janela do shadow (maxlen=100)
    # para baseline justo no champion detection.
    incumbent_shadow_cw: deque = field(default_factory=lambda: deque(maxlen=100))
    incumbent_shadow_ccw: deque = field(default_factory=lambda: deque(maxlen=100))
    
    # Calibração removida (momentum desabilitado)
    
    # Martingale por direção (janela de 5 jogadas cada)
    martingale_cw: MartingaleState = field(default_factory=MartingaleState)
    martingale_ccw: MartingaleState = field(default_factory=MartingaleState)
    
    # Pendente: última sugestão para verificar no próximo spin
    # Inclui bet_placed=True/False para saber se realmente apostou
    pending_prediction: Dict[str, Any] = field(default_factory=dict)

    # B2 (12/06): atribuição do último resultado por região (C1/C2/C3/miss)
    # + distância circular assinada até C1. Preenchido por check_prediction;
    # consumido pelo message_handler para persistir em decisions.result_region
    # e na DNA feature hit_region. Não persiste no state.json (efêmero).
    last_hit_attribution: Optional[Dict[str, Any]] = field(default=None)

    # V4 (13/06): últimos resultados sorteados (números puros) para a zona fria
    # de C3 — refatoracao_estrategica_13_06.md. Não confundir com as timelines
    # (que guardam FORÇAS). Mais recente em index 0 (appendleft).
    recent_results: deque = field(default_factory=lambda: deque(maxlen=10))

    # DIR3 (sentido-fase): o sentido é uma FASE alternada (a roleta gira um sentido
    # por vez). spin_seq = contador de giros reais ao vivo (n); seed_parity/seed_n =
    # âncora informada pelo operador; fase(n) = seed XOR ((n - seed_n) % 2).
    # direction_source = origem do sentido vigente; direction_locked = fase travada
    # pelo operador. Round-trip em save()/load()/reset_session(). Telemetria inócua
    # até SDA_SENTIDO_AUTORITATIVO=1 (não muda a aposta).
    spin_seq: int = 0
    seed_parity: str = ""
    seed_n: int = 0
    direction_source: str = ""
    direction_locked: bool = False
    # DIR10 (sentido-fase): ring buffer dedicado p/ overlay (timeline rica auditavel).
    # Cada entry: {"numero":int, "seq":int, "direction":str}. Mais recente em index 0
    # (mesma convencao de recent_results). SEPARADO de recent_results (maxlen=10, zona
    # fria C3 — nao mexer para nao quebrar SDA17). Tamanho controlado por
    # SDA_OVERLAY_ULTIMOS_N (default 12; 0 = desativa publicacao).
    _phase_overlay_ring: deque = field(default_factory=lambda: deque(maxlen=12))
    # DIR19 (sentido-fase): buffer dedicado p/ shift de fase (DIR4). Mantem janela 20
    # (suporta gap k<=20, > que recent_results maxlen=10). SEPARADO para nao alterar
    # zona fria C3 (8 testes SDA17 dependem da janela 10 original). phase_advance ja
    # aceita max_window=20 em state/phase.py.
    _phase_results: deque = field(default_factory=lambda: deque(maxlen=20))
    # V5.1 sig4 (05/08): placar de visitas das 6 regiões FIXAS da roda (5×6+1×7,
    # ordem física — strategies/regions_v5.py REGION6_SIZES). Conta TODOS os giros
    # dos DOIS sentidos + histórico (espelha recent_results). População sempre-on
    # e inerte (padrão shadow DIR-x); o USO no compose é gated por SDA_V5_SIG4.
    # Round-trip: save()/load()/reset_session().
    region6_counts: List[int] = field(default_factory=lambda: [0] * 6)
    
    # Triple Rate Advisor
    bet_advisor: TripleRateAdvisor = field(default_factory=TripleRateAdvisor)
    
    # M15-ADA: Estado adaptativo (v1.6+)
    _adaptive_state: Dict[str, Any] = field(default_factory=dict)

    # S-STRAT-13: rotações testadas em paralelo no shadow grid.
    SHADOW_SHIFTS: ClassVar[Tuple[int, ...]] = (1, 3, 5, 10)

    def __post_init__(self) -> None:
        # S-STRAT-13: inicializa deques por shift (4 challengers paralelos).
        # BUG-A24-V2-09 / V3-18: tratar None explicito + colapsar if duplicado.
        if not self.shadow_grid:
            self.shadow_grid = {
                s: {"cw": deque(maxlen=100), "ccw": deque(maxlen=100)}
                for s in self.SHADOW_SHIFTS
            }
        # BUG-A24-V3-17: incumbent paralelo (maxlen=100) para comparacao justa
        # com shadow_grid. performance_sda17 (maxlen=12) e curto demais para
        # baseline confiavel do champion detection.
        if not hasattr(self, "incumbent_shadow_cw") or self.incumbent_shadow_cw is None:
            self.incumbent_shadow_cw = deque(maxlen=100)
        if not hasattr(self, "incumbent_shadow_ccw") or self.incumbent_shadow_ccw is None:
            self.incumbent_shadow_ccw = deque(maxlen=100)

        # Implantação C1/C2 variável + Block-Gale (17/06): motores por sentido +
        # histórico de atribuições (dist_c1/c2/c3) para o voto. Gated por flag no handler.
        if not hasattr(self, "c_selection_engine") or self.c_selection_engine is None:
            self.c_selection_engine = CSelectionEngine()
        if not hasattr(self, "block_gale_engine") or self.block_gale_engine is None:
            self.block_gale_engine = BlockGaleEngine(base_unit=1.0)
        if not hasattr(self, "c_attr_cw") or self.c_attr_cw is None:
            self.c_attr_cw = deque(maxlen=12)
        if not hasattr(self, "c_attr_ccw") or self.c_attr_ccw is None:
            self.c_attr_ccw = deque(maxlen=12)

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

        # V4 (BUG-F): zera a janela de resultados da zona fria de C3 ao trocar
        # dealer/mesa — senão a frieza mistura sessões.
        self.recent_results = deque(maxlen=10)
        # DIR10 (sentido-fase): zera tambem o ring overlay — historico novo comeca limpo.
        self._phase_overlay_ring = deque(maxlen=12)
        # DIR19 (sentido-fase): zera buffer de fase tambem (janela 20).
        self._phase_results = deque(maxlen=20)
        # V5.1 sig4: placar das 6 regiões fixas é POR SESSÃO — zera na troca.
        self.region6_counts = [0] * 6
        
        # Calibração removida (momentum desabilitado)
        
        # Reset Martingale
        self.martingale_cw = MartingaleState()
        self.martingale_ccw = MartingaleState()

        # BUG-A24-13: Reset Shadow grid (S-STRAT-13) + legacy shadow_hits.
        # Sem isso, trocar dealer/mesa contamina o champion detection.
        self.shadow_hits_cw = deque(maxlen=100)
        self.shadow_hits_ccw = deque(maxlen=100)
        self.shadow_grid = {
            s: {"cw": deque(maxlen=100), "ccw": deque(maxlen=100)}
            for s in self.SHADOW_SHIFTS
        }
        # BUG-A24-V3-17: reset incumbent_shadow (paralelo maxlen=100).
        self.incumbent_shadow_cw = deque(maxlen=100)
        self.incumbent_shadow_ccw = deque(maxlen=100)
        # BUG-A24-V3-21: limpar estado adaptativo de shadow (EMA + suggestion)
        # ao trocar dealer/mesa para nao vazar sinais antigos.
        self._adaptive_state.pop("shadow_ema", None)
        self._adaptive_state.pop("suggested_shift", None)
        # S-STRAT-14: reset bandit no reset de sessão (evita contaminação cross-dealer).
        self._adaptive_state.pop("bandit", None)
        self._adaptive_state.pop("auto_promotes", None)

        # Implantação C1/C2 + Block-Gale (17/06): reset dos motores por sentido
        # (evita contaminação cross-dealer, igual ao shadow/bandit acima).
        try:
            self.c_selection_engine.reset()
            self.block_gale_engine.reset()
            self.c_attr_cw = deque(maxlen=12)
            self.c_attr_ccw = deque(maxlen=12)
        except Exception:  # noqa: BLE001
            pass
        
        # Reset Prediction pendente
        self.pending_prediction = {}
        
        # Reset último número (opcional)
        if not keep_last_number:
            self.last_number = 0
            self.last_direction = ""
        
        # DIR3 (sentido-fase): re-ancora a fase no novo começo (n=0). Mantém a
        # paridade-semente e o lock do operador (a roleta física segue alternando).
        self.spin_seq = 0
        self.seed_n = 0
        self.direction_source = "reset"
        # DIR16 (sentido-fase): FIX CRITICO #S/#W/#X — zerar tambem seed_parity para
        # forcar auto-seed da DIR5 no 1º giro pos-reset (se nao for lock explicito).
        # Sem isto, project_phase segue projetando com paridade da MESA ANTERIOR ate
        # o operador chamar set_seed manualmente — vetor real de aposta no lado errado
        # em handoff de dealer. Atras de flag SDA_RESET_REANCORA (default OFF byte-identico).
        from app_config.settings import reset_reancora_enabled
        if reset_reancora_enabled() and not self.direction_locked:
            self.seed_parity = ""
            self.last_phase_uncertain = False
            self.last_direction_event = None
        
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
        
        # V4: registra todo número sorteado (zona fria de C3), independente de
        # haver spin anterior. Antes do cálculo de força (BUG-F: ciclo de vida).
        self.recent_results.appendleft(numero)
        self._region6_bump(numero)
        # DIR19: buffer dedicado para shift (janela 20). Separado para nao alterar C3.
        try:
            self._phase_results.appendleft(int(numero))
        except Exception:  # noqa: BLE001 — observabilidade nunca quebra fluxo de aposta
            pass
        # DIR10 (sentido-fase): ring overlay rico (numero+seq+direction) — separado
        # para nao perturbar a zona fria C3. spin_seq atual reflete o evento ainda
        # nao incrementado (handle_new_result incrementa em :762 apos process_spin).
        try:
            self._phase_overlay_ring.appendleft({
                "numero": int(numero),
                "seq": int(getattr(self, "spin_seq", 0) or 0),
                "direction": direcao,
            })
        except Exception:  # noqa: BLE001 — observabilidade nunca quebra fluxo de aposta
            pass

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
    
    def _region6_bump(self, numero: int) -> None:
        """V5.1 sig4: incrementa a visita da região fixa (6 arcos) do número.

        Espelha recent_results: giros ao vivo (process_spin) E histórico
        (register_history_number) — TODOS os sentidos, por spec do operador.
        Defensivo: nunca quebra o fluxo de aposta."""
        try:
            from strategies.regions_v5 import region6_of
            gi = region6_of(int(numero), list(roulette.WHEEL_SEQUENCE))
            if gi is not None:
                self.region6_counts[gi] += 1
        except Exception:  # noqa: BLE001 — placar é observabilidade, não gate
            pass

    def sync_phase_buffer(self, nums) -> bool:
        """SPR-V1 B1 (furo A): espelha no buffer de fase os números recuperados num
        gap do DIR4, na MESMA ordem em que `phase_advance` os devolve (mais antigo →
        mais recente), de modo que `_phase_results` volte a espelhar o `allNumbers`
        do cliente e o próximo shift alinhe em k=1.

        Antes deste método o handler sincronizava apenas `recent_results` (zona fria
        C3) — desde a DIR19 o alinhamento lê `_phase_results`, então qualquer gap
        deixava o buffer de fase PERMANENTEMENTE defasado e todo giro seguinte virava
        `phase_uncertain` (com re-ancoragem na direção do cliente).

        Retorna True em sucesso. Se `_phase_results` estiver ausente (estado legado)
        ou os números não forem conversíveis, LOGA ERRO e retorna False — proibido
        engolir a falha em silêncio, pois é exatamente a regressão que este método
        corrige. Conversão feita ANTES de qualquer mutação (nunca deixa o buffer
        meio-atualizado). Não toca `recent_results` nem a aposta.
        """
        buf = getattr(self, "_phase_results", None)
        if buf is None:
            logger.error(
                "[FASE] sync_phase_buffer: _phase_results ausente (estado legado) — "
                "gap NAO sincronizado; proximo shift pode gerar phase_uncertain falso"
            )
            return False
        try:
            valores = [int(n) for n in (nums or [])]
        except (TypeError, ValueError) as e:
            logger.error(f"[FASE] sync_phase_buffer: numeros invalidos ({e}) — gap NAO sincronizado")
            return False
        for n in valores:
            buf.appendleft(n)
        return True

    def _apply_seed(self, direction: str, source: str = "",
                    locked: Optional[bool] = None, n: Optional[int] = None) -> bool:
        """SPR-V1 B4: ÚNICO caminho auditável de escrita da âncora de fase
        (`seed_parity`/`seed_n`/`direction_source`/`direction_locked`).

        - `locked=None` **preserva** o lock atual: omitir o campo NUNCA destrava o
          operador (antes, `handle_set_seed` fazia `bool(data.get("locked", False))`
          e um `set_seed` sem o campo destravava silenciosamente).
        - `source="vision"` é **recusado** quando há lock explícito (fail-close: a
          visão não usurpa uma âncora confirmada pelo operador) → retorna False.
        - `direction=""` (ou inválida) LIMPA a âncora (força auto-seed no próximo
          giro alinhado) — é o que DIR17/DIR16 precisam.
        - `source=""` preserva `direction_source` (re-ancoragem não muda a origem).
        - `n=None` ancora em `spin_seq` (o giro corrente).

        Nunca lança; nunca toca decisão/cobertura/stake (INV-3 intacto).
        """
        if source == "vision" and bool(getattr(self, "direction_locked", False)):
            logger.warning("[FASE] _apply_seed: fonte 'vision' recusada sob lock do operador")
            return False
        from state.phase import normalize as _norm, VALID as _VALID
        d = _norm(direction or "")
        self.seed_parity = d if d in _VALID else ""
        try:
            self.seed_n = int(self.spin_seq if n is None else n)
        except (TypeError, ValueError):
            self.seed_n = 0
        if source:
            self.direction_source = source
        if locked is not None:
            self.direction_locked = bool(locked)
        return True

    def register_history_number(self, numero: int) -> None:
        """DIR2 (sentido-fase): registra um número de HISTÓRICO como contexto
        NÃO-DIRECIONAL. O histórico do DOM (12 últimos) não carrega o sentido real
        do giro — a extensão o fabrica por alternância retroativa. Alimentar
        timeline_cw/ccw com essa direção inventada envenena o SDA17. Aqui só
        populamos recent_results (zona fria C3) e o último número, SEM tocar
        timelines nem last_direction (a fase real entra com os giros ao vivo)."""
        self.recent_results.appendleft(numero)
        self._region6_bump(numero)
        # DIR19: historico tambem alimenta buffer de fase (janela 20).
        try:
            self._phase_results.appendleft(int(numero))
        except Exception:  # noqa: BLE001 — observabilidade nunca quebra fluxo de aposta
            pass
        # DIR10: historico tambem entra no ring overlay (NAO-direcional explicito).
        try:
            self._phase_overlay_ring.appendleft({
                "numero": int(numero),
                "seq": int(getattr(self, "spin_seq", 0) or 0),
                "direction": "",  # NAO-direcional: historico nao carrega sentido real
            })
        except Exception:  # noqa: BLE001 — observabilidade nunca quebra fluxo de aposta
            pass
        self.last_number = numero
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

        # B2 (12/06): classificar EM QUAL região o resultado caiu (P5).
        # Antes só existia o hit binário — impossível saber se C2/C3 pagam
        # os 10 números que custam. Prioridade C1 > C2 > C3 (mesma regra do
        # feedback sigmoid em sda17._pct_sigmoid_update).
        try:
            self.last_hit_attribution = self._attribute_hit_region(
                pred.get("centers") or [], numbers, actual_number, hit
            )
        except Exception:  # noqa: BLE001 — atribuição nunca quebra o fluxo
            self.last_hit_attribution = None
        
        # Calibração removida (momentum desabilitado)
        
        # SEMPRE adicionar ao histórico SDA17 (base para Triple Rate)
        if direction in ("cw", "horario"):
            self.performance_sda17_cw.appendleft(hit)
            # BUG-A24-V3-17: incumbent paralelo maxlen=100 (baseline justo p/ shadow)
            self.incumbent_shadow_cw.appendleft(hit)
        else:
            self.performance_sda17_ccw.appendleft(hit)
            self.incumbent_shadow_ccw.appendleft(hit)

        # S-STRAT-10 v2 / S-STRAT-13 — Shadow grid: registra hit para cada
        # rotação testada (1, 3, 5, 10). Mantém legacy shadow_hits_cw/ccw
        # apontando para o shift=5 para retrocompatibilidade do dashboard.
        shadow_by_shift = pred.get("shadow_numbers_by_shift") or {}
        side_key = "cw" if direction in ("cw", "horario") else "ccw"
        for shift, sh_nums in shadow_by_shift.items():
            # BUG-A24-V2-10: JSON serializa int keys como str. Se este
            # pending_prediction veio de state.json restaurado, shift é str
            # e o lookup shadow_grid[shift] cai no except silenciosamente.
            try:
                shift_int = int(shift)
            except (TypeError, ValueError):
                continue
            sh_hit = actual_number in sh_nums
            try:
                self.shadow_grid[shift_int][side_key].appendleft(sh_hit)
            except KeyError:
                continue
            if shift_int == 5:
                if side_key == "cw":
                    self.shadow_hits_cw.appendleft(sh_hit)
                else:
                    self.shadow_hits_ccw.appendleft(sh_hit)

        # BUG-A24-V4-01: S-STRAT-13.1 EMA + sustained DEVEM atualizar por SPIN,
        # nao por scrape HTTP. Antes vivia em get_shadow_stats (chamado a cada
        # 2-15s pelo Prometheus/dashboard) → sustained chegava a 200 em ~6min
        # em vez de ~100min (200 spins reais). Suggestion prematura. Agora
        # roda 1x por spin aqui.
        self._update_shadow_ema_on_spin()
        # S-STRAT-14: bandit ε-greedy entre challengers do shadow grid.
        self._update_bandit_on_spin()
        
        # APENAS adicionar ao histórico BET se realmente apostou
        if bet_placed:
            if direction in ("cw", "horario"):
                self.performance_bet_cw.appendleft(hit)
            else:
                self.performance_bet_ccw.appendleft(hit)
        
        # Limpar predição pendente
        self.pending_prediction = {}
        
        return hit

    @staticmethod
    def _attribute_hit_region(centers: List[int], numbers: List[int],
                              actual_number: int, hit: bool) -> Dict[str, Any]:
        """B2 (12/06) — Atribui o resultado a uma região da jogada (P5).

        Atribuição por CENTRO MAIS PRÓXIMO (geometria-agnóstica): como hit=True
        implica actual ∈ numbers, o resultado pertence ao cluster cujo centro
        está mais perto (empate → C1>C2>C3). Independe de raios, então segue a
        geometria viva (V2 fat-SAT C1=1/sat=3; V3 sat 4/2) sem subcontar os
        satélites. Fallbacks (SDA-19/21, early-session) têm centers=[c1] → C1.

        Returns:
            dict com:
              slot: 'C1' | 'C2' | 'C3' | 'miss'
              dist_c1: distância circular ASSINADA result→C1 (−18..+18,
                       positivo no sentido da sequência da roda)
              dist_min: menor distância circular até qualquer centro
        """
        wheel = list(roulette.WHEEL_SEQUENCE)
        size = len(wheel)
        pos = {n: i for i, n in enumerate(wheel)}

        def _signed(frm: int, to: int) -> Optional[int]:
            if frm not in pos or to not in pos:
                return None
            d = (pos[to] - pos[frm]) % size
            return d - size if d > size // 2 else d

        out: Dict[str, Any] = {"slot": "miss", "dist_c1": None, "dist_min": None,
                               "dist_c2": None, "dist_c3": None, "numero": actual_number}
        if not centers:
            return out

        c1 = centers[0]
        out["dist_c1"] = _signed(c1, actual_number)
        # Distâncias assinadas até C2/C3 individualmente (auditoria 12/06):
        # base para adaptação por região (EMA de erro por setor) e para
        # medir se cada região está bem posicionada em relação às forças.
        if len(centers) > 1:
            out["dist_c2"] = _signed(centers[1], actual_number)
        if len(centers) > 2:
            out["dist_c3"] = _signed(centers[2], actual_number)

        dists = []
        for c in centers:
            sd = _signed(c, actual_number)
            if sd is not None:
                dists.append(abs(sd))
        if dists:
            out["dist_min"] = min(dists)

        if not hit:
            return out

        # FIX (13/06): atribuição por CENTRO MAIS PRÓXIMO, geometria-agnóstica.
        # O atribuidor antigo usava raios fixos (3,2,2 = legado 7+5+5); com a
        # geometria viva fat-SAT (C1 raio 1; satélites raio 3, ou 4/2 no V3),
        # ~2,6% dos acertos de satélite (dist 3-4) caíam em 'unattributed',
        # subcontando C2/C3 na telemetria P5/hit_region. Como hit ⇒ actual ∈
        # numbers, o resultado pertence ao cluster do centro mais próximo
        # (empate → C1>C2>C3, via '<' estrito preservando a ordem dos slots).
        best_idx: Optional[int] = None
        best_dist: Optional[int] = None
        for idx, c in enumerate(centers[:3]):
            sd = _signed(c, actual_number)
            if sd is None:
                continue
            d = abs(sd)
            if best_dist is None or d < best_dist:
                best_dist = d
                best_idx = idx
        out["slot"] = f"C{best_idx + 1}" if best_idx is not None else "C1"
        return out
    
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
        # S-STRAT-10 v2 / S-STRAT-13 — Shadow grid PARAMÉTRICO: mesmos N
        # números do incumbent rotacionados por cada shift em SHADOW_SHIFTS.
        # Testa sweep da hipótese "estratégia está off-by-N no centro?".
        shadow_by_shift: Dict[int, List[int]] = {}
        shadow_numbers: List[int] = []
        try:
            wheel = list(roulette.WHEEL_SEQUENCE)
            wheel_size = len(wheel)
            idx_map = {n: i for i, n in enumerate(wheel)}
            for shift in self.SHADOW_SHIFTS:
                rotated = [
                    wheel[(idx_map[n] + shift) % wheel_size]
                    for n in numbers if n in idx_map
                ]
                shadow_by_shift[shift] = rotated
            shadow_numbers = shadow_by_shift.get(5, [])
        except Exception:
            shadow_by_shift = {}
            shadow_numbers = []

        self.pending_prediction = {
            "numbers": numbers,
            "direction": direction,
            "center": center,
            "centers": sda_centers or [center],
            "predicted_force": predicted_force,
            "bet_placed": bet_placed,
            "tr_confidence": tr_confidence,
            "tr_reason": tr_reason,
            "sda_score": sda_score,
            "shadow_numbers": shadow_numbers,
            "shadow_numbers_by_shift": shadow_by_shift,
        }

    def _update_shadow_ema_on_spin(self) -> None:
        """S-STRAT-13.1 BUG-V4-01: atualiza EMA + sustained 1x por spin (em
        check_prediction), nao por scrape HTTP. Tambem gera/persiste a
        suggested_shift preservando flag 'applied' do humano (BUG-V4-02).
        """
        def acc(d) -> float:
            n = len(d)
            return (sum(1 for x in d if x) / n) if n else 0.0

        inc_cw_acc = acc(self.incumbent_shadow_cw)
        inc_ccw_acc = acc(self.incumbent_shadow_ccw)

        shadow_state = self._adaptive_state.setdefault("shadow_ema", {})
        alpha = 0.05
        per_shift_snapshot: Dict[str, Dict[str, Any]] = {}
        for shift in self.SHADOW_SHIFTS:
            grid = self.shadow_grid.get(shift, {})
            sd_cw_n = len(grid.get("cw", deque()))
            sd_ccw_n = len(grid.get("ccw", deque()))
            sd_cw_acc = acc(grid.get("cw", deque()))
            sd_ccw_acc = acc(grid.get("ccw", deque()))
            edge_avg_raw = ((sd_cw_acc - inc_cw_acc) + (sd_ccw_acc - inc_ccw_acc)) / 2.0
            sk = str(shift)
            ema_entry = shadow_state.setdefault(sk, {"ema": 0.0, "sustained": 0})
            ema_entry["ema"] = float(ema_entry.get("ema", 0.0)) * (1 - alpha) + edge_avg_raw * alpha
            mature = sd_cw_n >= 50 and sd_ccw_n >= 50
            if mature and ema_entry["ema"] > 0.04:
                ema_entry["sustained"] = int(ema_entry.get("sustained", 0)) + 1
            elif ema_entry["ema"] < 0.02:
                ema_entry["sustained"] = max(0, int(ema_entry.get("sustained", 0)) - 1)
            per_shift_snapshot[sk] = {
                "shift": shift,
                "edge_ema": ema_entry["ema"],
                "sustained": ema_entry["sustained"],
                "n_cw": sd_cw_n,
                "n_ccw": sd_ccw_n,
            }

        # BUG-V4-02: preservar applied flag se humano ja marcou.
        SUSTAIN_THRESHOLD = 200
        # S-STRAT-13.1 promoção automática: threshold superior + flag opt-in.
        AUTO_PROMOTE_THRESHOLD = 400
        promotable = [
            s for s in per_shift_snapshot.values()
            if s["sustained"] >= SUSTAIN_THRESHOLD
            and s["edge_ema"] > 0.04
            and s["n_cw"] >= 50 and s["n_ccw"] >= 50
        ]
        existing = self._adaptive_state.get("suggested_shift") or {}
        if promotable:
            top = max(promotable, key=lambda s: s["edge_ema"])
            # Se ja existe suggestion para o mesmo shift, preservar applied/ts.
            if existing.get("shift") == top["shift"]:
                existing["edge_ema"] = round(top["edge_ema"], 5)
                existing["sustained_spins"] = top["sustained"]
                # NAO sobrescreve 'applied' nem 'ts' originais
            else:
                # Novo shift dominante: reset suggestion.
                self._adaptive_state["suggested_shift"] = {
                    "shift": top["shift"],
                    "edge_ema": round(top["edge_ema"], 5),
                    "sustained_spins": top["sustained"],
                    "applied": False,
                    "ts": time.time(),
                }
            # S-STRAT-13.1: auto-promote (opt-in via settings.shadow_auto_promote_enabled).
            self._maybe_auto_promote_shift(top)
        # Se nao ha promotable, mantem suggestion antiga (humano pode ainda nao
        # ter aplicado). Se quiser invalidar, deve setar applied=True explicito.

    def _maybe_auto_promote_shift(self, top: Dict[str, Any]) -> None:
        """S-STRAT-13.1 — auto-promove um shift quando sustained ≥ AUTO_PROMOTE_THRESHOLD.

        Comportamento:
        - Opt-in via getattr(settings, 'shadow_auto_promote_enabled', False).
          Mantém auto-promote DESLIGADO por padrão (humano-in-the-loop).
        - Quando atinge threshold: marca suggestion.applied=True + auto_promoted=True;
          registra em _adaptive_state['auto_promotes'] (lista append, last 20);
          loga evento [SHADOW-AUTO-PROMOTE]; incrementa counter Prometheus se disponível.
        - Idempotente: se já foi auto-promovido para esse shift, no-op.
        """
        AUTO_PROMOTE_THRESHOLD = 400
        try:
            enabled = bool(getattr(settings, "shadow_auto_promote_enabled", False))
        except Exception:  # noqa: BLE001
            enabled = False
        if not enabled:
            return
        if top["sustained"] < AUTO_PROMOTE_THRESHOLD:
            return
        suggestion = self._adaptive_state.get("suggested_shift") or {}
        if suggestion.get("auto_promoted") and suggestion.get("shift") == top["shift"]:
            return  # já promovido para esse shift
        # Marca applied + auto_promoted
        suggestion["applied"] = True
        suggestion["auto_promoted"] = True
        suggestion["auto_promoted_ts"] = time.time()
        self._adaptive_state["suggested_shift"] = suggestion
        # Histórico curto
        history = self._adaptive_state.setdefault("auto_promotes", [])
        history.append({
            "shift": top["shift"],
            "edge_ema": round(top["edge_ema"], 5),
            "sustained": top["sustained"],
            "ts": time.time(),
        })
        if len(history) > 20:
            del history[: len(history) - 20]
        logger.warning(
            "[SHADOW-AUTO-PROMOTE] shift=%s edge_ema=%.4f sustained=%d",
            top["shift"], top["edge_ema"], top["sustained"],
        )
        # Counter Prometheus (defensivo — health_server pode não estar carregado em tests)
        try:
            from server import health_server as _hs
            if _hs._PROM_METRICS and "shadow_auto_promotes" in _hs._PROM_METRICS:
                _hs._PROM_METRICS["shadow_auto_promotes"].labels(shift=str(top["shift"])).inc()
        except Exception:  # noqa: BLE001
            pass

    # ---------- S-STRAT-14: bandit ε-greedy entre shifts do shadow grid ----------

    def _update_bandit_on_spin(self) -> None:
        """S-STRAT-14 — atualiza bandit ε-greedy com o último spin de cada shift.

        Para cada shift, lê o head do shadow_grid (mais recente) e contabiliza
        como reward (HIT=+1). Trata cw e ccw como observações independentes do
        mesmo braço (cada braço acumula até 2 observações por spin: 1 cw + 1 ccw).

        ε decai com volume:
          - cold-start ε=1.0 enquanto algum braço tem n<10 (exploração total).
          - ε=0.10 quando todos têm n>=10 (exploitação predominante).

        Recommendation: arg-max(mean_reward) com prob (1-ε), aleatório com prob ε.
        Não APLICA — apenas registra em `_adaptive_state.bandit.recommended_shift`
        (humano-in-the-loop, alinhado com S-STRAT-13.1).
        """
        import random as _r
        bandit = self._adaptive_state.setdefault("bandit", {
            "arms": {str(s): {"n": 0, "rewards": 0.0} for s in self.SHADOW_SHIFTS},
            "epsilon": 1.0,
            "recommended_shift": None,
            "total_pulls": 0,
        })
        # Garantia retrocompat: novos shifts entram com state vazio.
        for s in self.SHADOW_SHIFTS:
            bandit["arms"].setdefault(str(s), {"n": 0, "rewards": 0.0})

        # Cada shift consome o último resultado registrado em shadow_grid (head).
        for shift in self.SHADOW_SHIFTS:
            grid = self.shadow_grid.get(shift, {})
            for dk in ("cw", "ccw"):
                q = grid.get(dk)
                if not q:
                    continue
                # Head (most recent) — appendleft é usado, então índice 0.
                reward = 1.0 if q[0] else 0.0
                arm = bandit["arms"][str(shift)]
                arm["n"] += 1
                arm["rewards"] += reward
                bandit["total_pulls"] += 1

        # ε-schedule: cold-start até cada braço ter n>=10.
        min_n = min(a["n"] for a in bandit["arms"].values())
        if min_n < 10:
            bandit["epsilon"] = 1.0
        else:
            bandit["epsilon"] = 0.10

        # Recomendação: arg-max mean com prob 1-ε, random com prob ε.
        means = {
            sk: (a["rewards"] / a["n"]) if a["n"] > 0 else 0.0
            for sk, a in bandit["arms"].items()
        }
        eps = bandit["epsilon"]
        if _r.random() < eps:
            choice = _r.choice(list(bandit["arms"].keys()))
        else:
            choice = max(means.items(), key=lambda kv: kv[1])[0]
        try:
            bandit["recommended_shift"] = int(choice)
        except (TypeError, ValueError):
            bandit["recommended_shift"] = None
        bandit["means_snapshot"] = {sk: round(v, 4) for sk, v in means.items()}

    def get_bandit_stats(self) -> Dict[str, Any]:
        """S-STRAT-14 — snapshot do bandit para /api/strategy e métricas."""
        bandit = self._adaptive_state.get("bandit") or {}
        if not bandit:
            return {
                "design": "epsilon_greedy_v1",
                "epsilon": 1.0,
                "arms": {},
                "recommended_shift": None,
                "total_pulls": 0,
            }
        arms_out = {}
        for sk, a in bandit.get("arms", {}).items():
            n = int(a.get("n", 0))
            r = float(a.get("rewards", 0.0))
            arms_out[sk] = {
                "n": n,
                "rewards": r,
                "mean": round(r / n, 5) if n > 0 else 0.0,
            }
        return {
            "design": "epsilon_greedy_v1",
            "epsilon": float(bandit.get("epsilon", 1.0)),
            "arms": arms_out,
            "recommended_shift": bandit.get("recommended_shift"),
            "total_pulls": int(bandit.get("total_pulls", 0)),
        }

    def get_shadow_stats(self) -> Dict[str, Any]:
        """S-STRAT-13 + S-STRAT-13.1 — snapshot shadow grid + auto-suggestion.

        Read-only: apenas le o estado pre-computado em check_prediction (BUG-V4-01).
        """
        def stats(perf_deq) -> Dict[str, Any]:
            n = len(perf_deq)
            hits = sum(1 for x in perf_deq if x)
            return {"n": n, "hits": hits, "acc": (hits / n) if n else 0.0}

        # BUG-A24-V3-17: usa incumbent_shadow (maxlen=100) em vez de
        # performance_sda17 (maxlen=12) para baseline justo.
        inc_cw = stats(self.incumbent_shadow_cw)
        inc_ccw = stats(self.incumbent_shadow_ccw)

        shadow_state = self._adaptive_state.get("shadow_ema") or {}

        challengers: List[Dict[str, Any]] = []
        for shift in self.SHADOW_SHIFTS:
            grid = self.shadow_grid.get(shift, {})
            sd_cw = stats(grid.get("cw", deque()))
            sd_ccw = stats(grid.get("ccw", deque()))
            edge_cw = round((sd_cw["acc"] - inc_cw["acc"]) * 100, 1)
            edge_ccw = round((sd_ccw["acc"] - inc_ccw["acc"]) * 100, 1)

            # BUG-V4-01: EMA/sustained apenas LEITURA aqui (atualiza por spin).
            ema_entry = shadow_state.get(str(shift), {"ema": 0.0, "sustained": 0})

            # BUG-A24-V3-22: alinhar criterio do alert com champion
            # (n>=30 em ambas direcoes em vez de apenas uma).
            beats_inc = (
                sd_cw["n"] >= 30 and sd_ccw["n"] >= 30
                and (sd_cw["acc"] + sd_ccw["acc"]) / 2 > (inc_cw["acc"] + inc_ccw["acc"]) / 2
            )
            challengers.append({
                "shift": shift,
                "design": f"wheel_rotation_+{shift}",
                "cw": sd_cw,
                "ccw": sd_ccw,
                "edge_pp_cw": edge_cw,
                "edge_pp_ccw": edge_ccw,
                "edge_ema": round(float(ema_entry.get("ema", 0.0)), 5),
                "sustained_spins": int(ema_entry.get("sustained", 0)),
                "avg_acc": round((sd_cw["acc"] + sd_ccw["acc"]) / 2, 4),
                "beats_incumbent": beats_inc,
            })

        eligible = [c for c in challengers if c["cw"]["n"] >= 30 and c["ccw"]["n"] >= 30]
        champion = max(eligible, key=lambda c: c["avg_acc"], default=None)
        any_beats = any(c["beats_incumbent"] for c in challengers)

        # BUG-V4-01/V4-02: suggestion lida do _adaptive_state (escrita por spin).
        suggestion = self._adaptive_state.get("suggested_shift")

        return {
            "design": "shadow_grid_v1",
            "shifts": list(self.SHADOW_SHIFTS),
            "incumbent": {"cw": inc_cw, "ccw": inc_ccw},
            "challengers": challengers,
            "champion": {
                "shift": champion["shift"] if champion else None,
                "avg_acc": champion["avg_acc"] if champion else None,
            } if champion else {"shift": None, "avg_acc": None},
            "suggestion": suggestion,
            "baseline_random": 17.0 / 37.0,
            "alert": "shadow_beating_incumbent" if any_beats else "ok",
            # Legacy fields para retrocompatibilidade do dashboard antigo.
            "shadow": {
                "cw": next((c["cw"] for c in challengers if c["shift"] == 5), {"n": 0, "hits": 0, "acc": 0.0}),
                "ccw": next((c["ccw"] for c in challengers if c["shift"] == 5), {"n": 0, "hits": 0, "acc": 0.0}),
            },
            "edge_pp": {
                "cw": next((c["edge_pp_cw"] for c in challengers if c["shift"] == 5), 0.0),
                "ccw": next((c["edge_pp_ccw"] for c in challengers if c["shift"] == 5), 0.0),
            },
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
    
    def engine_overlay_fields(self) -> Dict[str, Any]:
        """Telemetria aditiva dos motores C1/C2 + Block-Gale, derivada do estado
        PERSISTENTE (não do handler) — fonte única para os canais que o dashboard
        consome (`trace`/`state_sync`). Espelha `c_selection`/`block_gale`/`bet_gate`
        do `sugestao` e acrescenta `ultimo_acerto` (veredito red/green do último spin).

        Aditivo e retrocompatível (Obrigação ISO #9: não remove/renomeia chaves).
        Geometria-agnóstico, sem I/O, acessos seguros (não levanta em uso normal),
        e o chamador ainda envolve em try/except defensivo.
        """
        out: Dict[str, Any] = {}
        eng = getattr(self, "block_gale_engine", None)
        if eng is not None:
            # `active` distingue o modo no ar: o engine está SEMPRE instanciado, mas
            # só é a fonte de staking quando SDA_STAKING_MODE=block_gale. Sem isto o
            # dashboard mostraria o bloco (parado) mesmo em gale/flat/kelly legado.
            from app_config.settings import staking_mode as _sm
            st_cw = eng.states["cw"]
            st_ccw = eng.states["ccw"]
            out["block_gale"] = {
                "active": _sm() == "block_gale",
                "cw": {"level": st_cw.level, "cap": st_cw.cap,
                       "block": f"{st_cw.block_bets}/{BLOCK_SIZE}", "max": st_cw.max_level_seen},
                "ccw": {"level": st_ccw.level, "cap": st_ccw.cap,
                        "block": f"{st_ccw.block_bets}/{BLOCK_SIZE}", "max": st_ccw.max_level_seen},
            }
            out["bet_gate"] = {"only_after_green": bool(eng.only_after_green)}
        # c_selection: par escolhido do spin corrente (injetado no pending_prediction).
        chosen = (self.pending_prediction or {}).get("cs_chosen")
        if chosen in ("C1", "C2"):
            out["c_selection"] = {"chosen": chosen, "pair": f"{chosen}+C3"}
        # ultimo_acerto: veredito red/green do último spin verificado (slot 'miss' = red).
        # Usa o `numero` da própria atribuição (não last_number), senão um spin sem
        # predição mostraria o número novo com o slot antigo (número/veredito incoerentes).
        attr = self.last_hit_attribution
        if isinstance(attr, dict) and attr.get("slot"):
            slot = attr["slot"]
            out["ultimo_acerto"] = {
                "slot": slot,
                "green": slot in ("C1", "C2", "C3"),
                "numero": attr.get("numero", self.last_number),
                # Sentido analisado do spin recém-resolvido (horário/anti-horário) —
                # o front marca verde/vermelho COM o sentido (pedido do operador).
                "direction": getattr(self, "last_direction", "") or "",
            }
        # force17 (C1=ForceLast + 3 regiões): telemetria do spin corrente, stashada
        # transientemente pelo handler em last_force17_meta. Aditivo/retrocompatível.
        f17 = getattr(self, "last_force17_meta", None)
        if isinstance(f17, dict) and f17.get("regioes"):
            # dir_bias: anti-horário = favorável (sentido com edge); horário = desfavorável.
            _tgt = self.target_direction
            _bias = "favoravel" if _tgt in ("ccw", "anti-horario") else "desfavoravel"
            out["force17"] = {
                "active": True,
                "regioes": f17.get("regioes", []),
                "c1_force": f17.get("c1_force"),
                "coverage_n": f17.get("coverage_n"),
                "numeros": f17.get("numeros", []),
                "dir_bias": _bias,
            }
            # V5 (04/08): modo do seletor no mesmo bloco (aditivo; ausente no
            # force17 clássico — Obrigação ISO #9 preservada).
            if f17.get("v5_mode"):
                out["force17"]["v5_mode"] = f17["v5_mode"]
            # V5.1 (05/08 tarde): telemetria spec4 no state_sync — o cherry-pick
            # acima descartava spec4/r2_delta/r3_region (só iam no trace).
            for _k in ("spec4", "r2_delta", "r3_region"):
                if f17.get(_k) is not None:
                    out["force17"][_k] = f17[_k]
            out["regioes"] = f17.get("regioes", [])
        # DIR5 (sentido-fase): bloco autoritativo da fase, publicado no state_sync (1s)
        # e no trace. O cliente sobrescreve sua paridade com next_direction; o overlay
        # mostra a fase + origem. Aditivo (clientes antigos ignoram). next_direction =
        # oposto do último processado = fase do próximo giro.
        out["sentido"] = {
            "last_seq": int(getattr(self, "spin_seq", 0) or 0),
            "last_direction": getattr(self, "last_direction", "") or "",
            "next_direction": self.target_direction,
            "locked": bool(getattr(self, "direction_locked", False)),
            "source": getattr(self, "direction_source", "") or "",
            "resync_advised": bool(getattr(self, "last_phase_uncertain", False)),
        }
        try:
            from state import phase_metrics
            out["sentido"]["stats"] = phase_metrics.snapshot()
        except Exception:  # noqa: BLE001 — observabilidade nunca quebra o overlay
            pass
        # SPR-V1 B4 (pré-requisito do SPR-V2): ECO AUTORITATIVO + capability.
        # Bloco ADITIVO publicado em state_sync/sugestao/trace — cliente antigo ignora
        # campo desconhecido. Permite ao cliente do V2 desfazer um flip local quando o
        # servidor rejeita um giro fantasma (spin_seq/direction voltam inalterados).
        # `enabled` é NOMINAL e DINÂMICO (capability, lida POR CHAMADA): anuncia que o
        # par de flags do servidor está no ar. `direction`/`seed_parity` vêm NULL quando
        # não há âncora válida — sem âncora não há autoridade a espelhar.
        try:
            from app_config.settings import (
                sentido_autoritativo_enabled as _sae,
                phase_buffer_sync_enabled as _pbs,
            )
            from state.phase import project_phase as _pp, HORARIO as _H, VALID as _V
            _seq = int(getattr(self, "spin_seq", 0) or 0)
            _sp = getattr(self, "seed_parity", "") or ""
            _tem_ancora = _sp in _V
            # spin_seq já foi incrementado pelo último giro ⇒ é o índice do PRÓXIMO.
            _next = _pp(_sp, getattr(self, "seed_n", 0), _seq) if _tem_ancora else ""
            out["phase_authority"] = {
                "enabled": bool(_sae() and _pbs()),
                "spin_seq": _seq,
                "direction": ("cw" if _next == _H else "ccw") if _tem_ancora else None,
                "seed_parity": (0 if _sp == _H else 1) if _tem_ancora else None,
                "seed_n": int(getattr(self, "seed_n", 0) or 0) if _tem_ancora else None,
            }
        except Exception:  # noqa: BLE001 — eco é observabilidade; nunca quebra o overlay
            pass
        # DIR10 (sentido-fase): publica timeline rica (numero+seq+direction) para
        # auditoria externa (dashboards, debug offline). Default N=12; 0 desativa.
        # Ring buffer SEPARADO de recent_results (zona fria C3) — sem impacto SDA17.
        try:
            from app_config.settings import overlay_ultimos_n as _on
            _n = _on()
            if _n > 0:
                _ring = list(getattr(self, "_phase_overlay_ring", []) or [])
                out["ultimos"] = _ring[:_n]
        except Exception:  # noqa: BLE001
            pass
        return out

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
        # S-STRAT-11: direção alvo (oposta à última) para threshold dinâmico isolado.
        target_dir = "ccw" if self.last_direction == "horario" else "cw"
        return self.bet_advisor.analyze(
            self.target_performance, sda_score=sda_score, direction=target_dir
        )

    # ==================================================================== #
    # v4.4 Quick Wins INV-3 — Stake modulation                              #
    #                                                                      #
    # Estes métodos NÃO alteram should_bet/acao. Apenas ajustam o VALOR     #
    # exibido (`current_bet`) preservando martingale e Triple Rate.         #
    # ==================================================================== #
    def get_effective_bet(self, direction: str, strategy, n_numbers: int = 21) -> Dict[str, Any]:
        """
        QW-1 (Stake Minimizer) + QW-2 (Stake Weight) — calcula valor de aposta
        efetivo aplicando modulações em cima de `current_bet`.

        Args:
            direction: "cw"/"horario"/"ccw"/"anti-horario" (target direction).
            strategy: instância de SDA17Strategy (exposta via message_handler).
            n_numbers: nº de números apostados (geometria viva) — usado pelos
                modos flat/kelly (stake = U·N). Ignorado no modo gale.

        Returns:
            dict com {
                "effective_bet":  int,   # valor a exibir no overlay
                "base_bet":       int,   # current_bet do martingale (sem modulação)
                "multiplier":     float, # 0.0..1.5 efetivamente aplicado
                "mode":           str,   # "minimizer" | "weight" | "normal" | "mg_escalated"
                "rolling_rate":   float | None,
                "minimizer_active": bool,
            }
        """
        # S-STAKE (flat_kelly_junho.md §6.2) — dispatcher de staking. Em flat/kelly
        # delega para staking.policy e retorna ANTES do bloco QW (RN-6). No modo
        # gale (default) o ramo é pulado e o código abaixo roda inalterado
        # (byte-idêntico — rollback trivial via SDA_STAKING_MODE=gale). Um único
        # except (fail-safe): qualquer falha de staking → cai no gale legado.
        try:
            from app_config.settings import staking_mode as _staking_mode
            _mode = _staking_mode()
            if _mode in ("flat", "kelly"):
                from staking.policy import compute_staking
                return compute_staking(
                    _mode, direction=direction, n_numbers=n_numbers, strategy=strategy
                )
        except Exception as _stk_e:  # noqa: BLE001 — staking nunca quebra a aposta
            logger.warning(f"[STAKE] dispatcher falhou ({_stk_e}) — fallback gale legado")

        mg = self.martingale_cw if direction in ("cw", "horario") else self.martingale_ccw
        base_bet = mg.current_bet
        result = {
            "effective_bet": base_bet,
            "base_bet": base_bet,
            "multiplier": 1.0,
            "mode": "normal",
            "rolling_rate": None,
            "minimizer_active": False,
        }

        # Helper opcional: se strategy não expõe os métodos QW (compat ascendente)
        # retorna base sem modulação.
        if not hasattr(strategy, "should_minimize") or not hasattr(strategy, "get_stake_weight"):
            return result

        try:
            minimize, rate = strategy.should_minimize(direction)
        except Exception as e:
            logger.warning(f"[QW-1] should_minimize falhou ({e}) — usando base")
            return result
        result["rolling_rate"] = rate

        if minimize:
            # QW-1: força level=1 + stake mínimo. Aposta CONTINUA (INV-3).
            try:
                if mg.level != 1:
                    # Reset implícito: conta para métrica QW-3
                    if hasattr(strategy, "record_mg_reset"):
                        strategy.record_mg_reset(direction)
                    mg.level = 1
                    mg.consecutive_hits = 0
                frac = float(strategy._cfg.get("sda17.minimizer", "stake_fraction", 0.10))
            except Exception:
                frac = 0.10
            # Garante valor mínimo inteiro >= 1 (estética overlay)
            effective = max(1, int(round(base_bet * frac)))
            result.update({
                "effective_bet": effective,
                "multiplier": frac,
                "mode": "minimizer",
                "minimizer_active": True,
            })
            return result

        # QW-2: weight só quando level=1 (não amplifica em escalação).
        if mg.level == 1:
            try:
                w = float(strategy.get_stake_weight(direction))
            except Exception:
                w = 1.0
            if abs(w - 1.0) > 1e-9:
                effective = max(1, int(round(base_bet * w)))
                result.update({
                    "effective_bet": effective,
                    "multiplier": w,
                    "mode": "weight",
                })
                return result
            return result

        # Mantém base em escalação (sem amplificar drawdown).
        result["mode"] = "mg_escalated"
        return result

    @staticmethod
    def _fsync_dir(dir_path: Path) -> None:
        """C2/A23: fsync do diretório torna o rename durável (POSIX). No-op no Windows."""
        if os.name != "posix":
            return
        try:
            dir_fd = os.open(str(dir_path), os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(dir_fd)
        except OSError:
            pass
        finally:
            os.close(dir_fd)

    def save(self, path: Optional[Path] = None) -> None:
        """Salva estado em arquivo JSON (v2.0 - S-STRAT-13.1 EMA+suggestion) com escrita atômica."""
        import os
        import tempfile
        
        path = path or settings.state_file
        # BUG-A24-01: serializa shadow_grid (keys int → str para JSON).
        shadow_grid_serializable = {
            str(shift): {
                "cw": list(sides.get("cw", [])),
                "ccw": list(sides.get("ccw", [])),
            }
            for shift, sides in (self.shadow_grid or {}).items()
        }
        data = {
            "version": "2.0.0",
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
            "pending_prediction": self.pending_prediction,
            "adaptive_state": self._adaptive_state,
            "bet_advisor_state": self.bet_advisor.state_dict(),
            # S-STRAT-13 persistence (BUG-A24-01)
            "shadow_hits_cw": list(self.shadow_hits_cw),
            "shadow_hits_ccw": list(self.shadow_hits_ccw),
            "shadow_grid": shadow_grid_serializable,
            # BUG-A24-V3-17: persistir incumbent_shadow paralelo
            "incumbent_shadow_cw": list(self.incumbent_shadow_cw),
            "incumbent_shadow_ccw": list(self.incumbent_shadow_ccw),
            # V4 (13/06): janela de resultados para a zona fria de C3.
            "recent_results": list(self.recent_results),
            # DIR3 (sentido-fase): contador de giros + âncora de fase + origem/lock.
            "spin_seq": self.spin_seq,
            "seed_parity": self.seed_parity,
            "seed_n": self.seed_n,
            "direction_source": self.direction_source,
            "direction_locked": self.direction_locked,
            # DIR10: ring overlay rico (numero+seq+direction). Round-trip preserva
            # historico recente atraves de restarts (cliente nao perde timeline).
            "_phase_overlay_ring": list(self._phase_overlay_ring),
            # DIR19: buffer dedicado para shift (janela 20).
            "_phase_results": list(self._phase_results),
            # V5.1 sig4 (05/08): placar das 6 regiões fixas (round-trip).
            "region6_counts": list(self.region6_counts),
            # Implantação C1/C2 + Block-Gale (17/06): estado dos motores (gated por flag).
            "c_selection": self.c_selection_engine.state_dict(),
            "block_gale": self.block_gale_engine.state_dict(),
            "c_attr_cw": list(self.c_attr_cw),
            "c_attr_ccw": list(self.c_attr_ccw),
        }
        
        # Escrita atômica + durável (C2/A23): flush+fsync do temp antes do replace e
        # fsync do diretório depois, para o estado sobreviver a queda de energia entre
        # o rename e o writeback do page-cache (senão o os.replace atômico pode deixar
        # um state.json truncado/zerado após crash).
        dir_path = Path(path).parent
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tmp', 
                                          dir=dir_path, delete=False, 
                                          encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
            temp_path = f.name
        
        try:
            os.replace(temp_path, path)
            self._fsync_dir(dir_path)
        except OSError:
            try:
                with open(path, 'w', encoding='utf-8') as target:
                    with open(temp_path, 'r', encoding='utf-8') as source:
                        target.write(source.read())
                    target.flush()
                    os.fsync(target.fileno())
                self._fsync_dir(dir_path)
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
        - v1.5 -> v1.6: adiciona adaptive_state (vazio se não existe, populado durante operação)
        """
        path = path or settings.state_file
        if not path.exists():
            if os.environ.get("STATE_FILE") and path == settings.state_file:
                raise FileNotFoundError(
                    f"STATE_FILE configurado, mas o estado persistente nao existe: {path}"
                )
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
            
            # v1.4+ / v1.5+ / v1.6+ - formato atual
            gs = cls(
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
            # M15-ADA: Restaurar estado adaptativo (v1.6+, vazio se v1.5)
            gs._adaptive_state = data.get("adaptive_state", {})
            # V4 (13/06): restaurar janela de resultados (compat: vazio se ausente)
            gs.recent_results = deque(data.get("recent_results", []), maxlen=10)
            # DIR3 (sentido-fase): restaurar contador/âncora (compat: defaults se ausente)
            gs.spin_seq = int(data.get("spin_seq", 0) or 0)
            gs.seed_parity = data.get("seed_parity", "") or ""
            gs.seed_n = int(data.get("seed_n", 0) or 0)
            gs.direction_source = data.get("direction_source", "") or ""
            gs.direction_locked = bool(data.get("direction_locked", False))
            # DIR10: round-trip do ring overlay. Default vazio se ausente (backward compat).
            try:
                _ring_data = data.get("_phase_overlay_ring", []) or []
                gs._phase_overlay_ring = deque(_ring_data, maxlen=12)
            except Exception:  # noqa: BLE001
                gs._phase_overlay_ring = deque(maxlen=12)
            # DIR19: round-trip do buffer de fase.
            try:
                _phase_data = data.get("_phase_results", []) or []
                gs._phase_results = deque(_phase_data, maxlen=20)
            except Exception:  # noqa: BLE001
                gs._phase_results = deque(maxlen=20)
            # V5.1 sig4: round-trip do placar (compat: [0]*6 se ausente/corrompido).
            try:
                _r6 = data.get("region6_counts", []) or []
                _r6 = [int(c) for c in _r6][:6]
                gs.region6_counts = _r6 + [0] * (6 - len(_r6))
            except Exception:  # noqa: BLE001 — estado legado não pode travar boot
                gs.region6_counts = [0] * 6
            # S-OBS-7: restaurar counter do Kill Switch (sobrevive restarts)
            try:
                gs.bet_advisor.load_state(data.get("bet_advisor_state", {}))
            except Exception as _e:
                logger.warning(f"S-OBS-7: falha ao restaurar bet_advisor_state: {_e}")
            # S-STRAT-13 / BUG-A24-01: restaurar shadow grid (keys str → int).
            try:
                sh_cw = data.get("shadow_hits_cw", [])
                sh_ccw = data.get("shadow_hits_ccw", [])
                gs.shadow_hits_cw = deque(sh_cw, maxlen=100)
                gs.shadow_hits_ccw = deque(sh_ccw, maxlen=100)
                sg_raw = data.get("shadow_grid", {}) or {}
                for shift_key, sides in sg_raw.items():
                    try:
                        shift_int = int(shift_key)
                    except (TypeError, ValueError):
                        continue
                    if shift_int in gs.shadow_grid:
                        gs.shadow_grid[shift_int]["cw"] = deque(sides.get("cw", []), maxlen=100)
                        gs.shadow_grid[shift_int]["ccw"] = deque(sides.get("ccw", []), maxlen=100)
                # BUG-A24-V3-17: restaurar incumbent_shadow (compat: vazio se ausente)
                gs.incumbent_shadow_cw = deque(data.get("incumbent_shadow_cw", []), maxlen=100)
                gs.incumbent_shadow_ccw = deque(data.get("incumbent_shadow_ccw", []), maxlen=100)
            except Exception as _e:
                logger.warning(f"S-STRAT-13: falha ao restaurar shadow_grid: {_e}")
            # Implantação C1/C2 + Block-Gale (17/06): rehidratar motores (compat: ausente => default).
            try:
                gs.c_selection_engine.load_state(data.get("c_selection", {}))
                gs.block_gale_engine.load_state(data.get("block_gale", {}))
                gs.c_attr_cw = deque(data.get("c_attr_cw", []), maxlen=12)
                gs.c_attr_ccw = deque(data.get("c_attr_ccw", []), maxlen=12)
            except Exception as _e:
                logger.warning(f"IMPL C1C2/gale: falha ao restaurar motores: {_e}")
            return gs
        except Exception as e:
            logger.error(f"Falha ao carregar state.json: {e}")
            backup = Path(str(path) + '.corrupted')
            try:
                import shutil
                shutil.copy2(path, backup)
                logger.info(f"Backup do state corrompido salvo em: {backup}")
            except Exception:  # noqa: BLE001 — backup é best-effort
                pass
            # C1/A19: em produção (STATE_FILE definido) NÃO reinicia silenciosamente
            # com estado vazio — isso apagaria timeline/fase/martingale acumulados e
            # o motor voltaria a apostar do zero sem ninguém perceber. Falha fechado
            # para o preflight/deploy barrar; o operador restaura o backup .corrupted.
            if os.environ.get("STATE_FILE") and path == settings.state_file:
                raise RuntimeError(
                    f"state.json corrompido em producao: {path}; "
                    f"backup salvo em {backup}. Restaure/valide antes de subir."
                ) from e
            return cls()
