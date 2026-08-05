"""Regression guards for the Azure pre-cutover runtime."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
AZURE = ROOT / "deploy" / "azure"


def _strategy_defaults(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    result: dict[str, str] = {}
    pattern = re.compile(
        r"^\s*-\s+([A-Z][A-Z0-9_]*)=\$\{([A-Z][A-Z0-9_]*):-([^}]*)\}",
        re.MULTILINE,
    )
    for key, reference, value in pattern.findall(text):
        assert key == reference
        if key.startswith(("SDA_", "GALE_", "C_")):
            result[key] = value
    return result


def test_azure_strategy_flags_match_live_production_contract():
    hostdime = _strategy_defaults(ROOT / "docker-compose.yml")
    azure = _strategy_defaults(AZURE / "compose.azure.yml")

    assert azure.keys() == hostdime.keys()
    assert azure["SDA_BET_PAIR"] == "v5_1721"
    assert azure["SDA_V5_SIG4"] == "1"
    assert azure["SDA_SUGESTAO_BROADCAST"] == "1"
    assert azure["SDA_V5_FLIP_PURO"] == "1"
    assert hostdime["SDA_DNA_REALIZE"] == "0"
    assert azure["SDA_DNA_REALIZE"] == "1"

    for key in azure.keys() - {"SDA_DNA_REALIZE"}:
        assert azure[key] == hostdime[key], key


def test_caddy_canary_restricts_websocket_writers():
    caddy = (AZURE / "Caddyfile").read_text(encoding="utf-8")
    staged = (AZURE / "kv-to-env.sh").read_text(encoding="utf-8")

    assert "remote_ip {$WS_ALLOWED_CIDRS:" in caddy
    assert 'handle /ws* {' in caddy
    assert 'respond "WebSocket indisponível neste endereço" 403' in caddy
    assert 'WS_ALLOWED_CIDRS="%s"' in staged
    assert "0.0.0.0/0 ::/0" in staged


def test_frontend_publish_is_readable_and_http_verified():
    deploy = (AZURE / "deploy-azure.sh").read_text(encoding="utf-8")

    assert 'chmod 0755 "$WWW_PARENT"' in deploy
    assert 'find "$FRONTEND_STAGE" -type d -exec chmod 0755' in deploy
    assert 'find "$FRONTEND_STAGE" -type f -exec chmod 0644' in deploy
    assert "frontend_http_ok" in deploy
    assert "frontend_rollback" in deploy
    assert "curl -fsS" in deploy


def test_blob_snapshots_commit_manifest_last_and_restore_by_manifest():
    backup = (AZURE / "backup-sqlite-to-blob.sh").read_text(encoding="utf-8")
    push = (AZURE / "hostdime-push-snapshot.sh").read_text(encoding="utf-8")
    restore = (AZURE / "restore-sqlite-from-blob.sh").read_text(encoding="utf-8")

    assert 'BLOB_PREFIX="${BLOB_PREFIX:-azure-local/}"' in backup
    assert backup.index('for f in "${payloads[@]}"') < backup.index('upload_file "$manifest"')
    assert push.index('for file in "${payloads[@]}"') < push.index('upload_blob "$MANIFEST"')
    assert "If-None-Match: *" in push
    assert "AZURE_STORAGE_SAS_TOKEN" in push
    assert 'STATE_PATH="$DATA_SOURCE/state.json"' in push
    assert backup.index('cp "$DATA_DIR/state.json" "$STATE_SNAPSHOT"') < backup.index(
        'python3 - "$TMP/decisions_$STAMP.db" "$STATE_SNAPSHOT"'
    )
    assert "MANIFEST_BLOBS" in restore
    assert "sha256sum -c" in restore
    assert "ACTIVE_ALIASES" in restore
    assert "docker volume inspect" in restore
    assert "restore no caminho ativo exige --stamp" in restore
    assert "sidecar SQLite presente" in restore
    assert "stamp $STAMP já aplicado e íntegro" in restore


def test_pre_cutover_units_and_probe_artifacts_exist():
    expected = (
        "systemd/roleta-azure-backup.service",
        "systemd/roleta-azure-backup.timer",
        "systemd/roleta-standby-sync.service",
        "systemd/roleta-standby-sync.timer",
        "systemd/roleta-hostdime-snapshot.service",
        "systemd/roleta-hostdime-snapshot.timer",
        "probe-realtime-persistence.sh",
        "ws-persistence-probe.py",
        "cutover-caddy.sh",
    )
    for relative in expected:
        assert (AZURE / relative).is_file(), relative

    probe = (AZURE / "probe-realtime-persistence.sh").read_text(encoding="utf-8")
    assert "/opt/roleta/probe-data" in probe
    assert "ROLETA_PG_DSN=" in probe
    assert "docker volume inspect" in probe
    assert "volume ativo mudou durante o probe" in probe
    assert "spin_seq não avançou sem gaps" in probe


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash não disponível")
def test_azure_shell_scripts_have_valid_syntax():
    scripts = sorted(AZURE.glob("*.sh"))
    result = subprocess.run(
        ["bash", "-n", *[str(path.relative_to(ROOT)) for path in scripts]],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode == 127 and "No such file or directory" in (
        result.stdout + result.stderr
    ):
        pytest.skip("bash não consegue traduzir o path deste worktree")
    assert result.returncode == 0, result.stderr


def test_websocket_probe_is_valid_python():
    source = (AZURE / "ws-persistence-probe.py").read_text(encoding="utf-8")
    compile(source, str(AZURE / "ws-persistence-probe.py"), "exec")
