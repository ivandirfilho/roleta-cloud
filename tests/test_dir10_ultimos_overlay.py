"""DIR10 (sentido-fase): ultimos[N]{numero,seq,direction} no overlay (fix #K).

Antes: overlay so tinha last_seq escalar. Auditoria offline cega.

Depois: GameState._phase_overlay_ring (deque maxlen=12) recebe cada giro com
{numero, seq, direction}. engine_overlay_fields publica como out["ultimos"][N]
(N controlado por SDA_OVERLAY_ULTIMOS_N; 0 desativa). Buffer SEPARADO de
recent_results (zona fria C3, maxlen=10 — nao mexer).
"""

import os
import tempfile
from pathlib import Path
from state.game import GameState
from state.phase import HORARIO, ANTI
from app_config.settings import overlay_ultimos_n


def test_flag_default_12(monkeypatch):
    monkeypatch.delenv("SDA_OVERLAY_ULTIMOS_N", raising=False)
    assert overlay_ultimos_n() == 12
    monkeypatch.setenv("SDA_OVERLAY_ULTIMOS_N", "5")
    assert overlay_ultimos_n() == 5
    monkeypatch.setenv("SDA_OVERLAY_ULTIMOS_N", "0")
    assert overlay_ultimos_n() == 0


def test_process_spin_alimenta_ring():
    """Cada giro vai para o ring overlay com numero+seq+direction."""
    gs = GameState()
    gs.spin_seq = 0
    gs.process_spin(7, HORARIO)
    gs.spin_seq = 1
    gs.process_spin(22, ANTI)
    gs.spin_seq = 2
    gs.process_spin(13, HORARIO)
    ring = list(gs._phase_overlay_ring)
    assert len(ring) == 3
    # Mais recente em [0]:
    assert ring[0]["numero"] == 13
    assert ring[0]["direction"] == HORARIO
    assert ring[1]["numero"] == 22
    assert ring[2]["numero"] == 7


def test_overlay_publica_ultimos(monkeypatch):
    """engine_overlay_fields inclui out['ultimos'] limitado a N."""
    monkeypatch.setenv("SDA_OVERLAY_ULTIMOS_N", "3")
    gs = GameState()
    for i, (n, d) in enumerate([(1, HORARIO), (2, ANTI), (3, HORARIO), (4, ANTI), (5, HORARIO)]):
        gs.spin_seq = i
        gs.process_spin(n, d)
    out = gs.engine_overlay_fields()
    assert "ultimos" in out
    assert len(out["ultimos"]) == 3
    assert out["ultimos"][0]["numero"] == 5


def test_overlay_desativado_com_n_zero(monkeypatch):
    """N=0 desativa publicacao (ring nao aparece no overlay)."""
    monkeypatch.setenv("SDA_OVERLAY_ULTIMOS_N", "0")
    gs = GameState()
    gs.process_spin(10, HORARIO)
    out = gs.engine_overlay_fields()
    assert "ultimos" not in out


def test_register_history_alimenta_ring_nao_direcional():
    """register_history_number popula ring com direction='' (NAO-direcional)."""
    gs = GameState()
    gs.register_history_number(7)
    gs.register_history_number(22)
    ring = list(gs._phase_overlay_ring)
    assert len(ring) == 2
    assert all(r["direction"] == "" for r in ring)


def test_roundtrip_ring_em_save_load():
    """Ring overlay sobrevive a save/load (cliente nao perde timeline em restart)."""
    gs = GameState()
    for i, (n, d) in enumerate([(10, HORARIO), (20, ANTI)]):
        gs.spin_seq = i
        gs.process_spin(n, d)
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "state.json"
        gs.save(p)
        gs2 = GameState.load(p)
    ring2 = list(gs2._phase_overlay_ring)
    assert len(ring2) == 2
    assert ring2[0]["numero"] == 20


def test_reset_session_limpa_ring():
    """reset_session zera o ring (novo dealer = nova historia)."""
    gs = GameState()
    gs.process_spin(10, HORARIO)
    gs.process_spin(20, ANTI)
    assert len(gs._phase_overlay_ring) == 2
    gs.reset_session()
    assert len(gs._phase_overlay_ring) == 0
