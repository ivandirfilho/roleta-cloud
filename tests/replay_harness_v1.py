"""SPR-V1 — harness determinístico de replay (não-interferência).

Roda uma lista FIXA de giros pelo `MessageHandler.handle_new_result` real, com DB
SQLite temporário e broadcast mockado, e devolve um dict serializável com os campos
que a DoD exige comparar antes × depois:
`final_action`, cobertura (`sda_numbers`/`sda_centers`), stake (`gale_bet_value`),
`timeline_cw`/`timeline_ccw`, `seed_parity`, `seed_n`, `spin_seq`, `decisions`.

Sem `random`, sem relógio real na comparação (timestamps do cliente são fixos e os
campos de tempo do servidor NÃO entram no snapshot).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Giros congelados: 24 eventos, alternância cw/ccw, números fixos (sem random).
SPINS: List[int] = [
    17, 32, 5, 21, 0, 26, 3, 12, 28, 7, 29, 18,
    22, 9, 31, 14, 20, 1, 33, 16, 24, 10, 8, 30,
]
# Índices de SPINS que o cliente REALMENTE envia. Os ausentes simulam um blackout
# do cliente (minimizado) — chegam só dentro de `allNumbers`, exercitando o caminho
# de gap do DIR4 (reconcile_shift/phase_advance) no replay.
SKIPPED: List[int] = [8, 9, 17]
ALL_NUMBERS_WINDOW = 12
T0_MS = 1_700_000_000_000
STEP_MS = 45_000

# Flags de PRODUÇÃO relevantes para o caminho de fase (as do sprint ficam OFF).
PROD_ENV = {
    "SDA_HISTORICO_NAO_DIRECIONAL": "1",
    "SDA_SENTIDO_AUTORITATIVO": "1",
    "SDA_PHASE_RECONCILE": "1",
    "SDA_DEDUP_SEQ": "1",
    "SDA_RESET_REANCORA": "1",
    "SDA_UNCERTAIN_REANCORA": "1",
    "SDA_SENTIDO_AUTORITATIVO_SHADOW": "1",
    "SDA_LOCK_TOTAL": "1",
    "SDA_DIRECTION_VISION": "0",
    "PROFIT_CUT_V1": "0",
    "PROFIT_STOP_LOSS_UNITS": "0",
    # Flags do MOTOR que o `tests/conftest.py` fixa por `setdefault`. Precisam estar
    # explícitas aqui para o replay dar o MESMO resultado dentro e fora do pytest
    # (senão a fixture congelada e a execução na suíte divergiriam por ambiente,
    # não por código — falso positivo de interferência).
    "REGION_SHIFT_V1": "0",
    "SDA_SIGMOID_SATELLITES": "1",
    "SDA_GEOMETRY_V2": "0",
    # Flags NOVAS do SPR-V1 — todas OFF (é exatamente o que a DoD exige).
    "SDA_PHASE_BUFFER_SYNC": "0",
    "SDA_PHASE_MIN_OVERLAP": "0",
    "SDA_MIN_SPIN_INTERVAL_MS": "0",
    "SDA_PHASE_ALT_METRIC": "0",
}


class _FakeWS:
    def __init__(self) -> None:
        self.sent: List[str] = []

    async def send(self, message: str) -> None:
        self.sent.append(message)


def _decision_row(decision: Any) -> Dict[str, Any]:
    """Linha determinística de `decisions` (sem timestamps/ids voláteis)."""
    return {
        "spin_number": decision.spin_number,
        "spin_direction": decision.spin_direction,
        "spin_force": decision.spin_force,
        "final_action": decision.final_action,
        "action_reason": decision.action_reason,
        "sda_should_bet": decision.sda_should_bet,
        "sda_score": decision.sda_score,
        "sda_center": decision.sda_center,
        "sda_centers": list(decision.sda_centers or []),
        "sda_numbers": list(decision.sda_numbers or []),
        "sda_offset": decision.sda_offset,
        "sda_offset_type": decision.sda_offset_type,
        "gale_level": decision.gale_level,
        "gale_bet_value": decision.gale_bet_value,
        "tr_should_bet": decision.tr_should_bet,
        "tr_reason": decision.tr_reason,
        "spin_seq": decision.spin_seq,
        "direction_next": decision.direction_next,
        "phase_uncertain": decision.phase_uncertain,
    }


def run_replay() -> Dict[str, Any]:
    """Executa o replay e devolve o snapshot comparável."""
    import database
    from app_config.settings import settings
    from state.game import GameState
    from strategies.sda17 import SDA17Strategy
    from server import message_handler as mh_mod
    from server.message_handler import MessageHandler

    tmp = tempfile.mkdtemp(prefix="sprv1-replay-")
    database.init_database(str(Path(tmp) / "decisions.db"))
    # Nunca escrever no state.json do repositório durante o replay.
    settings.state_file = Path(tmp) / "state.json"

    game_state = GameState()
    strategy = SDA17Strategy()
    handler = MessageHandler(
        game_state=game_state,
        strategy=strategy,
        state_lock=asyncio.Lock(),
        configs_path=str(Path(tmp) / "configs"),
    )

    captured: List[Dict[str, Any]] = []

    real_save = mh_mod.db_service.save_decision
    counter = {"n": 0}

    def _save_decision(decision):
        captured.append(_decision_row(decision))
        counter["n"] += 1
        return counter["n"]

    mh_mod.db_service.save_decision = _save_decision

    real_broadcast = mh_mod.connection_manager.broadcast
    real_get_role = mh_mod.connection_manager.get_role
    mh_mod.connection_manager.broadcast = MagicMock(
        side_effect=lambda *a, **k: asyncio.sleep(0)
    )
    mh_mod.connection_manager.get_role = lambda conn_id: "master"

    try:
        ws = _FakeWS()
        for i, numero in enumerate(SPINS):
            if i in SKIPPED:
                continue
            direcao = "horario" if i % 2 == 0 else "anti-horario"
            all_numbers = list(reversed(SPINS[max(0, i - ALL_NUMBERS_WINDOW + 1): i + 1]))
            data = {
                "type": "novo_resultado",
                "numero": numero,
                "direcao": direcao,
                "timestamp": T0_MS + i * STEP_MS,
                "t_client": T0_MS + i * STEP_MS,
                "trace_id": f"replay-{i:03d}",
                "allNumbers": all_numbers,
            }
            # Caminho REAL de entrada: process_message (role gate + dedup + dispatch).
            asyncio.run(handler.process_message(ws, json.dumps(data), "conn-replay"))
    finally:
        mh_mod.db_service.save_decision = real_save
        mh_mod.connection_manager.broadcast = real_broadcast
        mh_mod.connection_manager.get_role = real_get_role

    errors = [m for m in ws.sent if '"type": "error"' in m or '"type":"error"' in m]

    return {
        "spin_seq": game_state.spin_seq,
        "seed_parity": game_state.seed_parity,
        "seed_n": game_state.seed_n,
        "direction_source": game_state.direction_source,
        "direction_locked": game_state.direction_locked,
        "last_direction": game_state.last_direction,
        "last_number": game_state.last_number,
        "target_direction": game_state.target_direction,
        "timeline_cw": list(game_state.timeline_cw.forces),
        "timeline_ccw": list(game_state.timeline_ccw.forces),
        "recent_results": list(game_state.recent_results),
        "phase_results": list(getattr(game_state, "_phase_results", [])),
        "ws_errors": len(errors),
        "decisions": captured,
    }


def main() -> None:
    for k, v in PROD_ENV.items():
        os.environ[k] = v
    snap = run_replay()
    out = Path(__file__).parent / "fixtures" / "spr_v1_replay_baseline.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"fixture escrita: {out}")


if __name__ == "__main__":
    main()
