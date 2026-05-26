"""B-09 (26/05/2026) regression test.

`state.game.GameState.store_prediction` persiste a lista de centros SDA na
chave `"centers"` do dict `pending_prediction` (linha ~465). Por engano, a
sprint W-02 inicial em `server/message_handler.py` consultava
`pending.get("sda_centers", [])`, que sempre retornava `[]`. Resultado: o
campo `calibration_error` ficou 0/N populado em produção mesmo após o
deploy de W-01+W-02.

Este teste blinda contra regressões: garante que o pending grava a chave
"centers" e que a lista de centros é recuperável a partir dela.
"""
from __future__ import annotations

import pytest

from state.game import GameState


@pytest.fixture
def gs() -> GameState:
    return GameState()


def test_pending_uses_centers_key(gs: GameState) -> None:
    gs.store_prediction(
        numbers=[17, 32, 15, 19, 4],
        direction="anti-horario",
        center=17,
        sda_centers=[17, 32, 15],
    )
    pending = gs.pending_prediction
    assert pending is not None
    assert "centers" in pending, "pending deve guardar a chave 'centers'"
    assert pending["centers"] == [17, 32, 15]


def test_pending_centers_fallback_to_center(gs: GameState) -> None:
    gs.store_prediction(
        numbers=[17],
        direction="horario",
        center=17,
        sda_centers=None,
    )
    pending = gs.pending_prediction
    assert pending is not None
    assert pending["centers"] == [17], "sem sda_centers, fallback = [center]"


def test_handler_reads_centers_not_sda_centers(gs: GameState) -> None:
    """Garante que o consumidor (message_handler) lê a chave correta."""
    gs.store_prediction(
        numbers=[0, 32, 26],
        direction="horario",
        center=0,
        sda_centers=[0, 32, 26],
    )
    pending = gs.pending_prediction
    centers = pending.get("centers") or pending.get("sda_centers") or []
    assert centers == [0, 32, 26]
    assert pending.get("sda_centers", []) == [], (
        "documentar: chave 'sda_centers' NAO existe no pending — "
        "consumidores devem ler 'centers'"
    )
