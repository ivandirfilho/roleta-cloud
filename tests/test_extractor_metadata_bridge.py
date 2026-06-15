import json
import subprocess
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "extension" / "extractor_meta.js"
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


def test_extracts_provider_and_table_from_extractor_snapshot():
    script = f"""
      const fs = require('fs');
      const helper = require({json.dumps(str(HELPER))});
      const data = JSON.parse(fs.readFileSync({json.dumps(str(EXTRACTOR_JSON))}, 'utf8'));
      process.stdout.write(JSON.stringify(helper.extractDealMetaFromExtractorData(data)));
    """
    meta = _run_node(script)
    assert meta["provider"] == "evolution"
    assert meta["table"] == "PorROU0000000001"
    assert meta["dealer"] is None
    assert meta["round_id"] is None


def test_merge_preserves_dom_fields_while_filling_extractor_fields():
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const merged = helper.mergeDealMeta(
        {{ dealer: 'Alice', provider: 'host:betvip.bet.br', round_id: 'r-1' }},
        {{ provider: 'evolution', table: 'PorROU0000000001' }}
      );
      process.stdout.write(JSON.stringify(merged));
    """
    merged = _run_node(script)
    assert merged["dealer"] == "Alice"
    assert merged["provider"] == "evolution"
    assert merged["table"] == "PorROU0000000001"
    assert merged["round_id"] == "r-1"


def test_deal_audit_c2_reads_dealer_from_data_session():
    """DEAL-AUDIT C2 (14/06): extractDealMetaFromExtractorData passa a popular
    dealer/round_id quando v18.2+ trouxer data.session. Antes era hardcoded null.
    """
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fake = {{
        _meta: {{
          source: {{ url: 'https://betvip.bet.br/games/evolution/roleta' }},
          provider: {{ name: 'Evolution Gaming' }}
        }},
        _detectedFrames: {{ frames: [
          {{ url: 'https://a8-latam.evo-games.com/frontend/evo/r2/#provider=evolution&table_id=PorROU0000000001',
             isMainFrame: false, isEvolution: true, isPotentialGame: true }}
        ] }},
        data: {{
          session: {{
            dealer: {{ name: {{ value: 'Maria' }} }},
            round:  {{ id:   {{ value: 'R987654' }} }}
          }}
        }}
      }};
      process.stdout.write(JSON.stringify(helper.extractDealMetaFromExtractorData(fake)));
    """
    meta = _run_node(script)
    assert meta["dealer"] == "Maria"
    assert meta["round_id"] == "R987654"
    assert meta["table"] == "PorROU0000000001"
    assert meta["provider"] == "evolution"


def test_deal_audit_c2_returns_dealer_alone_when_only_session_present():
    """DEAL-AUDIT C2: helper deve retornar objeto quando só dealer foi capturado
    (antes exigia provider OR table). Garante que dealer puro nao é descartado.
    """
    script = f"""
      const helper = require({json.dumps(str(HELPER))});
      const fake = {{
        data: {{ session: {{ dealer: {{ name: {{ value: 'Carlos' }} }} }} }}
      }};
      process.stdout.write(JSON.stringify(helper.extractDealMetaFromExtractorData(fake)));
    """
    meta = _run_node(script)
    assert meta is not None
    assert meta["dealer"] == "Carlos"
    assert meta["provider"] is None
    assert meta["table"] is None
