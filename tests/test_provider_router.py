"""Tests for provider_router.js (auto-detecção / zero-upload — v3.3, passos_escuta_junho §4.9)."""

import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "extension" / "provider_router.js"


def _run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "-e", script],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def _node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = pytest.mark.skipif(not _node_available(), reason="Node.js required for provider_router tests")


def _load_expr() -> str:
    return f"const r = require({json.dumps(str(HELPER))});"


def test_router_loads():
    script = _load_expr() + """
      process.stdout.write(JSON.stringify({
        hasMatch: typeof r.matchHostToProvider,
        hasDetectUrl: typeof r.detectFromUrl,
        hasDetectFrames: typeof r.detectFromFrames,
        hasScore: typeof r.scoreProvider,
        hasManifestPath: typeof r.manifestPathFor,
        providers: r.PROVIDER_DETECTION.map(p => p.id)
      }));
    """
    out = _run_node(script)
    assert out["hasMatch"] == "function"
    assert out["hasDetectUrl"] == "function"
    assert out["hasDetectFrames"] == "function"
    assert out["hasScore"] == "function"
    assert "evolution" in out["providers"]


def test_match_host_evolution():
    script = _load_expr() + """
      process.stdout.write(JSON.stringify({
        evo: r.matchHostToProvider('a8-latam.evo-games.com'),
        evolution: r.matchHostToProvider('live.evolutiongaming.com'),
        prag: r.matchHostToProvider('client.pragmaticplaylive.net'),
        play: r.matchHostToProvider('cdn.iconic21.com'),
        none: r.matchHostToProvider('betvip.bet.br')
      }));
    """
    out = _run_node(script)
    assert out["evo"] == "evolution"
    assert out["evolution"] == "evolution"
    assert out["prag"] == "pragmatic"
    assert out["play"] == "playtech"
    assert out["none"] is None


def test_detect_from_url_full():
    script = _load_expr() + """
      process.stdout.write(JSON.stringify({
        a: r.detectFromUrl('https://a8-latam.evo-games.com/frontend/evo/r1'),
        b: r.detectFromUrl('https://google.com')
      }));
    """
    out = _run_node(script)
    assert out["a"] == "evolution"
    assert out["b"] is None


def test_detect_from_frames_evolution_iframe():
    """Main page is the operator site; the game lives in an evo-games iframe."""
    script = _load_expr() + """
      const frames = [
        'https://betvip.bet.br/games/evolution/roleta-ao-vivo',
        'https://a8-latam.evo-games.com/frontend/evo/r1'
      ];
      process.stdout.write(JSON.stringify(r.detectFromFrames(frames)));
    """
    out = _run_node(script)
    assert out["providerId"] == "evolution"
    assert out["confidence"] >= 0.6
    assert out["ambiguous"] is False


def test_detect_from_frames_unknown():
    script = _load_expr() + """
      process.stdout.write(JSON.stringify(r.detectFromFrames([
        'https://betvip.bet.br/home', 'https://google.com/ads'
      ])));
    """
    out = _run_node(script)
    assert out["providerId"] is None
    assert out["confidence"] == 0


def test_detect_from_frames_ambiguous_is_rejected():
    """Two providers tied -> ambiguous -> providerId null (NB-03)."""
    script = _load_expr() + """
      process.stdout.write(JSON.stringify(r.detectFromFrames([
        'https://x.evo-games.com/r1',
        'https://y.pragmaticplaylive.net/g2'
      ])));
    """
    out = _run_node(script)
    assert out["ambiguous"] is True
    assert out["providerId"] is None


def test_irrelevant_host():
    script = _load_expr() + """
      process.stdout.write(JSON.stringify({
        g: r.isIrrelevantHost('www.google.com'),
        e: r.isIrrelevantHost('a8-latam.evo-games.com')
      }));
    """
    out = _run_node(script)
    assert out["g"] is True
    assert out["e"] is False


def test_score_provider_weighted():
    script = _load_expr() + """
      process.stdout.write(JSON.stringify({
        urlOnly: r.scoreProvider({ url: true }),
        all: r.scoreProvider({ url: true, dom: 1, meta: true }),
        none: r.scoreProvider({})
      }));
    """
    out = _run_node(script)
    assert out["urlOnly"] == pytest.approx(0.5, abs=0.01)
    assert out["all"] == pytest.approx(1.0, abs=0.01)
    assert out["none"] == 0


def test_manifest_path_and_availability():
    script = _load_expr() + """
      process.stdout.write(JSON.stringify({
        path: r.manifestPathFor('evolution'),
        evoAvail: r.getProvider('evolution').available,
        pragAvail: r.getProvider('pragmatic').available,
        missing: r.manifestPathFor('nope')
      }));
    """
    out = _run_node(script)
    assert out["path"] == "providers/evolution.json"
    assert out["evoAvail"] is True
    assert out["pragAvail"] is False
    assert out["missing"] is None
