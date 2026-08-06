"""SPR-V1 / DIR21 — FURO B: intervalo mínimo entre giros (plausibilidade física).

A roleta real cicla em ~42-48s. Um `novo_resultado` que chega poucos ms depois do
último giro ACEITO é fisicamente impossível — só serve para avançar `spin_seq` e
INVERTER a fase autoritativa (a fase é um toggle: um giro fantasma flipa o sentido
de todos os giros seguintes).

Medido no relógio MONOTÔNICO DO SERVIDOR: `_last_accept_ts_ms` (usado pelo dedup
legado) é `Date.now()` do CLIENTE — adulterável e sujeito a regressão por NTP.

Flag `SDA_MIN_SPIN_INTERVAL_MS` default 0 (OFF).
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app_config.settings import min_spin_interval_ms
from state.game import GameState
from state.phase import HORARIO, ANTI


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("SDA_MIN_SPIN_INTERVAL_MS", raising=False)
    assert min_spin_interval_ms() == 0
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    assert min_spin_interval_ms() == 15000


def test_flag_ignora_valor_invalido_e_negativo(monkeypatch):
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "abc")
    assert min_spin_interval_ms() == 0
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "-5")
    assert min_spin_interval_ms() == 0


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send(self, message):
        self.sent.append(message)


@pytest.fixture()
def handler(tmp_path, monkeypatch):
    import database
    from app_config.settings import settings
    from strategies.sda17 import SDA17Strategy
    from server import message_handler as mh_mod
    from server.message_handler import MessageHandler

    database.init_database(str(tmp_path / "d.db"))
    monkeypatch.setattr(settings, "state_file", tmp_path / "state.json")
    monkeypatch.setattr(mh_mod.db_service, "save_decision", lambda d: 1)
    monkeypatch.setattr(
        mh_mod.connection_manager, "broadcast",
        MagicMock(side_effect=lambda *a, **k: asyncio.sleep(0)),
    )
    monkeypatch.setattr(mh_mod.connection_manager, "get_role", lambda cid: "master")
    return MessageHandler(
        game_state=GameState(), strategy=SDA17Strategy(),
        state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"),
    )


def _spin(handler, ws, i, numero, direcao):
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": numero, "direcao": direcao,
        "timestamp": 1_700_000_000_000 + i * 45_000, "trace_id": f"t-{i:03d}",
        "allNumbers": [numero],
    }), "c1"))


def test_relogio_nasce_desarmado(handler):
    assert handler._last_accept_srv_mono is None


def test_relogio_arma_somente_apos_giro_aceito(handler, monkeypatch):
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    assert handler._last_accept_srv_mono is not None
    assert handler.game_state.spin_seq == 1


def test_giro_implausivel_e_descartado(handler, monkeypatch):
    """Segundo giro imediato (mesmo com número/direção/trace diferentes) é barrado."""
    from state import phase_metrics
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    phase_metrics.reset()
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    seq = handler.game_state.spin_seq
    _spin(handler, ws, 1, 32, ANTI)
    assert handler.game_state.spin_seq == seq, "giro fantasma avancou spin_seq (flip de fase)"
    assert phase_metrics.snapshot()["spin_implausivel_total"] == 1
    phase_metrics.reset()


def test_flag_off_aceita_giro_rapido(handler, monkeypatch):
    """INV ADITIVO: com a flag em 0 nada muda."""
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "0")
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    _spin(handler, ws, 1, 32, ANTI)
    assert handler.game_state.spin_seq == 2


def test_rejeicao_nao_arma_o_relogio(handler, monkeypatch):
    """Um giro REJEITADO não pode empurrar a janela para a frente — senão bastaria
    uma rajada para bloquear indefinidamente os giros legítimos."""
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    t_apos_aceito = handler._last_accept_srv_mono
    _spin(handler, ws, 1, 32, ANTI)
    assert handler._last_accept_srv_mono == t_apos_aceito


def test_gate_nao_queima_trace_id(handler, monkeypatch):
    """O gate roda ANTES do dedup por trace_id: um giro rejeitado por implausibilidade
    NÃO pode inutilizar o seu trace_id, senão o reenvio legítimo do mesmo giro (depois
    que o intervalo passar) seria descartado como duplicado."""
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    monkeypatch.setenv("SDA_DEDUP_SEQ", "1")
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": 32, "direcao": ANTI,
        "timestamp": 1, "trace_id": "reenviado", "allNumbers": [32],
    }), "c1"))
    assert "reenviado" not in list(handler._recent_trace_ids)
    # Intervalo passou (simulado): o MESMO trace_id ainda é aceitável.
    handler._last_accept_srv_mono = None
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "novo_resultado", "numero": 32, "direcao": ANTI,
        "timestamp": 2, "trace_id": "reenviado", "allNumbers": [32],
    }), "c1"))
    assert handler.game_state.spin_seq == 2


def test_reset_de_sessao_desarma_o_relogio(handler, monkeypatch):
    """Sessão nova = mesa/dealer novo: o primeiro giro não pode ser barrado pelo
    último giro da sessão anterior."""
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    asyncio.run(handler.process_message(
        ws, json.dumps({"type": "nova_sessao"}), "c1"))
    assert handler._last_accept_srv_mono is None
    _spin(handler, ws, 1, 32, ANTI)
    assert handler.game_state.spin_seq == 1  # reset zerou; este giro entrou


def test_correcao_historico_desarma_o_relogio(handler, monkeypatch):
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "correcao_historico", "resultados": [{"numero": 5, "direcao": HORARIO}],
    }), "c1"))
    assert handler._last_accept_srv_mono is None


def test_nao_persistido_no_round_trip(handler, tmp_path, monkeypatch):
    """DECISÃO CONSCIENTE (ADENDO ISO): `time.monotonic()` só é comparável dentro do
    MESMO processo — persistir produziria comparação sem sentido após restart. O campo
    fica FORA de save()/load(); o custo é aceitar um giro logo após um restart."""
    monkeypatch.setenv("SDA_MIN_SPIN_INTERVAL_MS", "15000")
    ws = _FakeWS()
    _spin(handler, ws, 0, 17, HORARIO)
    p = tmp_path / "s.json"
    handler.game_state.save(p)
    dados = json.loads(p.read_text(encoding="utf-8"))
    assert "_last_accept_srv_mono" not in dados
    assert not any("srv_mono" in k for k in dados)
