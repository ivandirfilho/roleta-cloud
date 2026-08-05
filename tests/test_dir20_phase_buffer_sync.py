"""SPR-V1 / DIR20 — FURO A: sincronização do BUFFER DE FASE nos gaps.

Antes: o bloco de gap do DIR4 sincronizava só `recent_results` (zona fria C3), mas
desde a DIR19 o alinhamento lê `_phase_results`. Resultado: depois de QUALQUER gap o
buffer de fase ficava permanentemente defasado, todo giro seguinte virava
`phase_uncertain` e a DIR17 re-ancorava na direção do CLIENTE — que é exatamente a
fonte que a fase autoritativa existe para não obedecer.

Depois: `GameState.sync_phase_buffer(inter)` espelha os números recuperados, atrás da
flag `SDA_PHASE_BUFFER_SYNC` (default OFF).
"""

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from app_config.settings import phase_buffer_sync_enabled
from state.game import GameState
from state.phase import HORARIO, ANTI, phase_advance


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("SDA_PHASE_BUFFER_SYNC", raising=False)
    assert phase_buffer_sync_enabled() is False
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "1")
    assert phase_buffer_sync_enabled() is True


def test_sync_phase_buffer_preserva_ordem_mru():
    """`inter` vem do mais antigo ao mais recente; appendleft nessa ordem deixa o
    mais recente em [0] — mesma convenção de `_phase_results`/`allNumbers`."""
    gs = GameState()
    for n in [10, 20, 30]:
        gs.process_spin(n, HORARIO)
    assert list(gs._phase_results) == [30, 20, 10]
    assert gs.sync_phase_buffer([40, 50]) is True   # 40 mais antigo, 50 mais recente
    assert list(gs._phase_results) == [50, 40, 30, 20, 10]


def test_sync_phase_buffer_nao_toca_recent_results():
    """INV: a zona fria C3 do SDA17 é sincronizada pelo handler, não por aqui."""
    gs = GameState()
    gs.process_spin(7, HORARIO)
    antes = list(gs.recent_results)
    gs.sync_phase_buffer([11, 12])
    assert list(gs.recent_results) == antes


def test_sync_phase_buffer_lista_vazia_e_noop():
    gs = GameState()
    gs.process_spin(7, HORARIO)
    assert gs.sync_phase_buffer([]) is True
    assert list(gs._phase_results) == [7]


def test_sync_phase_buffer_sem_buffer_retorna_false_e_loga(caplog):
    """Estado legado (load antigo sem `_phase_results`): FALHA RUIDOSA, não silenciosa."""
    gs = GameState()
    delattr(gs, "_phase_results")
    with caplog.at_level("ERROR"):
        assert gs.sync_phase_buffer([1, 2]) is False
    assert any("sync_phase_buffer" in r.message for r in caplog.records)


def test_sync_phase_buffer_valores_invalidos_nao_mutam_parcialmente(caplog):
    """Conversão ANTES da mutação: um valor ruim no meio não deixa o buffer meio-cheio."""
    gs = GameState()
    gs.process_spin(5, HORARIO)
    with caplog.at_level("ERROR"):
        assert gs.sync_phase_buffer([1, "xx", 3]) is False
    assert list(gs._phase_results) == [5]


def test_invariante_prefixo_apos_gap_recuperado():
    """Após sincronizar o gap, `_phase_results` é PREFIXO-equivalente ao `allNumbers`
    do cliente (o buffer guarda 20, a janela do cliente tem 12)."""
    gs = GameState()
    historico = [4, 19, 15, 32, 0, 26, 3, 35]
    for n in historico:
        gs.process_spin(n, HORARIO)
    prev = list(gs._phase_results)
    # Cliente reaparece com 3 números novos (2 perdidos + o do giro atual).
    all_numbers = [12, 28, 7] + prev
    gap, inter, uncertain = phase_advance(prev, all_numbers)
    assert (gap, uncertain) == (2, False)
    assert gs.sync_phase_buffer(inter) is True
    gs.process_spin(all_numbers[0], ANTI)   # o giro atual entra pelo process_spin
    janela = all_numbers[:12]
    assert list(gs._phase_results)[: len(janela)] == janela


# ---------------------------------------------------------------- handler (E2E)

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
    monkeypatch.setenv("SDA_PHASE_RECONCILE", "1")
    monkeypatch.setenv("SDA_SENTIDO_AUTORITATIVO", "1")
    monkeypatch.setenv("SDA_UNCERTAIN_REANCORA", "1")
    return MessageHandler(
        game_state=GameState(), strategy=SDA17Strategy(),
        state_lock=asyncio.Lock(), configs_path=str(tmp_path / "cfg"),
    )


def _enviar(handler, ws, i, numero, direcao, all_numbers):
    data = {
        "type": "novo_resultado", "numero": numero, "direcao": direcao,
        "timestamp": 1_700_000_000_000 + i * 45_000, "trace_id": f"t-{i:03d}",
        "allNumbers": all_numbers,
    }
    asyncio.run(handler.process_message(ws, json.dumps(data), "c1"))


def _rodar_com_gap(handler, monkeypatch, flag: str):
    """Envia 6 giros, ESCONDE 2 do stream (só chegam em allNumbers) e mede quantos
    `phase_uncertain` acontecem DEPOIS do gap."""
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", flag)
    from state import phase_metrics
    phase_metrics.reset()
    spins = [17, 32, 5, 21, 0, 26, 3, 12, 28, 7]
    escondidos = {4, 5}
    ws = _FakeWS()
    for i, numero in enumerate(spins):
        if i in escondidos:
            continue
        direcao = HORARIO if i % 2 == 0 else ANTI
        _enviar(handler, ws, i, numero, direcao, list(reversed(spins[: i + 1])))
    snap = phase_metrics.snapshot()
    phase_metrics.reset()
    return snap


def test_gap_sem_sync_deixa_fase_permanentemente_incerta(handler, monkeypatch):
    """REPRODUÇÃO do furo A: com a flag OFF todo giro após o gap é phase_uncertain."""
    snap = _rodar_com_gap(handler, monkeypatch, "0")
    assert snap["gap_recuperado_total"] >= 1
    assert snap["phase_uncertain_total"] >= 3, snap


def test_gap_com_sync_nao_contamina_giros_seguintes(handler, monkeypatch):
    """FIX: com a flag ON o buffer volta a alinhar e a incerteza NÃO se propaga."""
    snap = _rodar_com_gap(handler, monkeypatch, "1")
    assert snap["gap_recuperado_total"] >= 1
    assert snap["phase_uncertain_total"] == 0, snap
    assert snap["phase_buffer_missing_total"] == 0


def test_correcao_historico_limpa_buffer_de_fase(handler, monkeypatch):
    """Reprocessar histórico não pode deixar números da mesa ANTERIOR no buffer."""
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "1")
    gs = handler.game_state
    for n in [4, 19, 15]:
        gs.process_spin(n, HORARIO)
    assert len(gs._phase_results) == 3
    ws = _FakeWS()
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "correcao_historico",
        "resultados": [{"numero": 7, "direcao": HORARIO}, {"numero": 11, "direcao": ANTI}],
    }), "c1"))
    assert 4 not in list(gs._phase_results)


def test_correcao_historico_com_flag_off_preserva_legado(handler, monkeypatch):
    monkeypatch.setenv("SDA_PHASE_BUFFER_SYNC", "0")
    gs = handler.game_state
    for n in [4, 19, 15]:
        gs.process_spin(n, HORARIO)
    ws = _FakeWS()
    asyncio.run(handler.process_message(ws, json.dumps({
        "type": "correcao_historico", "resultados": [],
    }), "c1"))
    assert 4 in list(gs._phase_results)
