"""Regression tests for the MIG-0 state persistence path."""

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_compose_keeps_state_in_the_persistent_volume():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "roleta-data:/app/data" in compose
    assert "STATE_FILE=/app/data/state.json" in compose
    assert "./state.json:/app/state.json" not in compose
    assert "stop_grace_period: 60s" in compose


def test_deploy_scripts_fail_closed_before_state_migration():
    for relative_path in (
        "scripts/roleta-deploy-pull.sh",
        "tools/deploy_pull.sh",
    ):
        deploy_script = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "STATE MIGRATION REQUIRED" in deploy_script
        assert "docker volume inspect" in deploy_script
        assert "docker compose config --format json" in deploy_script
        assert "docker volume ls" in deploy_script
        assert "state.json" in deploy_script


def test_deploy_and_resume_paths_guard_before_starting_the_new_app():
    canonical = (ROOT / "scripts/roleta-deploy-pull.sh").read_text(encoding="utf-8")
    legacy = (ROOT / "tools/deploy_pull.sh").read_text(encoding="utf-8")
    resume = (ROOT / "scripts/resume_app.sh").read_text(encoding="utf-8")

    assert canonical.index("if ! assert_state_volume_ready") < canonical.index(
        'docker compose run --rm "$SERVICE" alembic upgrade head'
    )
    legacy_guard = legacy.index("if ! assert_state_volume_ready")
    legacy_guard = legacy[legacy_guard : legacy.index("\nfi", legacy_guard)]
    assert 'docker compose build --quiet "$SERVICE" || true' in legacy_guard
    assert 'docker compose up -d "$SERVICE" || true' in legacy_guard
    assert resume.index("assert_state_volume_ready\n") < resume.index("docker compose up -d")


def test_state_file_is_overridable_by_environment(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    monkeypatch.setenv("STATE_FILE", str(state_path))

    from app_config.settings import Settings

    assert Settings().state_file == state_path


def test_explicit_missing_state_file_fails_closed(monkeypatch, tmp_path):
    state_path = tmp_path / "missing-state.json"
    monkeypatch.setenv("STATE_FILE", str(state_path))

    from app_config.settings import settings
    from state.game import GameState

    monkeypatch.setattr(settings, "state_file", state_path)
    with pytest.raises(FileNotFoundError, match="STATE_FILE"):
        GameState.load()
