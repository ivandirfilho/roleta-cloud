"""Tests — phantom dedup (auditoria resultados_bancos 22/06).

A extensão às vezes reenvia o MESMO número+sentido 1-7s depois (re-detecção do
DOM estático); o ciclo real é ~42-48s. is_duplicate_spin rejeita esses re-envios
quando SDA_DEDUP_PHANTOM=1, usando a JANELA DE TEMPO como discriminador. Default
OFF (toca o caminho de aposta). A guarda original (mesmo número no mesmo segundo)
continua valendo independic da flag.
"""
import asyncio
from unittest.mock import MagicMock

import pytest


def _make_handler():
    from server.message_handler import MessageHandler
    return MessageHandler(
        game_state=MagicMock(),
        strategy=MagicMock(),
        state_lock=asyncio.Lock(),
        configs_path="/tmp/does-not-exist",
    )


def test_same_second_dedup_always(monkeypatch):
    monkeypatch.delenv("SDA_DEDUP_PHANTOM", raising=False)
    h = _make_handler()
    assert h.is_duplicate_spin(5, 1000, "horario") is False   # 1º aceito
    assert h.is_duplicate_spin(5, 1500, "horario") is True     # mesmo nº, mesmo segundo


def test_phantom_disabled_by_default(monkeypatch):
    monkeypatch.delenv("SDA_DEDUP_PHANTOM", raising=False)
    h = _make_handler()
    assert h.is_duplicate_spin(5, 1000, "horario") is False
    # mesmo nº+sentido 3s depois (fantasma) — flag OFF: NÃO rejeita
    assert h.is_duplicate_spin(5, 4000, "horario") is False


def test_phantom_rejected_when_enabled(monkeypatch):
    monkeypatch.setenv("SDA_DEDUP_PHANTOM", "1")
    h = _make_handler()
    assert h.is_duplicate_spin(5, 1000, "horario") is False     # 1º aceito
    assert h.is_duplicate_spin(5, 4000, "horario") is True       # re-envio 3s depois -> fantasma
    assert h.is_duplicate_spin(5, 7000, "horario") is True       # outro re-envio dentro da janela


def test_real_spin_beyond_window_accepted(monkeypatch):
    monkeypatch.setenv("SDA_DEDUP_PHANTOM", "1")
    monkeypatch.setenv("SDA_DEDUP_PHANTOM_WINDOW_MS", "20000")
    h = _make_handler()
    assert h.is_duplicate_spin(5, 1000, "horario") is False
    # mesmo nº 45s depois (ciclo real) -> NÃO é fantasma
    assert h.is_duplicate_spin(5, 46000, "horario") is False


def test_phantom_distinguishes_number_and_direction(monkeypatch):
    monkeypatch.setenv("SDA_DEDUP_PHANTOM", "1")
    h = _make_handler()
    assert h.is_duplicate_spin(5, 1000, "horario") is False
    assert h.is_duplicate_spin(8, 3000, "horario") is False      # nº diferente -> aceita
    assert h.is_duplicate_spin(8, 5000, "anti-horario") is False  # sentido diferente -> aceita
    assert h.is_duplicate_spin(8, 6000, "anti-horario") is True   # agora repete nº+sentido -> fantasma
