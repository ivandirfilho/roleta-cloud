"""Tests — Vision fill-forward do dealer (auditoria_pos_foto 21/06 §7.2).

Cobre a lógica PURA (core/dealer_fill.resolve_dealer) e o wiring por-sessão no
MessageHandler (_resolve_spin_dealer / _remember_dealer), incluindo o corte na
troca de dealer e na troca de sessão. Tudo flag-gated (SDA_DEALER_FILL_FORWARD)
e metadata — não toca aposta.
"""
import asyncio
from unittest.mock import MagicMock

import pytest

from core.dealer_fill import is_real_dealer, resolve_dealer


# ---------- lógica pura ----------

def test_is_real_dealer():
    assert is_real_dealer("LEVI")
    assert is_real_dealer("  Anna ")
    assert not is_real_dealer(None)
    assert not is_real_dealer("")
    assert not is_real_dealer("unknown")
    assert not is_real_dealer("UNKNOWN")


def test_resolve_real_dealer_becomes_last_known():
    used, last = resolve_dealer("LEVI", None, enabled=True)
    assert used == "LEVI" and last == "LEVI"


def test_resolve_fills_forward_when_enabled():
    used, last = resolve_dealer(None, "LEVI", enabled=True)
    assert used == "LEVI" and last == "LEVI"
    used2, last2 = resolve_dealer("unknown", "LEVI", enabled=True)
    assert used2 == "LEVI" and last2 == "LEVI"


def test_resolve_no_fill_when_disabled():
    used, last = resolve_dealer(None, "LEVI", enabled=False)
    assert used is None and last == "LEVI"  # flag OFF: não preenche, mantém memória


def test_resolve_cuts_on_dealer_change():
    used, last = resolve_dealer("ANNA", "LEVI", enabled=True)
    assert used == "ANNA" and last == "ANNA"  # dealer real novo substitui


def test_resolve_no_last_known_returns_raw():
    used, last = resolve_dealer(None, None, enabled=True)
    assert used is None and last is None


# ---------- wiring no handler (por sessão) ----------

def _make_handler():
    from server.message_handler import MessageHandler
    return MessageHandler(
        game_state=MagicMock(),
        strategy=MagicMock(),
        state_lock=asyncio.Lock(),
        configs_path="/tmp/does-not-exist",
    )


def test_handler_fill_forward_enabled(monkeypatch):
    monkeypatch.setenv("SDA_DEALER_FILL_FORWARD", "1")
    h = _make_handler()
    assert h._resolve_spin_dealer("LEVI") == "LEVI"   # real -> usa e memoriza
    assert h._resolve_spin_dealer(None) == "LEVI"     # sem dealer -> herda
    assert h._resolve_spin_dealer("unknown") == "LEVI"
    assert h._resolve_spin_dealer("ANNA") == "ANNA"   # troca corta
    assert h._resolve_spin_dealer(None) == "ANNA"


def test_handler_fill_forward_disabled(monkeypatch):
    monkeypatch.setenv("SDA_DEALER_FILL_FORWARD", "0")
    h = _make_handler()
    assert h._resolve_spin_dealer("LEVI") == "LEVI"
    assert h._resolve_spin_dealer(None) is None       # flag OFF: não herda


def test_handler_session_change_invalidates(monkeypatch):
    monkeypatch.setenv("SDA_DEALER_FILL_FORWARD", "1")
    h = _make_handler()
    h._resolve_spin_dealer("LEVI")
    h.current_session_id = "newsess0"                 # troca de sessão
    assert h._resolve_spin_dealer(None) is None        # não vaza entre sessões


def test_handler_remember_dealer_from_vision(monkeypatch):
    monkeypatch.setenv("SDA_DEALER_FILL_FORWARD", "1")
    h = _make_handler()
    h._remember_dealer("STEFANY")                      # ex.: vindo do OCR
    assert h._resolve_spin_dealer(None) == "STEFANY"
    h._remember_dealer("unknown")                      # não sobrescreve com lixo
    assert h._resolve_spin_dealer(None) == "STEFANY"
