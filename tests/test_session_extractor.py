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


def test_extract_session_is_self_contained_under_mv3_injection():
    """DEAL-AUDIT 15/06 (regression): background.js injeta a função via
    chrome.scripting.executeScript({func: extractSessionData}), o que serializa
    APENAS o corpo (Function.prototype.toString) e o executa no contexto da pagina,
    SEM o closure do modulo. Se a funcao referenciar um helper externo
    (probeSelectors/cleanText), a pagina lanca ReferenceError e o dealer volta null
    para sempre. Este teste reconstroi a funcao a partir do toString e a executa
    isolada, usando o `document` GLOBAL (como em producao), sem passar opts."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fn = helper.extractSessionData;
      // Reconstroi a funcao a partir do texto serializado (== o que o Chrome injeta).
      const injected = new Function('return (' + fn.toString() + ')')();
      // document GLOBAL da "pagina" (a injecao real NAO passa opts.document).
      global.document = {{
        querySelector(sel) {{
          if (sel === "[data-role='dealer-name']") return {{ innerText: 'Maria Croupier' }};
          return null;
        }}
      }};
      global.location = {{ href: 'https://a8-latam.evo-games.com/x' }};
      const cfg = {{ dealer: {{ name: {{ selector: "[data-role='dealer-name']" }} }} }};
      let result;
      try {{ result = {{ ok: true, out: injected(cfg) }}; }}
      catch (e) {{ result = {{ ok: false, err: e.constructor.name + ': ' + e.message }}; }}
      process.stdout.write(JSON.stringify(result));
    """
    out = _run_node(script)
    assert out["ok"], f"injecao MV3 lancou erro (funcao nao self-contained): {out.get('err')}"
    assert out["out"]["dealer"] == "Maria Croupier"


def test_collect_dealer_candidates_when_selectors_miss():
    """DEAL-AUDIT 15/06: quando nenhum seletor de dealer casa, options.collectCandidates
    varre o DOM e devolve candidatos {cls,role,txt} (evidencia p/ afinar evolution.json
    sem chutar). Sem a flag, NAO coleta (custo zero no tick normal)."""
    el = "(cls, role, txt) => ({ children: [], className: cls, innerText: txt, getAttribute: (a) => (a === 'data-role' ? (role||'') : '') })"
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const el = {el};
      const nodes = [ el('header-title', '', 'Lobby'),
                      el('app_dealerName_x9', '', 'Maria Croupier'),
                      el('numbers-value', '', '17') ];
      const fakeDoc = {{ querySelector(s) {{ return null; }}, querySelectorAll(s) {{ return nodes; }} }};
      const cfg = {{ dealer: {{ name: {{ selector: "[data-role='dealer-name']" }} }} }};
      const withFlag = helper.extractSessionData(cfg, {{ document: fakeDoc, collectCandidates: true }});
      const noFlag   = helper.extractSessionData(cfg, {{ document: fakeDoc }});
      process.stdout.write(JSON.stringify({{ withFlag, noFlag }}));
    """
    out = _run_node(script)
    assert out["withFlag"]["dealer"] is None
    cands = out["withFlag"].get("dealerCandidates")
    assert isinstance(cands, list) and len(cands) >= 1
    assert "Maria Croupier" in [c["txt"] for c in cands]
    # 'numbers-value' nao casa a keyword de dealer/host/presenter -> nao deve entrar
    assert all("17" != c["txt"] for c in cands)
    # sem a flag, nao paga o custo de varrer o DOM
    assert "dealerCandidates" not in out["noFlag"]


def test_collect_candidates_is_self_contained_under_mv3_injection():
    """A varredura de candidatos tambem roda no contexto da pagina (injecao MV3);
    garante que usa apenas APIs nativas (sem helper de closure)."""
    el = "(cls, txt) => ({ children: [], className: cls, innerText: txt, getAttribute: () => '' })"
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const injected = new Function('return (' + helper.extractSessionData.toString() + ')')();
      const el = {el};
      global.document = {{ querySelector: () => null,
        querySelectorAll: () => [ el('chat-hostName', 'Joao Host') ] }};
      global.location = {{ href: 'https://a8-latam.evo-games.com/x' }};
      const cfg = {{ dealer: {{ name: {{ selector: "[data-role='dealer-name']" }} }} }};
      let result;
      try {{ result = {{ ok: true, out: injected(cfg, {{ collectCandidates: true }}) }}; }}
      catch (e) {{ result = {{ ok: false, err: e.constructor.name + ': ' + e.message }}; }}
      process.stdout.write(JSON.stringify(result));
    """
    out = _run_node(script)
    assert out["ok"], f"coleta nao self-contained sob injecao: {out.get('err')}"
    assert out["out"]["dealerCandidates"][0]["txt"] == "Joao Host"


def test_extract_session_marks_game_frame():
    """DEAL-AUDIT 15/06: o frame que contem os numeros da roleta
    ([data-role='recent-number']) deve ser marcado isGameFrame=true; um frame de
    lobby (sem numeros) deve ser false."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const gameDoc  = {{ querySelector(sel) {{ return sel === '[data-role="recent-number"]' ? {{}} : null; }} }};
      const lobbyDoc = {{ querySelector(sel) {{ return null; }} }};
      process.stdout.write(JSON.stringify({{
        game:  helper.extractSessionData({{}}, {{ document: gameDoc  }}).isGameFrame,
        lobby: helper.extractSessionData({{}}, {{ document: lobbyDoc }}).isGameFrame
      }}));
    """
    out = _run_node(script)
    assert out["game"] is True
    assert out["lobby"] is False


def test_combine_prioritizes_game_frame_over_lobby():
    """DEAL-AUDIT 15/06 (bug do table): o frame do jogo (isGameFrame=true) tem
    prioridade — evita capturar table/round/dealer de um frame de lobby/cross-sell
    (caso real em prod: table='Blackjack Silver D' numa sessao de roleta 'PorROU')."""
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const frames = [
        {{ result: {{ table: 'Blackjack Silver D', round_id: 'LOBBY-1', dealer: null,    frameUrl: 'https://lobby',     isGameFrame: false }} }},
        {{ result: {{ table: 'Roleta ao Vivo',     round_id: 'R-77',    dealer: 'Carla', frameUrl: 'https://evo-games', isGameFrame: true  }} }}
      ];
      process.stdout.write(JSON.stringify(helper.combineSessionFrames(frames)));
    """
    out = _run_node(script)
    assert out["table"] == "Roleta ao Vivo"
    assert out["round_id"] == "R-77"
    assert out["dealer"] == "Carla"
    assert out["frameUrl"] == "https://evo-games"
