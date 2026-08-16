"""SPR-D1 — contratos do self-heal do tick NOOP e da observabilidade do nginx.

O incidente de 16/08 ficou indiagnosticavel de fora por dois motivos, e este
arquivo trava os dois:

1. `roleta.conf` nao expunha `/health` — a unica sonda externa possivel era o
   proprio `/ws`, que so diz "502" sem distinguir "app morto" de "nginx sem a
   location". Os testes de conf garantem que a sonda continue existindo.
2. `scripts/roleta-deploy-pull.sh` saia `exit 0` no tick NOOP sem olhar para o
   app: container caido ficava caido ate o proximo merge. Os testes funcionais
   exercitam `self_heal_tick()` com stubs, cobrindo tambem os dois freios que
   impedem o self-heal de brigar com uma pausa deliberada.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO / "scripts" / "roleta-deploy-pull.sh"
NGINX_CONF = REPO / "roleta.conf"

BASH = shutil.which("bash")


def _bash(script: str, *args: str) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, newline="\n") as fh:
        fh.write(script)
        path = fh.name
    try:
        return subprocess.run(
            [BASH, path, *args], capture_output=True, text=True, timeout=120
        )
    finally:
        Path(path).unlink(missing_ok=True)


# Exercita o bloco de self-heal do script real com sondas e `docker` stubados.
# Os stubs vem DEPOIS do `source` de proposito: precisam sobrescrever as funcoes
# reais, nao ser sobrescritos por elas.
HARNESS = r"""
set -uo pipefail
SRC="$1"
BLOCK="$(mktemp)"
awk '/^# >>> SPR-D1 SELF-HEAL BEGIN/{f=1} /^# <<< SPR-D1 SELF-HEAL END/{f=0} f' "$SRC" > "$BLOCK"
# Guard de SUB-captura: os marcadores sumiram/mudaram.
grep -q 'self_heal_tick()' "$BLOCK" || { echo "BLOCO-NAO-EXTRAIDO"; exit 90; }
# Guard de SOBRE-captura: se o marcador final nao casar, o awk levaria ate o EOF e
# o `source` abaixo executaria o fluxo de deploy REAL (git reset --hard) no
# checkout de quem roda o teste. Barrar antes de sourcear e inegociavel.
if grep -qE 'git reset --hard|git fetch|docker compose build|alembic upgrade' "$BLOCK"; then
    echo "BLOCO-EXCEDIDO"; exit 91
fi

STATE_DIR="$(mktemp -d)"
SELF_HEAL_PAUSED_FILE="$STATE_DIR/self_heal_paused"
HEALTH_URL="http://127.0.0.1:8766/health"
HEALTH_RETRIES=2
HEALTH_INTERVAL=0
SERVICE="roleta-cloud"
SELF_HEAL=1
WS_PROBE_HOST=127.0.0.1
WS_PROBE_PORT=8765
WS_PROBE_TIMEOUT=1
log() { :; }

# shellcheck disable=SC1090
source "$BLOCK"

HEALTH_OK=1; WS_OK=1; STATE="running:0:false"; UP_OK=1; HEAL_AFTER_UP=1; UP_CALLS=0
probe_health_http()  { [ "$HEALTH_OK" = "1" ]; }
probe_ws_handshake() { [ "$WS_OK" = "1" ]; }
container_state()    { echo "$STATE"; }
docker() {
    if [ "${1:-}" = "compose" ]; then
        UP_CALLS=$((UP_CALLS+1))
        if [ "$UP_OK" = "1" ]; then
            if [ "$HEAL_AFTER_UP" = "1" ]; then HEALTH_OK=1; WS_OK=1; fi
            return 0
        fi
        return 1
    fi
    return 0
}

fail=0
scenario() { # nome rc_esperado ups_esperados
    UP_CALLS=0
    self_heal_tick >/dev/null 2>&1
    local rc=$?
    if [ "$rc" = "$2" ] && [ "$UP_CALLS" = "$3" ]; then
        echo "PASS  $1"
    else
        echo "FAIL  $1 (rc=$rc esperado $2 | up=$UP_CALLS esperado $3)"; fail=1
    fi
}

HEALTH_OK=1; WS_OK=1; STATE="running:0:false"
scenario "saudavel = no-op silencioso" 0 0

HEALTH_OK=1; WS_OK=0; STATE="running:0:false"; HEAL_AFTER_UP=1
scenario "handshake WS falha com health vivo -> cura" 0 1

HEALTH_OK=0; WS_OK=0; STATE="exited:1:false"; HEAL_AFTER_UP=1
scenario "crash (exit 1) -> cura" 0 1

HEALTH_OK=0; WS_OK=0; STATE="missing:0:false"; HEAL_AFTER_UP=1
scenario "container ausente -> cura" 0 1

HEALTH_OK=0; WS_OK=0; STATE="exited:137:true"; HEAL_AFTER_UP=1
scenario "OOM killer (137 OOMKilled) -> cura" 0 1

HEALTH_OK=0; WS_OK=0; STATE="exited:0:false"
scenario "parada graciosa (exit 0) -> stand-down" 0 0

HEALTH_OK=0; WS_OK=0; STATE="exited:143:false"
scenario "SIGTERM (143, docker stop) -> stand-down" 0 0

HEALTH_OK=0; WS_OK=0; STATE="exited:137:false"
scenario "SIGKILL pos-grace (137 sem OOM) -> stand-down" 0 0

HEALTH_OK=0; WS_OK=0; STATE="exited:1:false"; : > "$SELF_HEAL_PAUSED_FILE"
scenario "sentinela de pausa -> stand-down" 0 0
rm -f "$SELF_HEAL_PAUSED_FILE"

HEALTH_OK=0; WS_OK=0; STATE="exited:1:false"; SELF_HEAL=0
scenario "SELF_HEAL=0 -> desligado" 0 0
SELF_HEAL=1

HEALTH_OK=0; WS_OK=0; STATE="restarting:1:false"; HEAL_AFTER_UP=0
scenario "crash-loop persistente -> rc!=0 (unit failed)" 1 1

HEALTH_OK=0; WS_OK=0; STATE="exited:1:false"; UP_OK=0
scenario "docker up falha -> rc!=0 (unit failed)" 1 1

rm -rf "$STATE_DIR" "$BLOCK"
exit $fail
"""


class TestNginxObservability(unittest.TestCase):
    """A sonda externa que faltava no incidente de 16/08."""

    @classmethod
    def setUpClass(cls):
        cls.conf = NGINX_CONF.read_text(encoding="utf-8")

    def test_health_location_existe_e_aponta_para_8766(self):
        self.assertIn("location = /health", self.conf)
        health = self.conf.split("location = /health", 1)[1][:600]
        self.assertIn("proxy_pass http://127.0.0.1:8766", health)

    def test_metrics_nao_fica_publico(self):
        self.assertIn("location = /metrics", self.conf)
        metrics = self.conf.split("location = /metrics", 1)[1][:600]
        self.assertIn("deny all", metrics)

    def test_ws_continua_no_8765(self):
        self.assertIn("location /ws", self.conf)
        self.assertIn("proxy_pass http://127.0.0.1:8765", self.conf)


class TestSelfHealContrato(unittest.TestCase):
    """O tick NOOP nao pode mais sair 0 com o app fora do ar."""

    @classmethod
    def setUpClass(cls):
        cls.src = DEPLOY_SH.read_text(encoding="utf-8")

    def test_tick_noop_chama_self_heal(self):
        """O ramo `LOCAL == REMOTE` nao pode mais sair 0 sem olhar para o app."""
        self.assertIn('if [ "$LOCAL" = "$REMOTE" ]; then', self.src)
        ramo = self.src.split('if [ "$LOCAL" = "$REMOTE" ]; then', 1)[1].split("\nfi\n", 1)[0]
        self.assertIn("self_heal_tick", ramo)
        # e o exit 0 do NOOP so pode vir DEPOIS da cura
        self.assertLess(ramo.index("self_heal_tick"), ramo.index("exit 0"))

    def test_sonda_cobre_as_duas_portas(self):
        """A sonda WS precisa exigir handshake, nao só TCP-connect (docker-proxy)."""
        self.assertIn("probe_ws_handshake", self.src)
        self.assertIn("101", self.src)
        self.assertIn("8765", self.src)
        self.assertIn("HEALTH_URL", self.src)
        self.assertNotIn("probe_ws_tcp", self.src)

    def test_stand_down_cobre_sinais_de_parada(self):
        """137 sem OOM e 143 vêm de `docker stop`; 137 com OOM é outage real."""
        self.assertIn("deliberate_stop", self.src)
        self.assertIn("OOMKilled", self.src)
        for pat in ("exited:0:", "exited:143:", "exited:137:true", "exited:137:"):
            with self.subTest(pat=pat):
                self.assertIn(pat, self.src)

    def test_sentinelas_do_harness_existem(self):
        """Sem os dois marcadores o teste funcional sourceia o deploy real."""
        self.assertIn("# >>> SPR-D1 SELF-HEAL BEGIN", self.src)
        self.assertIn("# <<< SPR-D1 SELF-HEAL END", self.src)

    def test_kill_switch_e_sentinela_existem(self):
        self.assertIn("SELF_HEAL", self.src)
        self.assertIn("SELF_HEAL_PAUSED_FILE", self.src)

    def test_pause_resume_gerenciam_a_sentinela(self):
        pause = (REPO / "scripts" / "pause_app.sh").read_text(encoding="utf-8")
        resume = (REPO / "scripts" / "resume_app.sh").read_text(encoding="utf-8")
        self.assertIn("self_heal_paused", pause)
        self.assertIn("self_heal_paused", resume)

    def test_runbook_existe(self):
        self.assertTrue((REPO / "docs" / "runbooks" / "servidor-502-glassbox.md").exists())


@unittest.skipUnless(BASH, "bash nao disponivel")
class TestSelfHealFuncional(unittest.TestCase):
    """Executa self_heal_tick() de verdade, com sondas e docker stubados."""

    def test_sintaxe_bash(self):
        for rel in (
            "scripts/roleta-deploy-pull.sh",
            "scripts/pause_app.sh",
            "scripts/resume_app.sh",
        ):
            with self.subTest(script=rel):
                r = subprocess.run(
                    [BASH, "-n", str(REPO / rel)], capture_output=True, text=True
                )
                if r.returncode == 127:
                    self.skipTest("bash nao consegue ler o path (WSL/path translation)")
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_cenarios(self):
        r = _bash(HARNESS, str(DEPLOY_SH))
        if r.returncode == 90:
            self.fail(
                "harness nao conseguiu extrair o bloco de self-heal — as sentinelas "
                "'# >>> SPR-D1 SELF-HEAL BEGIN/END' mudaram"
            )
        if r.returncode == 91:
            self.fail(
                "a extracao passou do bloco de self-heal e capturou o fluxo de deploy "
                "(git reset --hard). A sentinela final '# <<< SPR-D1 SELF-HEAL END' "
                "deve fechar o bloco ANTES de `cd \"$REPO_DIR\"`"
            )
        if r.returncode == 127 or "No such file or directory" in r.stderr:
            self.skipTest("bash nao consegue ler o path (WSL/path translation)")
        self.assertEqual(r.returncode, 0, f"{r.stdout}\n{r.stderr}")
        self.assertIn("PASS", r.stdout)
        self.assertNotIn("FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main()
