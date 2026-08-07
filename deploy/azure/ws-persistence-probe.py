#!/usr/bin/env python3
"""Envia spins pelo protocolo WebSocket real e exige sugestão APOSTAR por spin."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid

import websockets


async def wait_for_type(ws, expected: str, timeout: float = 15.0) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"timeout esperando mensagem {expected}")
        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        payload = json.loads(raw)
        if payload.get("type") == "error":
            raise RuntimeError(f"servidor retornou erro: {payload}")
        if payload.get("type") == expected:
            return payload


async def run(url: str, count: int) -> dict:
    device_id = f"azure-probe-{uuid.uuid4().hex[:12]}"
    async with websockets.connect(
        url,
        open_timeout=15,
        close_timeout=10,
        ping_interval=20,
        ping_timeout=20,
    ) as ws:
        await wait_for_type(ws, "role_assigned")
        await ws.send(json.dumps({"type": "register", "device_id": device_id}))
        role = await wait_for_type(ws, "role_assigned")
        if role.get("role") != "master":
            raise RuntimeError(f"probe não virou MASTER: {role}")

        base_ms = int(time.time() * 1000) + 2000
        suggestions = 0
        for index in range(count):
            timestamp = base_ms + index * 1000
            payload = {
                "type": "novo_resultado",
                "numero": index % 37,
                "direcao": "horario" if index % 2 == 0 else "anti-horario",
                "trace_id": f"probe-{uuid.uuid4().hex[:12]}-{index}",
                "t_client": timestamp,
                "timestamp": timestamp,
                "provider": "probe",
                "table": "azure-precutover",
                "round_id": f"probe-round-{index}",
            }
            await ws.send(json.dumps(payload))
            suggestion = await wait_for_type(ws, "sugestao", timeout=30)
            action = (suggestion.get("data") or {}).get("acao")
            if action != "APOSTAR":
                raise RuntimeError(f"INV-3 violada no spin {index}: acao={action!r}")
            suggestions += 1

    return {
        "url": url,
        "device_id": device_id,
        "spins_sent": count,
        "suggestions_received": suggestions,
        "inv3": "APOSTAR",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8765")
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.count <= 1000:
        parser.error("--count deve estar entre 1 e 1000")
    result = asyncio.run(run(args.url, args.count))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
