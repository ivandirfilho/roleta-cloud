"""Auditoria 12/06 — cadência pós-reset e premissa "nunca sem indicação" (INV-3 global).

Premissas do owner (12/06 tarde):
- Pós-reset, a estratégia indica aposta plena após 2 resultados (forças) do sentido.
- A estratégia principal NUNCA fica sem indicação de aposta; isso só pode
  acontecer nas 2 primeiras oportunidades de cada sentido (calibração:
  1ª sem dados → PULAR; 2ª com 1 força → fallback N=21 JÁ indica).
- Vetos (Triple Rate, CUT-POLICY v1, stop-loss) modulam STAKE, nunca
  suprimem a indicação (INV-3 — mesmo padrão do QW-1).

Integração real: MessageHandler.handle_new_result com GameState/SDA17 reais
e camada de banco mockada (db_service).
"""
from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from models.trace import TraceContext
from state.game import GameState
from strategies.sda17 import SDA17Strategy


class _MockWS:
    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)


def _mk_handler():
    from server.message_handler import MessageHandler

    loop = asyncio.new_event_loop()
    gs = GameState()
    strategy = SDA17Strategy()
    handler = MessageHandler(
        game_state=gs,
        strategy=strategy,
        state_lock=asyncio.Lock(),
        configs_path="/tmp/does-not-exist",
    )
    handler._test_loop = loop  # loop único por handler (asyncio.Lock bound)
    return handler, gs, strategy


def _spin(handler, numero: int, direcao: str):
    ws = _MockWS()
    trace = TraceContext(trace_id=f"audit-{numero}-{direcao}")
    data = {"numero": numero, "direcao": direcao, "t_client": 0}
    handler._test_loop.run_until_complete(
        handler.handle_new_result(ws, data, trace)
    )
    for m in ws.sent:
        body = json.loads(m)
        if body.get("type") == "sugestao":
            return body["data"]
    return None


class TestCadencePostReset(unittest.TestCase):
    """Cadência por sentido: PULAR (calibração 1) → N=21 (calibração 2) → SDA pleno."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("PROFIT_CUT_V1", "PROFIT_STOP_LOSS_UNITS")}
        os.environ["PROFIT_CUT_V1"] = "1"  # política de produção
        os.environ["PROFIT_STOP_LOSS_UNITS"] = "0"
        self._patches = [
            patch("server.message_handler.db_service", MagicMock(
                save_decision=MagicMock(return_value=1),
                get_session_pnl=MagicMock(return_value=0.0),
            )),
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

    def test_full_cadence_both_directions(self):
        handler, gs, _ = _mk_handler()
        gs.save = lambda *a, **k: None  # não tocar state.json em teste

        # Spin 1 (horario): target=anti-horario, timeline_ccw=0 → calibração 1.
        d1 = _spin(handler, 10, "horario")
        self.assertEqual(d1["acao"], "PULAR")

        # Spin 2 (anti-horario): 1ª força ccw; target=horario, timeline_cw=0.
        d2 = _spin(handler, 22, "anti-horario")
        self.assertEqual(d2["acao"], "PULAR")

        # Spin 3 (horario): 1ª força cw; target=ccw com 1 força → calibração 2
        # → INDICA N=21 (nunca sem indicação tendo dados).
        d3 = _spin(handler, 5, "horario")
        self.assertEqual(d3["acao"], "APOSTAR")
        self.assertEqual(len(d3["numeros"]), 21)

        # Spin 4 (anti-horario): 2ª força ccw; target=cw com 1 força → N=21.
        d4 = _spin(handler, 30, "anti-horario")
        self.assertEqual(d4["acao"], "APOSTAR")
        self.assertEqual(len(d4["numeros"]), 21)

        # Spin 5 (horario): 2ª força cw; target=ccw com 2 forças →
        # SDA17 PLENO (17 números, 3 centros) — premissa "indica após 2
        # resultados do sentido".
        d5 = _spin(handler, 17, "horario")
        self.assertEqual(d5["acao"], "APOSTAR")
        self.assertEqual(len(d5["centros"]), 3)
        self.assertLessEqual(len(d5["numeros"]), 17)
        self.assertGreaterEqual(len(d5["numeros"]), 15)  # overlap possível

        # Spin 6+: NUNCA mais PULAR (indicação sempre presente).
        d6 = _spin(handler, 8, "anti-horario")
        self.assertEqual(d6["acao"], "APOSTAR")

    def test_never_skip_after_calibration_long_run(self):
        """50 spins alternados: zero PULAR após as 2 primeiras oportunidades/sentido."""
        handler, gs, _ = _mk_handler()
        gs.save = lambda *a, **k: None
        import random
        rng = random.Random(42)
        acoes = []
        for i in range(50):
            direcao = "horario" if i % 2 == 0 else "anti-horario"
            acoes.append(_spin(handler, rng.randint(0, 36), direcao)["acao"])
        # Oportunidades 1 e 2 (spins 1 e 2) são calibração-1 de cada sentido.
        self.assertEqual(acoes[0], "PULAR")
        self.assertEqual(acoes[1], "PULAR")
        self.assertNotIn("PULAR", acoes[2:], "indicação sumiu fora da calibração")


def _async_none():
    async def _noop(*a, **k):
        return None
    return _noop()


class TestVetosModulateStakeNotAction(unittest.TestCase):
    """INV-3: score<4 / stop-loss / TR não suprimem indicação — reduzem stake."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in ("PROFIT_CUT_V1", "PROFIT_STOP_LOSS_UNITS")}
        os.environ["PROFIT_CUT_V1"] = "1"
        self._db = MagicMock(
            save_decision=MagicMock(return_value=1),
            get_session_pnl=MagicMock(return_value=0.0),
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

    def _warmed_handler(self):
        """Handler com 2+ forças nos dois sentidos (pós-calibração)."""
        handler, gs, _ = _mk_handler()
        gs.save = lambda *a, **k: None
        import random
        rng = random.Random(7)
        for i in range(8):
            _spin(handler, rng.randint(0, 36), "horario" if i % 2 == 0 else "anti-horario")
        return handler, gs

    def test_stop_loss_keeps_indication_with_min_stake(self):
        os.environ["PROFIT_STOP_LOSS_UNITS"] = "30"
        handler, gs = self._warmed_handler()
        self._db.get_session_pnl.return_value = -45.0  # estourou o stop
        d = _spin(handler, 12, "horario")
        self.assertEqual(d["acao"], "APOSTAR", "stop-loss não pode suprimir indicação")
        self.assertEqual(d["aposta"], 1, "stop-loss deve apostar o mínimo absoluto")
        self.assertIn("STOP-LOSS", d["action_reason"])

    def test_low_score_keeps_indication_with_reduced_stake(self):
        os.environ["PROFIT_STOP_LOSS_UNITS"] = "0"
        handler, gs = self._warmed_handler()
        d = _spin(handler, 12, "horario")
        self.assertEqual(d["acao"], "APOSTAR")
        if "CUT-POLICY" in d["action_reason"] or "Calibração" in d["action_reason"]:
            self.assertLess(
                d["aposta"], d["aposta_base"],
                "veto deve reduzir stake, não suprimir indicação",
            )

    def test_decision_records_effective_stake(self):
        """LEDGER FIX: Decision.gale_bet_value = stake efetivo (pós-modulação)."""
        os.environ["PROFIT_STOP_LOSS_UNITS"] = "30"
        handler, gs = self._warmed_handler()
        self._db.get_session_pnl.return_value = -45.0
        self._db.save_decision.reset_mock()
        d = _spin(handler, 12, "horario")
        self.assertEqual(d["aposta"], 1)
        decision = self._db.save_decision.call_args[0][0]
        self.assertEqual(
            decision.gale_bet_value, 1,
            "ledger deve registrar o stake REAL apostado (não o base)",
        )


class TestFallbackForce17Radius(unittest.TestCase):
    """Regressão BUG-FRONT #1 (18/06): com SDA_BET_PAIR=force17 o fallback de
    calibração (2ª jogada do sentido) deve indicar 17# (raio 8), e NÃO 21# (raio 10),
    independentemente de SDA_FORCE17_EXACT — que rege só o padding da aposta NORMAL,
    não o fallback. Antes do fix, EXACT=0 (produção) emitia 21# (geometria antiga)."""

    def setUp(self):
        self._env = {k: os.environ.get(k) for k in (
            "SDA_BET_PAIR", "SDA_FORCE17_EXACT", "PROFIT_CUT_V1", "PROFIT_STOP_LOSS_UNITS")}
        os.environ["SDA_FORCE17_EXACT"] = "0"  # estado real de produção
        os.environ["PROFIT_CUT_V1"] = "1"
        os.environ["PROFIT_STOP_LOSS_UNITS"] = "0"
        self._patches = [
            patch("server.message_handler.db_service", MagicMock(
                save_decision=MagicMock(return_value=1),
                get_session_pnl=MagicMock(return_value=0.0),
            )),
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

    def _calibration2_numeros(self):
        handler, gs, _ = _mk_handler()
        gs.save = lambda *a, **k: None
        _spin(handler, 10, "horario")        # calibração 1 (PULAR)
        _spin(handler, 22, "anti-horario")   # calibração 1 do outro sentido (PULAR)
        d3 = _spin(handler, 5, "horario")    # calibração 2 → fallback indica
        self.assertEqual(d3["acao"], "APOSTAR")
        return d3["numeros"]

    def test_force17_fallback_is_17_not_21(self):
        os.environ["SDA_BET_PAIR"] = "force17"
        nums = self._calibration2_numeros()
        self.assertEqual(len(nums), 17, "force17: fallback de calibração deve ser 17#, não 21#")

    def test_non_force17_fallback_keeps_21(self):
        os.environ["SDA_BET_PAIR"] = "c2c3"  # controle: regime não-force17 mantém histórico
        nums = self._calibration2_numeros()
        self.assertEqual(len(nums), 21, "fora de force17, o fallback mantém 21# (raio 10)")


if __name__ == "__main__":
    unittest.main()
