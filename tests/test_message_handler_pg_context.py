"""MessageHandler × contexto de features do PG (correção 06/08).

Dois contratos guardados aqui:

1. **Ciclo de vida da decisão pendente.** `last_decision_id` e
   `last_decision_direction` nascem juntos em `__init__`, são setados juntos e
   limpos juntos. Antes deste PR o par era assimétrico (`direction` só existia
   via `getattr`), o que escondia o estado de qualquer inspeção.

2. **O contexto é lido da fonte autoritativa NA HORA de publicar**, e não
   capturado no momento da decisão. `update_last_vision()` corrige
   dealer/mesa/provider/visão na decisão mais recente DEPOIS do save (quando a
   foto/OCR chega); um contexto em cache nasceria defasado e divergiria do
   backfill. Com a flag OFF não há leitura alguma.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from database.models import Decision
from state.game import GameState

FLAG = "SDA_PG_FEATURE_CONTEXT"


@pytest.fixture(autouse=True)
def _clear_flag(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


@pytest.fixture
def handler(tmp_path):
    from server.message_handler import MessageHandler
    return MessageHandler(GameState(), MagicMock(), asyncio.Lock(), str(tmp_path))


def _decision(**over) -> Decision:
    base = dict(id=99, session_id="s1", dealer="Ana", dealer_table="Mesa X",
                provider="Evolution", spin_seq=5, direction_source="authority")
    base.update(over)
    return Decision(**base)


# ---------------------------------------------------------------------------
# Ciclo de vida do par (id, direction)
# ---------------------------------------------------------------------------

def test_pending_decision_state_starts_empty(handler):
    assert handler.last_decision_id is None
    assert handler.last_decision_direction is None


def test_pending_decision_state_is_declared_in_init():
    """Ambos nascem em __init__ — sem estado fantasma criado só no meio do fluxo."""
    import inspect

    from server.message_handler import MessageHandler
    src = inspect.getsource(MessageHandler.__init__)
    assert "self.last_decision_id" in src
    assert "self.last_decision_direction" in src


def test_pending_decision_state_is_set_and_cleared_together():
    """No fluxo do giro os dois campos mudam sempre no mesmo par de ramos."""
    import inspect

    from server.message_handler import MessageHandler
    src = inspect.getsource(MessageHandler)
    assert src.count("self.last_decision_id = ") == src.count(
        "self.last_decision_direction = ")


# ---------------------------------------------------------------------------
# _pg_feature_context
# ---------------------------------------------------------------------------

def test_context_is_none_without_pending_decision(handler):
    assert handler._pg_feature_context(None) is None


def test_flag_off_never_touches_the_database(handler):
    repo = MagicMock()
    with patch("server.message_handler.db_service") as svc:
        svc.repository = repo
        assert handler._pg_feature_context(99) is None
    repo.get_decision.assert_not_called()


def test_flag_on_reads_authoritative_row_at_publish_time(handler, monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    repo = MagicMock()
    repo.get_decision.return_value = _decision()
    with patch("server.message_handler.db_service") as svc:
        svc.repository = repo
        ctx = handler._pg_feature_context(99)
    repo.get_decision.assert_called_once_with(99)
    assert ctx["decision_id"] == 99
    assert ctx["dealer"] == "Ana"
    assert ctx["dealer_table"] == "Mesa X"


def test_context_reflects_post_save_ocr_correction(handler, monkeypatch):
    """Regressão do motivo de NÃO cachear: a foto/OCR chega depois do save.

    `update_last_vision` reescreve dealer/mesa/provider na decisão mais recente
    quando o frame chega. Reler no publish faz o valor projetado ao vivo ser o
    MESMO que o backfill reconstruiria a partir do SQLite.
    """
    monkeypatch.setenv(FLAG, "1")
    repo = MagicMock()
    # Estado no momento do save: sem dealer (o DOM não expõe).
    repo.get_decision.return_value = _decision(dealer="unknown", dealer_table="")
    with patch("server.message_handler.db_service") as svc:
        svc.repository = repo
        before = handler._pg_feature_context(99)
    assert before["dealer"] is None

    # Foto chega e corrige a linha; o publish acontece depois.
    repo.get_decision.return_value = _decision(dealer="Bia", dealer_table="Mesa Y")
    with patch("server.message_handler.db_service") as svc:
        svc.repository = repo
        after = handler._pg_feature_context(99)
    assert after["dealer"] == "Bia"
    assert after["dealer_table"] == "Mesa Y"


def test_missing_decision_row_yields_none(handler, monkeypatch):
    monkeypatch.setenv(FLAG, "1")
    repo = MagicMock()
    repo.get_decision.return_value = None
    with patch("server.message_handler.db_service") as svc:
        svc.repository = repo
        assert handler._pg_feature_context(99) is None


def test_repository_failure_never_breaks_the_spin(handler, monkeypatch):
    """Telemetria nunca derruba o giro: erro vira log + contexto None."""
    monkeypatch.setenv(FLAG, "1")
    repo = MagicMock()
    repo.get_decision.side_effect = RuntimeError("db locked")
    with patch("server.message_handler.db_service") as svc:
        svc.repository = repo
        assert handler._pg_feature_context(99) is None


def test_context_is_passed_to_the_publisher(monkeypatch):
    """O publish do resultado carrega o contexto (evento self-contained)."""
    monkeypatch.setenv(FLAG, "1")
    from database import outbox_integration as oi

    fake_pub = MagicMock()
    with patch("database.outbox_integration._is_flag_enabled", return_value=True), \
         patch("database.outbox_integration._get_publisher", return_value=fake_pub):
        oi.maybe_publish_spin_result(
            99, "horario", True, 32, session_id="s1",
            context=oi.build_pg_feature_context(_decision()),
        )
    payload = fake_pub.publish.call_args.kwargs["payload"]
    assert payload["context"]["dealer"] == "Ana"
    assert payload["decision_id"] == 99
