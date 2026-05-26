"""
Testes ISO-S2 — sanitizacao de ErrorOutput (Seguranca / BUG-POST-004).

Garante que:
- Excecoes internas NAO vazam str(e) bruto para o cliente
- Apenas trace_id e mensagem opaca sao expostos
- Detalhe completo eh logado server-side (verificavel via caplog)
"""
import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest


class _MockWS:
    def __init__(self):
        self.sent = []

    async def send(self, msg):
        self.sent.append(msg)


def _make_handler():
    from server.message_handler import MessageHandler

    return MessageHandler(
        game_state=MagicMock(),
        strategy=MagicMock(),
        state_lock=asyncio.Lock(),
        configs_path="/tmp/does-not-exist",
    )


@pytest.mark.asyncio
async def test_generic_exception_does_not_leak_str_e(caplog):
    """Erro 500 nao deve conter o repr do erro interno."""
    handler = _make_handler()

    # Forca excecao injetando handle_legacy_spin com side_effect
    secret_path = "/etc/super_secret_password_file.txt"
    handler.handle_legacy_spin = AsyncMock(
        side_effect=RuntimeError(f"failed reading {secret_path}")
    )

    ws = _MockWS()
    # type 'spin' cai no else (handle_legacy_spin) e nao exige role check
    payload = json.dumps({"type": "spin", "trace_id": "trc-iso-s2-test"})

    with caplog.at_level(logging.ERROR, logger="server.message_handler"):
        await handler.process_message(ws, payload, conn_id="test-conn")

    assert len(ws.sent) == 1
    body = json.loads(ws.sent[0])

    # ASSERT CRITICO: caminho sensivel NAO esta na mensagem
    assert secret_path not in body["message"], (
        f"VAZAMENTO: path interno apareceu em ErrorOutput cliente: {body}"
    )
    assert "failed reading" not in body["message"]
    # trace_id para correlacao
    assert "trc-iso-s2-test" in body["message"]
    assert body["code"] == 500

    # Detalhe completo precisa ter sido logado server-side
    full_log = "\n".join(r.getMessage() for r in caplog.records)
    assert secret_path in full_log, "detalhe interno precisa estar nos logs"


@pytest.mark.asyncio
async def test_json_decode_error_does_not_leak_payload(caplog):
    """Erro 400 de JSON invalido nao deve ecoar payload bruto."""
    handler = _make_handler()
    ws = _MockWS()

    bad_payload = "this-is-not-json{{{ secret_token=abc123XYZ"

    with caplog.at_level(logging.ERROR, logger="server.message_handler"):
        await handler.process_message(ws, bad_payload, conn_id="test-conn")

    assert len(ws.sent) == 1
    body = json.loads(ws.sent[0])
    assert body["code"] == 400
    # Mensagem do cliente deve ser generica
    assert "secret_token" not in body["message"]
    assert "abc123XYZ" not in body["message"]

