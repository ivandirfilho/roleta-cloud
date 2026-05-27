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
