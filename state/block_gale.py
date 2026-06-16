"""Block-Gale isolado por sentido (implantação C1/C2 variável + Gale — 16/06/2026).

Gale em **blocos de 4 apostas COLOCADAS** por sentido, critério "2 de 4":
- >=2 vitórias no bloco  -> reset/permanece em G1
- <=1 vitória            -> sobe um nível (G1->G2->G3->G4) até o `cap`
- no teto (`level == cap`) e falha -> reinicia em G1 e aceita o loss

Stake por nível: x1 / x2 / x4 / x8. **Isolado por sentido** (dois estados).

Correções incorporadas da auditoria de design (implantação_c_variavel_gale_junho.md §10):
- B2: o bloco só conta apostas com ``placed=True`` (stake real). ``last_green`` é
  atualizado em TODA jogada (sombra), mesmo sem aposta.
- B1: "só após green" é um **stake-gate** (não supressão) — quem decide a indicação
  é o caller (INV-3); aqui apenas sinalizamos ``place=False`` quando *gated*.
- B6/B14: **trava de solvência** — nunca devolve ``place=True`` se o stake total
  excede a banca viva (produção não aposta a descoberto).
- B7: ``state_dict``/``load_state`` serializáveis (sem deques).
- B8: ``reset`` para troca de dealer/mesa.

Stateless quanto a I/O; todo o estado vive em memória e é serializado pelo caller
(em ``state.json::adaptive_state['block_gale']``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

# Multiplicador de stake por nível de gale.
MULT: Dict[int, int] = {1: 1, 2: 2, 3: 4, 4: 8}
BLOCK_SIZE: int = 4
WIN_THRESHOLD: int = 2  # >=2 de 4 -> reset/permanece G1


def _dk(direction: str) -> str:
    """Normaliza direção para 'cw' | 'ccw' (aceita 'horario'/'anti-horario')."""
    return "cw" if direction in ("cw", "horario") else "ccw"


def _clamp_cap(cap: int) -> int:
    try:
        return min(4, max(1, int(cap)))
    except (TypeError, ValueError):
        return 1


@dataclass
class BlockGaleState:
    """Estado do gale de UM sentido."""
    direction: str
    level: int = 1
    cap: int = 1
    block_bets: int = 0          # apostas COLOCADAS no bloco corrente (0..4)
    block_wins: int = 0
    last_green: Optional[bool] = None
    max_level_seen: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction,
            "level": self.level,
            "cap": self.cap,
            "block_bets": self.block_bets,
            "block_wins": self.block_wins,
            "last_green": self.last_green,
            "max_level_seen": self.max_level_seen,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any], direction: str) -> "BlockGaleState":
        d = d or {}
        cap = _clamp_cap(d.get("cap", 1))
        try:
            level = min(4, max(1, int(d.get("level", 1) or 1)))  # issue#3: clamp p/ dominio de MULT
        except (TypeError, ValueError):
            level = 1
        return cls(
            direction=direction,
            level=level,
            cap=cap,
            block_bets=int(d.get("block_bets", 0) or 0),
            block_wins=int(d.get("block_wins", 0) or 0),
            last_green=d.get("last_green", None),
            max_level_seen=int(d.get("max_level_seen", 1) or 1),
        )


class BlockGaleEngine:
    """Gerencia os dois `BlockGaleState` (cw/ccw) de forma independente."""

    def __init__(
        self,
        base_unit: float = 1.0,
        caps: Optional[Dict[str, int]] = None,
        only_after_green: bool = False,
    ) -> None:
        self.base_unit = float(base_unit)
        self.only_after_green = bool(only_after_green)
        caps = caps or {}
        self.states: Dict[str, BlockGaleState] = {
            "cw": BlockGaleState("cw", cap=_clamp_cap(caps.get("cw", 1))),
            "ccw": BlockGaleState("ccw", cap=_clamp_cap(caps.get("ccw", 1))),
        }

    # ---- configuração ----
    def set_cap(self, direction: str, cap: int) -> None:
        self.states[_dk(direction)].cap = _clamp_cap(cap)

    def set_base_unit(self, base_unit: float) -> None:
        self.base_unit = max(0.0, float(base_unit))

    # ---- consultas ----
    def stake(self, direction: str, n_numbers: int) -> float:
        """Stake TOTAL arriscado (base_unit por número × N × multiplicador)."""
        st = self.states[_dk(direction)]
        return self.base_unit * float(max(0, n_numbers)) * float(MULT[st.level])

    def expected_pnl(self, direction: str, n_numbers: int, green: bool) -> float:
        """P&L do bet ao nível atual (telemetria/teste). 1 número paga 36×stake."""
        st = self.states[_dk(direction)]
        mult = MULT[st.level]
        if green:
            return self.base_unit * mult * (36.0 - float(n_numbers))
        return -self.base_unit * mult * float(n_numbers)

    def decide(self, direction: str, bankroll: float, n_numbers: int) -> Dict[str, Any]:
        """Decide se coloca aposta (real) e com qual stake/nível.

        Returns dict: place, stake, level, cap, mult, gated, solvent.
        - ``gated``  = bloqueado pelo "só após green" (última não foi green).
        - ``solvent``= stake cabe na banca (senão NÃO aposta — sem descoberto).
        """
        st = self.states[_dk(direction)]
        stake_total = self.stake(direction, n_numbers)
        gated = self.only_after_green and (st.last_green is not True)
        solvent = stake_total <= float(bankroll) and stake_total > 0.0
        place = (not gated) and solvent
        return {
            "place": place,
            "stake": stake_total if place else 0.0,
            "level": st.level,
            "cap": st.cap,
            "mult": MULT[st.level],
            "gated": gated,
            "solvent": solvent,
        }

    # ---- atualização ----
    def on_result(self, direction: str, green: bool, placed: bool) -> Dict[str, Any]:
        """Resolve a jogada. SEMPRE atualiza `last_green`. Conta o bloco só se `placed`.

        Returns dict: level_before, level_after, transition, block_bets, block_wins.
        transition ∈ {None, 'reset', 'escalate', 'cap_reset'} (no fechamento do bloco).
        """
        st = self.states[_dk(direction)]
        st.last_green = bool(green)  # sombra de toda jogada (B2)
        level_before = st.level
        transition: Optional[str] = None

        if placed:
            st.block_bets += 1
            if green:
                st.block_wins += 1
            if st.block_bets >= BLOCK_SIZE:
                if st.block_wins >= WIN_THRESHOLD:
                    st.level = 1
                    transition = "reset"
                elif st.level >= st.cap:
                    st.level = 1
                    transition = "cap_reset"  # falhou no teto: reinicia, aceita loss
                else:
                    st.level += 1
                    transition = "escalate"
                st.block_bets = 0
                st.block_wins = 0
            st.max_level_seen = max(st.max_level_seen, level_before, st.level)

        return {
            "level_before": level_before,
            "level_after": st.level,
            "transition": transition,
            "block_bets": st.block_bets,
            "block_wins": st.block_wins,
            "max_level_seen": st.max_level_seen,
        }

    # ---- reset / persistência ----
    def reset(self, direction: Optional[str] = None) -> None:
        """Reseta um sentido (ou ambos) — troca de dealer/mesa (B8)."""
        keys = [_dk(direction)] if direction else ["cw", "ccw"]
        for k in keys:
            cap = self.states[k].cap
            self.states[k] = BlockGaleState(k, cap=cap)

    def state_dict(self) -> Dict[str, Any]:
        return {
            "base_unit": self.base_unit,
            "only_after_green": self.only_after_green,
            "cw": self.states["cw"].to_dict(),
            "ccw": self.states["ccw"].to_dict(),
        }

    def load_state(self, d: Dict[str, Any]) -> None:
        if not d:
            return
        self.base_unit = float(d.get("base_unit", self.base_unit))
        self.only_after_green = bool(d.get("only_after_green", self.only_after_green))
        self.states["cw"] = BlockGaleState.from_dict(d.get("cw"), "cw")
        self.states["ccw"] = BlockGaleState.from_dict(d.get("ccw"), "ccw")
