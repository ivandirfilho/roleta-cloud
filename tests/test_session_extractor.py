"""Tests for session_extractor.js (data-driven dealer/round/table capture - v18.2 Etapa 4)."""

import json
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "extension" / "session_extractor.js"
EXTRACTOR_JSON = REPO / "extrator_completo.json"


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


pytestmark = pytest.mark.skipif(not _node_available(), reason="Node.js required for session_extractor tests")


def test_session_extractor_loads():
    """Ensure helper exports both extractSessionData and combineSessionFrames."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      process.stdout.write(JSON.stringify({{
        hasExtract: typeof helper.extractSessionData,
        hasCombine: typeof helper.combineSessionFrames
      }}));
    """
    out = _run_node(script)
    assert out["hasExtract"] == "function"
    assert out["hasCombine"] == "function"


def test_extract_session_reads_dealer_from_primary_selector():
    """extractSessionData should use the primary selector when it matches."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fakeDoc = {{
        querySelector(sel) {{
          if (sel === '[data-role=dealer-name]') return {{ innerText: '  Maria  ', textContent: 'Maria' }};
          if (sel === '[data-role=game-id]')    return {{ innerText: 'R-12345' }};
          if (sel === '[data-role=game-title]') return {{ innerText: 'Roleta ao Vivo' }};
          return null;
        }}
      }};
      const cfg = {{
        dealer: {{ name: {{ selector: '[data-role=dealer-name]' }} }},
        round:  {{ id:   {{ selector: '[data-role=game-id]' }} }},
        table:  {{ name: {{ selector: '[data-role=game-title]' }} }}
      }};
      process.stdout.write(JSON.stringify(helper.extractSessionData(cfg, {{ document: fakeDoc }})));
    """
    out = _run_node(script)
    assert out["dealer"] == "Maria"
    assert out["round_id"] == "R-12345"
    assert out["table"] == "Roleta ao Vivo"


def test_extract_session_falls_back_when_primary_misses():
    """If primary selector returns nothing, fallbackSelectors are tried in order."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fakeDoc = {{
        querySelector(sel) {{
          if (sel === '[data-role=dealer-name]') return null;
          if (sel === '.dealer-name')           return null;
          if (sel === '[class*=presenter-name]') return {{ innerText: 'Joao da Silva' }};
          return null;
        }}
      }};
      const cfg = {{
        dealer: {{ name: {{
          selector: '[data-role=dealer-name]',
          fallbackSelectors: ['.dealer-name', '[class*=presenter-name]']
        }} }}
      }};
      process.stdout.write(JSON.stringify(helper.extractSessionData(cfg, {{ document: fakeDoc }})));
    """
    out = _run_node(script)
    assert out["dealer"] == "Joao da Silva"
    assert out["round_id"] is None
    assert out["table"] is None


def test_extract_session_respects_max_len():
    """maxLen should truncate captured strings to protect against runaway text nodes."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const longName = 'x'.repeat(500);
      const fakeDoc = {{ querySelector(sel) {{ return {{ innerText: longName }}; }} }};
      const cfg = {{ dealer: {{ name: {{ selector: '#x', maxLen: 50 }} }} }};
      process.stdout.write(JSON.stringify(helper.extractSessionData(cfg, {{ document: fakeDoc }})));
    """
    out = _run_node(script)
    assert len(out["dealer"]) == 50


def test_extract_session_uses_attribute_when_specified():
    """When attribute is set (e.g. 'data-round-id'), uses getAttribute instead of innerText."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fakeDoc = {{
        querySelector(sel) {{
          return {{
            innerText: 'wrong',
            getAttribute(name) {{ return name === 'data-round-id' ? '#R-7777' : null; }}
          }};
        }}
      }};
      const cfg = {{ round: {{ id: {{ selector: '#a', attribute: 'data-round-id' }} }} }};
      process.stdout.write(JSON.stringify(helper.extractSessionData(cfg, {{ document: fakeDoc }})));
    """
    out = _run_node(script)
    assert out["round_id"] == "#R-7777"


def test_extract_session_handles_throwing_selector():
    """If querySelector throws on a bad selector, subsequent fallbacks must still be tried."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fakeDoc = {{
        querySelector(sel) {{
          if (sel === 'bad>>>selector') throw new Error('SYNTAX_ERR');
          if (sel === '.good') return {{ innerText: 'recovered' }};
          return null;
        }}
      }};
      const cfg = {{ dealer: {{ name: {{
        selector: 'bad>>>selector',
        fallbackSelectors: ['.good']
      }} }} }};
      process.stdout.write(JSON.stringify(helper.extractSessionData(cfg, {{ document: fakeDoc }})));
    """
    out = _run_node(script)
    assert out["dealer"] == "recovered"


def test_extract_session_empty_config_yields_all_null():
    """Missing config or empty config returns an object with all session fields null."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fakeDoc = {{ querySelector(sel) {{ return {{ innerText: 'wrong' }}; }} }};
      process.stdout.write(JSON.stringify(helper.extractSessionData(undefined, {{ document: fakeDoc }})));
    """
    out = _run_node(script)
    assert out["dealer"] is None
    assert out["round_id"] is None
    assert out["table"] is None


def test_combine_session_frames_first_non_null_wins():
    """combineSessionFrames picks first non-null per field across frames (per-field independent)."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const frames = [
        {{ result: {{ dealer: null,   round_id: null,        table: null,        frameUrl: null }} }},
        {{ result: {{ dealer: 'Maria', round_id: null,        table: null,        frameUrl: 'https://a' }} }},
        {{ result: {{ dealer: 'Joao',  round_id: 'R-1',       table: 'Roleta',    frameUrl: 'https://b' }} }}
      ];
      process.stdout.write(JSON.stringify(helper.combineSessionFrames(frames)));
    """
    out = _run_node(script)
    assert out["dealer"] == "Maria"
    assert out["round_id"] == "R-1"
    assert out["table"] == "Roleta"
    assert out["frameUrl"] == "https://a"


def test_combine_session_frames_handles_empty_input():
    """Empty input must not crash; returns all-null shape."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      process.stdout.write(JSON.stringify(helper.combineSessionFrames([])));
    """
    out = _run_node(script)
    assert out == {"dealer": None, "round_id": None, "table": None, "frameUrl": None}


def test_extrator_completo_json_has_data_session_v18_2():
    """v18.2 must ship data.session with dealer/round/table selectors editable by operator."""
    data = json.loads(EXTRACTOR_JSON.read_text(encoding="utf-8"))
    assert data["_meta"]["version"] == "18.2.0"
    session = data["data"]["session"]
    assert "dealer" in session and session["dealer"]["name"]["selector"]
    assert "round" in session and session["round"]["id"]["selector"]
    assert "table" in session and session["table"]["name"]["selector"]
    assert isinstance(session["dealer"]["name"]["fallbackSelectors"], list)
    assert len(session["dealer"]["name"]["fallbackSelectors"]) >= 3


def test_extrator_completo_json_session_works_against_synthetic_dom():
    """End-to-end: configurar fakeDoc com seletores exatos do JSON v18.2 e checar captura."""
    data = json.loads(EXTRACTOR_JSON.read_text(encoding="utf-8"))
    session_cfg = data["data"]["session"]
    primary_dealer_sel = session_cfg["dealer"]["name"]["selector"]
    primary_round_sel = session_cfg["round"]["id"]["selector"]
    primary_table_sel = session_cfg["table"]["name"]["selector"]
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const cfg = {json.dumps(session_cfg)};
      const fakeDoc = {{
        querySelector(sel) {{
          if (sel === {json.dumps(primary_dealer_sel)}) return {{ innerText: 'Carla' }};
          if (sel === {json.dumps(primary_round_sel)})  return {{ innerText: '#999' }};
          if (sel === {json.dumps(primary_table_sel)})  return {{ innerText: 'Speed Roulette' }};
          return null;
        }}
      }};
      process.stdout.write(JSON.stringify(helper.extractSessionData(cfg, {{ document: fakeDoc }})));
    """
    out = _run_node(script)
    assert out["dealer"] == "Carla"
    assert out["round_id"] == "#999"
    assert out["table"] == "Speed Roulette"
