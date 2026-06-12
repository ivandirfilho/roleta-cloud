"""Auditoria 12/06 (2ª rodada) — feedback adaptativo alinhado à aposta real.

BUG-A: center=0 pulava update_adaptive (`if c1_predicted > 0`) — zero é
       número válido da roleta.
BUG-B: _pct_sigmoid_update recalculava a cobertura com offsets efetivos —
       no fallback N=19/21 o is_hit do aprendizado divergia do hit real.
BUG-L: stop-loss lia session_pnl ANTES do update_result da decisão
       recém-resolvida → gate com 1 spin de atraso.
MELHORIA-G: EMA do erro circular assinado por região/sentido (telemetria).
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from core.roulette import roulette
from models.trace import TraceContext
from state.game import GameState
from strategies.sda17 import SDA17Strategy

WHEEL = list(roulette.WHEEL_SEQUENCE)
SIZE = len(WHEEL)


def _at(center: int, offset: int) -> int:
    return WHEEL[(WHEEL.index(center) + offset) % SIZE]


class TestBugACenterZeroFeedback(unittest.TestCase):
    """BUG-A: predição com C1=0 DEVE alimentar o adaptativo."""

    def test_update_adaptive_accepts_center_zero(self):
        s = SDA17Strategy()
        before = len(s.cw_history)
        s.update_adaptive("cw", 0, 15, WHEEL)  # c1 = ZERO
        self.assertEqual(len(s.cw_history), before + 1)
        self.assertEqual(len(s._recent_hits["cw"]), 1)


class TestBugBFeedbackUsesRealBet(unittest.TestCase):
    """BUG-B: is_hit/min_dist do feedback = aposta REAL (não recalculada)."""

    def test_fallback_n21_hit_is_learned_as_hit(self):
        """Resultado a 9 casas do centro: HIT na aposta N=21, mas fora da
        cobertura 17 recalculada — o feedback deve aprender HIT."""
        s = SDA17Strategy()
        c1 = 0
        coverage = sorted(roulette.get_neighbors(c1, 10))  # N=21 real
        actual = _at(c1, 9)  # dentro de N=21; fora de C1±3 e de C2/C3 (±10±2 → 8..12... 9 NÃO: 9 está em c2_nbrs?)
        # offsets default 10 → c2 = +10, raio 2 → posições +8..+12 INCLUI +9.
        # Para isolar de verdade, use coverage explícita SEM o actual... então
        # o teste certo é o inverso: actual DENTRO da aposta real e FORA da
        # cobertura recalculada. Com defaults, recalculada cobre ±3, +8..+12,
        # -8..-12. Posições fora: ±4..±7, ±13..±18. Aposta N=21 cobre ±10.
        actual = _at(c1, 5)  # posição +5: fora da recalculada, dentro de N=21
        s.update_adaptive("cw", c1, actual, WHEEL,
                          coverage=coverage, centers=[c1])
        self.assertEqual(s._recent_hits["cw"], [1],
                         "hit real da aposta N=21 deve ser aprendido como HIT")

    def test_without_kwargs_keeps_legacy_behavior(self):
        """Sem coverage/centers, posição +5 está FORA da cobertura padrão."""
        s = SDA17Strategy()
        c1 = 0
        actual = _at(c1, 5)
        s.update_adaptive("cw", c1, actual, WHEEL)
        self.assertEqual(s._recent_hits["cw"], [0])

    def test_real_centers_drive_cooldown_attribution(self):
        """QW-4: hit em C2 REAL (passado por kwargs) marca cooldown de c2."""
        s = SDA17Strategy()
        c1 = 0
        c2 = _at(c1, 10)
        c3 = _at(c1, -10)
        cov = set(roulette.get_neighbors(c1, 3))
        cov |= set(roulette.get_neighbors(c2, 2))
        cov |= set(roulette.get_neighbors(c3, 2))
        actual = _at(c2, 1)  # hit em C2, fora de C1
        s.update_adaptive("cw", c1, actual, WHEEL,
                          coverage=sorted(cov), centers=[c1, c2, c3])
        self.assertGreater(s._cooldown["cw"]["c2"], 0)


class TestMelhoriaGRegionErrEma(unittest.TestCase):
    """MELHORIA-G: EMA do erro assinado por região/sentido (telemetria)."""

    def test_ema_populates_per_region_and_direction(self):
        s = SDA17Strategy()
        c1 = 0
        c2, c3 = _at(c1, 10), _at(c1, -10)
        actual = _at(c1, 2)  # +2 de C1; -8 de C2; +12 de C3
        s.update_adaptive("cw", c1, actual, WHEEL,
                          coverage=sorted(roulette.get_neighbors(c1, 3)),
                          centers=[c1, c2, c3])
        snap = s.get_region_err_snapshot()
        self.assertEqual(snap["cw"]["c1"], 2.0)
        self.assertEqual(snap["cw"]["c2"], -8.0)
        self.assertEqual(snap["cw"]["c3"], 12.0)
        self.assertIsNone(snap["ccw"]["c1"], "INV-1: ccw intocado")

    def test_ema_smooths_and_resets(self):
        s = SDA17Strategy()
        c1 = 0
        centers = [c1, _at(c1, 10), _at(c1, -10)]
        cov = sorted(roulette.get_neighbors(c1, 3))
        s.update_adaptive("ccw", c1, _at(c1, 4), WHEEL, coverage=cov, centers=centers)
        s.update_adaptive("ccw", c1, _at(c1, -4), WHEEL, coverage=cov, centers=centers)
        # EMA(alpha=.2): 4.0 → 0.8*4 + 0.2*(-4) = 2.4
        self.assertAlmostEqual(s._region_err_ema["ccw"]["c1"], 2.4, places=6)
        # Persistência roundtrip
        s2 = SDA17Strategy()
        s2.load_adaptive_state(s.get_adaptive_state())
        self.assertAlmostEqual(s2._region_err_ema["ccw"]["c1"], 2.4, places=6)
        # Reset (B1) zera
        s.reset_adaptive()
        self.assertIsNone(s._region_err_ema["ccw"]["c1"])


class _MockWS:
    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)


def _async_none():
    async def _noop(*a, **k):
        return None
    return _noop()


class TestBugLStopLossNoLag(unittest.TestCase):
    """BUG-L: o gate do spin N já vê o pnl da decisão resolvida no spin N."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("PROFIT_CUT_V1", "PROFIT_STOP_LOSS_UNITS")}
        os.environ["PROFIT_CUT_V1"] = "0"   # isola o stop-loss
        os.environ["PROFIT_STOP_LOSS_UNITS"] = "30"
        # Ledger fake: update_result soma pnl ANTES de o gate ler (ordem real).
        self._pnl = {"v": 0.0}

        def _upd(decision_id, hit, actual, calibration_error=None, result_region=None):
            self._pnl["v"] -= 17.0  # sangria determinística: cruza o stop rápido

        self._db = MagicMock(
            save_decision=MagicMock(return_value=1),
            update_result=MagicMock(side_effect=_upd),
            get_session_pnl=MagicMock(side_effect=lambda _sid: self._pnl["v"]),
        )
        self._patches = [
            patch("server.message_handler.db_service", self._db),
            patch("server.message_handler.connection_manager", MagicMock(
                broadcast=MagicMock(side_effect=lambda *a, **k: _async_none()),
            )),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_gate_sees_fresh_pnl_same_spin(self):
        from server.message_handler import MessageHandler

        loop = asyncio.new_event_loop()
        gs = GameState()
        gs.save = lambda *a, **k: None
        handler = MessageHandler(
            game_state=gs, strategy=SDA17Strategy(),
            state_lock=asyncio.Lock(), configs_path="/tmp/does-not-exist",
        )

        def spin(numero, direcao):
            ws = _MockWS()
            loop.run_until_complete(handler.handle_new_result(
                ws, {"numero": numero, "direcao": direcao, "t_client": 0},
                TraceContext(trace_id=f"L-{numero}-{direcao}"),
            ))
            for m in ws.sent:
                b = json.loads(m)
                if b.get("type") == "sugestao":
                    return b["data"]
            return None

        import random
        rng = random.Random(3)
        # Sangra o ledger fake até ultrapassar -30 com as resoluções.
        self._pnl["v"] = -20.0
        last = None
        crossed_at = None
        for i in range(12):
            d = spin(rng.randint(0, 36), "horario" if i % 2 == 0 else "anti-horario")
            if crossed_at is None and self._pnl["v"] <= -30.0:
                crossed_at = i
                # O MESMO spin em que o ledger cruzou -30 já deve sair com
                # stake mínimo (gate leu o pnl fresco — sem lag de 1 spin).
                self.assertIn("STOP-LOSS", d["action_reason"],
                              f"gate não reagiu no spin {i} (pnl={self._pnl['v']})")
                self.assertEqual(d["aposta"], 1)
            last = d
        self.assertIsNotNone(crossed_at, "cenário não cruzou o stop-loss")
        self.assertEqual(last["aposta"], 1)


class TestAuditR3Fixes(unittest.TestCase):
    """Auditoria r3 (12/06): coerência das mudanças do dia entre si."""

    def test_fallback_does_not_pollute_satellite_ema(self):
        """Fallback (centers=[c1]): C2/C3 NÃO foram propostos → EMA só de C1."""
        s = SDA17Strategy()
        c1 = 0
        coverage = sorted(roulette.get_neighbors(c1, 10))  # N=21 calibração
        s.update_adaptive("cw", c1, _at(c1, 5), WHEEL,
                          coverage=coverage, centers=[c1])
        snap = s.get_region_err_snapshot()
        self.assertEqual(snap["cw"]["c1"], 5.0)
        self.assertIsNone(snap["cw"]["c2"], "C2 derivado não foi apostado")
        self.assertIsNone(snap["cw"]["c3"], "C3 derivado não foi apostado")
        self.assertEqual(snap["cw"]["n"], {"c1": 1, "c2": 0, "c3": 0})

    def test_sample_counter_tracks_and_resets(self):
        s = SDA17Strategy()
        c1 = 0
        centers = [c1, _at(c1, 10), _at(c1, -10)]
        cov = sorted(roulette.get_neighbors(c1, 3))
        for _ in range(3):
            s.update_adaptive("ccw", c1, _at(c1, 2), WHEEL,
                              coverage=cov, centers=centers)
        snap = s.get_region_err_snapshot()
        self.assertEqual(snap["ccw"]["n"], {"c1": 3, "c2": 3, "c3": 3})
        # roundtrip persistência
        s2 = SDA17Strategy()
        s2.load_adaptive_state(s.get_adaptive_state())
        self.assertEqual(s2._region_err_n["ccw"]["c1"], 3)
        # reset B1 zera contadores junto
        s.reset_adaptive()
        self.assertEqual(s._region_err_n["ccw"], {"c1": 0, "c2": 0, "c3": 0})


if __name__ == "__main__":
    unittest.main()
