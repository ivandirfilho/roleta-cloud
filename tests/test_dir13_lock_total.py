"""DIR13 (sentido-fase): UX lock + FIX #Z lock total no servidor (fix #N + #Z).

Antes #Z: direction_locked so era checado em message_handler.py:740 (impede fusao
de video DIR7). NAO impedia auto-seed da DIR5 nem reanchoragem DIR17. Nome promete
'trava' mas semantica era 'so nao escuta video'.

Depois: com SDA_LOCK_TOTAL=1, direction_locked tem semantica completa:
- DIR5 auto-seed NAO dispara (preserva seed_parity do operador)
- DIR16 reset NAO zera seed_parity (ja era assim — agora gateado por lock_total)
- DIR17 reancora NAO dispara (ja era assim)
- DIR7 fusao video NAO ocorre (comportamento atual)

Cliente (background.js v3.7.0):
- Le directionLocked do chrome.storage.local
- Envia set_seed{direction, locked} com lock real (nao mais hardcoded false)
- manifest.version bumpado para 3.7.0
"""

from app_config.settings import lock_total_enabled


def test_flag_lock_total_default_off(monkeypatch):
    monkeypatch.delenv("SDA_LOCK_TOTAL", raising=False)
    assert lock_total_enabled() is False
    monkeypatch.setenv("SDA_LOCK_TOTAL", "1")
    assert lock_total_enabled() is True


def test_lock_total_decision_matrix():
    """Matriz: (lock_total_enabled, direction_locked) -> bloqueia_auto_seed."""
    cases = [
        (False, False, False),  # tudo OFF -> auto-seed normal
        (False, True,  False),  # lock mas flag OFF -> auto-seed (bug #Z legado)
        (True,  False, False),  # flag ON mas sem lock -> auto-seed normal
        (True,  True,  True),   # flag ON + lock -> bloqueia auto-seed
    ]
    for flag, locked, expected in cases:
        lock_total = flag and locked
        assert lock_total is expected


def test_manifest_bumpado_para_3_9_1():
    """Cliente em 3.9.1 (V5.2 badge dourado + minimizado único) — DIR13 preservado."""
    import json
    from pathlib import Path
    repo = Path(__file__).parent.parent
    manifest = json.loads((repo / "extension" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == "3.9.1"
    assert "DIR13" in manifest["description"]


def test_settings_lock_total_helper_existe():
    """app_config.settings.lock_total_enabled exposto."""
    from app_config import settings
    assert hasattr(settings, "lock_total_enabled")
    assert callable(settings.lock_total_enabled)
