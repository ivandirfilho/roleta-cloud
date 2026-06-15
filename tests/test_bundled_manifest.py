"""Tests for bundled provider manifests + manifest.json wiring (auto-start / zero-upload v3.3)."""

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
EXT = REPO / "extension"
PROVIDERS = EXT / "providers"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_evolution_manifest_bundled():
    """providers/evolution.json must exist, parse and carry the v18.2 session block."""
    manifest = _load(PROVIDERS / "evolution.json")
    assert manifest["_meta"]["service"] == "ExtractorBeat"
    # zero-upload depends on the data-driven session block (v18.2) being preserved
    assert "session" in manifest["data"]
    # detection metadata used by provider_router
    assert manifest["_detection"]["provider_id"] == "evolution"
    assert any("evo-games" in p for p in manifest["_detection"]["hostPatterns"])


def test_index_registry_consistent():
    index = _load(PROVIDERS / "index.json")
    providers = {p["id"]: p for p in index["providers"]}
    assert "evolution" in providers
    assert providers["evolution"]["available"] is True
    # every available provider must point to a bundled file that exists
    for p in index["providers"]:
        if p.get("available"):
            assert (EXT / p["path"]).exists(), f"missing bundled manifest for {p['id']}"


def test_manifest_json_wiring():
    """manifest.json must expose providers via web_accessible_resources + webNavigation perm."""
    mf = _load(EXT / "manifest.json")
    assert "webNavigation" in mf["permissions"]
    war = mf.get("web_accessible_resources", [])
    flat = [res for entry in war for res in entry.get("resources", [])]
    assert any("providers/" in r for r in flat)
    # version bumped to the auto-start release
    assert mf["version"].startswith("3.3")


def test_detection_hosts_match_deal_capture():
    """Registry host patterns must cover the providers known to deal_capture.js."""
    index = _load(PROVIDERS / "index.json")
    ids = {p["id"] for p in index["providers"]}
    # deal_capture.js knows these four providers
    assert {"evolution", "pragmatic", "playtech", "imagine"}.issubset(ids)
