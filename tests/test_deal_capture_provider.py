"""Tests para o helper normalizeProvider de extension/deal_capture.js.

BUG-1 FIX 21/06 (auditoria_pos_foto): o fallback de provider NAO pode mais
vazar `host:<dominio>` — frames de analytics (googletagmanager/doubleclick) e o
proprio dashboard (roleta.xma-ia.com) poluiam decisions.provider. O helper agora
recupera a marca pelo dominio (evo-games -> evolution) ou devolve 'unknown'.

Espelha a convencao de teste de JS da extensao (provider_router.js): carrega o
modulo UMD via `node -e require(...)` e valida a logica pura (sem DOM/browser).
"""
import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "extension" / "deal_capture.js"


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _node_available(), reason="Node.js required for deal_capture tests")


def _run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "-e", script],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def _load_expr() -> str:
    # require() executa o bloco UMD do topo (module.exports) sem rodar o IIFE
    # do content script (que depende de window/document/location).
    return f"const r = require({json.dumps(str(HELPER))});"


def test_helper_exports():
    out = _run_node(_load_expr() + """
      process.stdout.write(JSON.stringify({
        hasMatch: typeof r.matchHostBrand,
        hasNorm: typeof r.normalizeProvider,
      }));
    """)
    assert out["hasMatch"] == "function"
    assert out["hasNorm"] == "function"


def test_recovers_brand_from_domain():
    out = _run_node(_load_expr() + """
      process.stdout.write(JSON.stringify({
        evo: r.normalizeProvider('7k-bet-br.evo-games.com', null),
        evolution: r.normalizeProvider('live.evolutiongaming.com', null),
        prag: r.normalizeProvider('client.pragmaticplaylive.net', null),
        play: r.normalizeProvider('cdn.iconic21.com', null),
      }));
    """)
    assert out["evo"] == "evolution"
    assert out["evolution"] == "evolution"
    assert out["prag"] == "pragmatic"
    assert out["play"] == "playtech"


def test_unknown_instead_of_host_fallback():
    """O coracao do BUG-1: analytics / dashboard proprio -> 'unknown', NUNCA host:*."""
    out = _run_node(_load_expr() + """
      process.stdout.write(JSON.stringify({
        gtm: r.normalizeProvider('www.googletagmanager.com', null),
        dc: r.normalizeProvider('16089813.fls.doubleclick.net', null),
        dash: r.normalizeProvider('www.roleta.xma-ia.com', null),
        empty: r.normalizeProvider('', null),
      }));
    """)
    for v in out.values():
        assert v == "unknown"
        assert "host:" not in v


def test_clean_brand_passes_through_and_host_prefix_rejected():
    out = _run_node(_load_expr() + """
      process.stdout.write(JSON.stringify({
        clean: r.normalizeProvider('whatever', 'evolution'),
        hostRaw: r.normalizeProvider('www.googletagmanager.com', 'host:www.googletagmanager.com'),
      }));
    """)
    # marca limpa ja informada passa intacta
    assert out["clean"] == "evolution"
    # rawProvider 'host:*' e' ignorado e cai no dominio (analytics -> unknown)
    assert out["hostRaw"] == "unknown"


def test_has_useful_signal_blocks_analytics_frames():
    """BUG-5 (auditoria pos-reload): frame sem sinal real (provider unknown e sem
    dealer/table/round) NAO publica — evita sobrescrever o provider do jogo."""
    out = _run_node(_load_expr() + """
      const J = (m) => r.hasUsefulSignal(m);
      process.stdout.write(JSON.stringify({
        analytics: J({ provider: 'unknown', dealer: null, table: null, round_id: null }),
        knownProvider: J({ provider: 'evolution', dealer: null, table: null, round_id: null }),
        onlyDealer: J({ provider: 'unknown', dealer: 'LEVI', table: null, round_id: null }),
        onlyTable: J({ provider: 'unknown', dealer: null, table: 'PorROU1', round_id: null }),
        empty: J(null),
      }));
    """)
    assert out["analytics"] is False     # bloqueado
    assert out["knownProvider"] is True  # marca real publica
    assert out["onlyDealer"] is True     # dealer real publica
    assert out["onlyTable"] is True      # mesa real publica
    assert out["empty"] is False
