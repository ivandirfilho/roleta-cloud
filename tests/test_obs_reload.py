"""OBS-INODE (05/08/2026) — regressao do bug operacional das regras Prometheus.

Incidente real: apos o deploy do SPR-V1, `obs/alerts.yml` no servidor tinha 21 regras e o
container `roleta-prometheus` continuava servindo 18. O deploy usa `git reset --hard`, que
reescreve arquivos via temp+rename (NOVO INODE), e a compose montava `obs/alerts.yml` como
bind DE ARQUIVO — que fixa o inode. `POST /-/reload` nao resolvia; so recriar o container.

Tres familias de teste:
  1. estaticos — a compose precisa continuar montando o DIRETORIO `obs/` (se alguem voltar
     ao bind de arquivo, o bug volta silencioso e nenhum outro teste percebe);
  2. entrypoint — o launcher instalado no host tem de continuar sendo um ponteiro para o
     script versionado (senao a copia em /usr/local congela de novo);
  3. funcionais — `scripts/obs-apply.sh` roda de verdade contra stubs COM ESTADO de
     `docker`/`curl` (timestamp de reload, bytes vistos pelo container, regras carregadas),
     cobrindo noop / reload / recriacao / frescor / promtool / pendencia / kill-switch.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSE_OBS = REPO / "docker-compose.obs.yml"
OBS_APPLY = REPO / "scripts" / "obs-apply.sh"
LAUNCHER = REPO / "scripts" / "roleta-deploy-launcher.sh"
INSTALLER = REPO / "scripts" / "roleta-deploy-install.sh"
DEPLOY = REPO / "scripts" / "roleta-deploy-pull.sh"
LEGACY_DEPLOY = REPO / "tools" / "deploy_pull.sh"

# Seam de evidencia: aponta a suite funcional para OUTRA versao do script
# (ex.: `git show 0db70f6:scripts/obs-apply.sh > /tmp/r1.sh`) para demonstrar
# quais regressoes reprovam contra a rodada anterior:
#   OBS_APPLY_UNDER_TEST=/tmp/r1.sh python -m pytest tests/test_obs_reload.py
OBS_APPLY_UNDER_TEST = Path(os.environ.get("OBS_APPLY_UNDER_TEST", str(OBS_APPLY)))

BASH = shutil.which("bash")


def _bash_path(path: Path) -> str | None:
    """Traduz um path do host para um path que o `bash` disponivel enxergue.

    Cobre Git-bash (C:/x) e WSL (/mnt/c/x); no Linux o proprio path ja serve.
    """
    if BASH is None:
        return None
    raw = str(path)
    candidates = [raw, raw.replace("\\", "/")]
    drive = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if drive:
        candidates.append(f"/mnt/{drive.group(1).lower()}/" + drive.group(2).replace("\\", "/"))
    for cand in candidates:
        try:
            probe = subprocess.run(
                [BASH, "-c", f'test -e "{cand}"'], capture_output=True, timeout=60
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if probe.returncode == 0:
            return cand
    return None


def _code(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


class TestComposeMountKeepsUpWithInodeSwap(unittest.TestCase):
    """O mount de diretorio e a raiz da correcao — travado aqui."""

    def setUp(self):
        self.text = COMPOSE_OBS.read_text(encoding="utf-8")
        block = re.search(r"\n  prometheus:\n(.*?)(?=\n  [a-z0-9_-]+:\n)", self.text, re.S)
        self.assertIsNotNone(block, "servico prometheus nao encontrado na compose de obs")
        self.prom = block.group(1)

    def test_monta_diretorio_obs(self):
        self.assertIn(
            "- ./obs:/etc/prometheus:ro",
            self.prom,
            "prometheus precisa montar o DIRETORIO obs/ (bind de arquivo prende o inode)",
        )

    def test_nao_ha_bind_de_arquivo_individual(self):
        for bad in ("./obs/prometheus.yml:", "./obs/alerts.yml:"):
            self.assertNotIn(
                bad,
                self.prom,
                f"bind de arquivo {bad} reintroduz o bug do inode preso (incidente 05/08/2026)",
            )

    def test_config_file_continua_dentro_do_mount(self):
        self.assertIn("--config.file=/etc/prometheus/prometheus.yml", self.prom)
        self.assertIn("--web.enable-lifecycle", self.prom)  # POST /-/reload

    def test_rule_files_apontam_para_dentro_do_mount(self):
        prom_yml = (REPO / "obs" / "prometheus.yml").read_text(encoding="utf-8")
        rules = re.search(r"^rule_files:\n((?:\s+-\s.*\n)+)", prom_yml, re.M)
        self.assertIsNotNone(rules, "rule_files ausente em obs/prometheus.yml")
        for line in rules.group(1).strip().splitlines():
            path = line.split("-", 1)[1].strip()
            self.assertTrue(
                path.startswith("/etc/prometheus/"),
                f"rule_file {path} fica fora do diretorio montado",
            )
            self.assertTrue(
                (REPO / "obs" / Path(path).name).exists(),
                f"rule_file {path} nao existe em obs/",
            )

    def test_volume_tsdb_nomeado_preservado(self):
        self.assertIn("- prometheus-data:/prometheus", self.prom)


class TestDeployEntrypoint(unittest.TestCase):
    """O entrypoint do host tem de ser um PONTEIRO, nao uma copia congelada."""

    def test_launcher_nao_tem_logica_de_deploy(self):
        body = _code(LAUNCHER.read_text(encoding="utf-8"))
        for forbidden in ("git reset", "docker compose", "alembic", "healthcheck"):
            self.assertNotIn(
                forbidden, body, "launcher tem de ficar minusculo (logica vive no repo)"
            )

    def test_launcher_executa_o_script_versionado(self):
        body = _code(LAUNCHER.read_text(encoding="utf-8"))
        self.assertIn("scripts/roleta-deploy-pull.sh", body)
        self.assertIn("exec bash", body)

    def test_duplicado_legado_delega(self):
        """Duas copias do deploy = divergencia garantida; a antiga so delega."""
        body = _code(LEGACY_DEPLOY.read_text(encoding="utf-8"))
        self.assertIn("exec bash", body)
        self.assertIn("scripts/roleta-deploy-pull.sh", body)
        self.assertNotIn("git reset", body)
        self.assertNotIn("docker compose", body)

    def test_docs_instalam_o_launcher(self):
        docs = (REPO / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertIn("roleta-deploy-launcher.sh", docs)
        self.assertIn("roleta-deploy-install.sh", docs)
        self.assertNotIn(
            "install -m755 tools/deploy_pull.sh",
            docs,
            "docs nao podem mandar instalar o duplicado legado",
        )

    def test_deploy_avisa_quando_o_entrypoint_esta_congelado(self):
        """O congelamento tem de ser VISIVEL no log, nunca silencioso."""
        body = DEPLOY.read_text(encoding="utf-8")
        code = _code(body)
        # a guarda e fixada junto com a chamada: so procurar pela chamada deixaria
        # passar um `if false` que desliga a sonda sem remover a linha
        self.assertIn(
            'if [ -f "$REPO_DIR/scripts/roleta-deploy-install.sh" ]; then',
            code,
            "sonda de drift desligada ou sem guarda",
        )
        probe = body.find("roleta-deploy-install.sh")
        self.assertGreater(probe, 0, "deploy nao sonda o entrypoint instalado")
        trecho = body[probe : probe + 200]
        self.assertIn("--check", trecho)
        self.assertIn("|| true", trecho, "a sonda tem de ser nao-fatal")

    def test_deploy_nao_se_auto_instala(self):
        """Um deploy que reescreve o proprio entrypoint fica irrecuperavel se o
        arquivo novo estiver quebrado — a correcao e um comando manual."""
        body = _code(DEPLOY.read_text(encoding="utf-8"))
        self.assertNotIn("roleta-deploy-install.sh install", body)
        self.assertNotIn("install -m755", body)

    def test_rollback_documentado_funciona_apos_revert(self):
        """O `git revert` remove os próprios scripts: os COMANDOS do rollback não
        podem depender de `obs-apply.sh` nem de `roleta-deploy-install.sh`."""
        docs = (REPO / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
        inicio = docs.find("### Rollback após `git revert`")
        self.assertGreater(inicio, 0, "falta a secao de rollback pos-revert")
        resto = docs[inicio + 10 :]
        fim = resto.find("\n## ")
        bloco = resto[: fim if fim > 0 else len(resto)]

        fence = re.search(r"```bash\n(.*?)```", bloco, re.S)
        self.assertIsNotNone(fence, "secao de rollback sem bloco de comandos")
        comandos = "\n".join(
            ln.strip()
            for ln in fence.group(1).splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )

        self.assertIn("docker compose", comandos, "rollback tem de recriar via compose")
        self.assertIn("--force-recreate", comandos)
        self.assertIn("--no-deps", comandos, "rollback nao pode tocar os outros containers")
        self.assertNotIn("--remove-orphans", comandos)
        for dependente in ("obs-apply.sh", "roleta-deploy-install.sh", "roleta-deploy-launcher.sh"):
            self.assertNotIn(
                dependente, comandos, f"{dependente} nao existe mais depois do revert"
            )
    def test_deploy_passa_repo_dir_para_a_sonda(self):
        """Bypass/checkout em path nao-default: a sonda tem de herdar o REPO_DIR."""
        body = DEPLOY.read_text(encoding="utf-8")
        probe = body.find("roleta-deploy-install.sh")
        trecho = body[max(0, probe - 120) : probe + 200]
        self.assertIn('REPO_DIR="$REPO_DIR"', trecho, "sonda sem REPO_DIR explicito")

    def test_unit_systemd_roda_a_sonda_de_forma_nao_fatal(self):
        """A copia congelada nunca executa a sonda versionada; a unit executa."""
        unit = (REPO / "tools" / "systemd" / "roleta-deploy.service").read_text(encoding="utf-8")
        linha = [ln for ln in unit.splitlines() if ln.startswith("ExecStartPre=")]
        self.assertTrue(linha, "unit sem sonda de drift")
        self.assertIn("roleta-deploy-install.sh --check", linha[0])
        self.assertTrue(
            linha[0].startswith("ExecStartPre=-"),
            "a sonda nao pode bloquear o deploy (falta o prefixo '-')",
        )

    def test_docs_dizem_que_a_sonda_nao_pega_o_congelamento_atual(self):
        docs = (REPO / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertIn("NÃO detecta o congelamento atual", docs)
        self.assertIn("OBRIGATÓRIO", docs, "bootstrap tem de estar marcado como obrigatorio")

    def test_unit_systemd_continua_apontando_para_usr_local(self):
        unit = (REPO / "tools" / "systemd" / "roleta-deploy.service").read_text(encoding="utf-8")
        self.assertIn("/usr/local/bin/roleta-deploy-pull.sh", unit)


class TestDeployScriptChamaObsApply(unittest.TestCase):
    def setUp(self):
        self.body = DEPLOY.read_text(encoding="utf-8")

    def test_hook_presente(self):
        for needle in ("obs-apply.sh", "obs_run apply", "obs_run check"):
            self.assertIn(needle, self.body)

    def test_pendencia_retomada_antes_do_gate_noop(self):
        """Sem isso, a falha some no tick seguinte (LOCAL==REMOTE -> exit 0)."""
        resume = self.body.find("obs_run resume")
        noop = self.body.find('if [ "$LOCAL" = "$REMOTE" ]')
        start = self.body.find("DEPLOY START")
        self.assertGreater(resume, noop, "resume precisa estar dentro do gate NOOP")
        self.assertLess(resume, start, "resume precisa vir antes do deploy normal")

    def test_falha_de_obs_e_explicita(self):
        self.assertIn("DEPLOY PARCIAL", self.body)

    def test_nunca_remove_orphans(self):
        self.assertNotIn("--remove-orphans", _code(OBS_APPLY.read_text(encoding="utf-8")))
        self.assertNotIn("--remove-orphans", _code(self.body))


@unittest.skipUnless(BASH, "bash nao disponivel")
class BashHarness(unittest.TestCase):
    """Base: repo git temporario + stubs COM ESTADO de docker/curl."""

    ALERTS_1 = "groups:\n  - name: r\n    rules:\n      - alert: A\n        expr: up == 0\n"
    ALERTS_2 = ALERTS_1 + "      - alert: B\n        expr: up == 1\n"
    PROM_YML = "global:\n  scrape_interval: 15s\nrule_files:\n  - /etc/prometheus/alerts.yml\n"
    COMPOSE_V0 = "services:\n  prometheus:\n    image: prom/prometheus:v2.51.2\n"
    # mudanca que NAO altera a definicao do servico prometheus: `up -d` vira no-op
    COMPOSE_V1 = COMPOSE_V0 + "  # comentario irrelevante para o servico\n"

    @classmethod
    def setUpClass(cls):
        if _bash_path(OBS_APPLY_UNDER_TEST) is None:
            raise unittest.SkipTest("bash nao consegue ler o path do repo (WSL/path translation)")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="obsapply-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        self.state = self.tmp / "state"
        self.ctr = self.tmp / "container"  # o que o CONTAINER enxerga
        self.bin = self.tmp / "bin"
        for d in (self.repo / "obs", self.repo / "scripts", self.state, self.ctr, self.bin):
            d.mkdir(parents=True, exist_ok=True)
        self.stub_log = self.tmp / "calls.log"
        self.stub_log.write_text("", encoding="utf-8")
        self.ts_file = self.tmp / "reload_ts"
        # epoch realista: o script usa o relogio do host como baseline quando o
        # /metrics nao responde, e container/host compartilham o mesmo clock
        self.ts_file.write_text(f"{int(time.time())}\n", encoding="utf-8", newline="\n")

        shutil.copyfile(OBS_APPLY_UNDER_TEST, self.repo / "scripts" / "obs-apply.sh")
        self._write_stubs()
        self._git_repo()

    # ---- fixture helpers -------------------------------------------------
    def _git(self, *args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(self.repo), *args], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()

    def _write_repo_files(self, alerts: str, compose: str):
        (self.repo / "obs" / "alerts.yml").write_text(alerts, encoding="utf-8", newline="\n")
        (self.repo / "obs" / "prometheus.yml").write_text(
            self.PROM_YML, encoding="utf-8", newline="\n"
        )
        (self.repo / "docker-compose.obs.yml").write_text(compose, encoding="utf-8", newline="\n")

    def _sync_container(self):
        """Container passa a enxergar exatamente o que esta no repo (inclui subdirs)."""
        shutil.rmtree(self.ctr, ignore_errors=True)
        shutil.copytree(self.repo / "obs", self.ctr)

    def _git_repo(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        self._write_repo_files(self.ALERTS_1, self.COMPOSE_V0)
        self._git("add", "-A")
        self._git("commit", "-qm", "v0")
        self.sha0 = self._git("rev-parse", "HEAD")
        self._sync_container()

    def _commit(self, msg: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-qm", msg)
        return self._git("rev-parse", "HEAD")

    def _write_stubs(self):
        bump = (
            'bump_ts() { if [ "${STUB_RELOAD_STICKY:-0}" = "1" ]; then return 0; fi; '
            'cur=$(cat "$STUB_TS_FILE" 2>/dev/null || echo 1000); '
            'echo $((cur + 1)) > "$STUB_TS_FILE"; }\n'
        )
        docker = """#!/bin/bash
echo "docker $*" >> "$STUB_LOG"
""" + bump + """args=" $* "
ctr_path_to_src() {
    # traduz um caminho do container para o diretorio que representa a visao dele
    local p="$1" root="$2" base sub
    base=$(basename "$p")
    sub=$(dirname "$p"); sub=${sub#/etc/prometheus}; sub=${sub#/}
    if [ -n "$sub" ]; then echo "$root/$sub/$base"; else echo "$root/$base"; fi
}
case "$args" in
    *" ps "*)
        if [ "${STUB_NO_PROM:-0}" = "1" ]; then exit "${STUB_PS_RC:-0}"; fi
        # `ps -a` inclui os containers efemeros do `compose run` (nome ordena antes)
        case "$args" in *" -aq "*|*" -a "*) echo "oneoff-run-999" ;; esac
        echo "ctr123"; exit 0 ;;
    *promtool*)
        if [ -n "${STUB_PROMTOOL_OUT:-}" ]; then echo "$STUB_PROMTOOL_OUT" >&2; fi
        exit "${STUB_PROMTOOL_RC:-0}" ;;
    *" up "*)
        case "$args" in
            *--force-recreate*)
                rc="${STUB_FORCE_UP_RC:-${STUB_UP_RC:-0}}"
                if [ "$rc" = "0" ]; then bump_ts; fi   # container novo carrega a config
                exit "$rc" ;;
        esac
        # `up -d` puro: se a definicao do servico nao mudou, e no-op (nao recarrega).
        # STUB_UP_RECREATES=1 simula o caso em que a definicao MUDOU (ex.: o mount
        # novo): o container e recriado e passa a enxergar o repo.
        if [ "${STUB_UP_RECREATES:-0}" = "1" ] && [ "${STUB_UP_RC:-0}" = "0" ]; then
            cp -r "$STUB_REPO_OBS"/. "$STUB_CTR_DIR"/ 2>/dev/null
            bump_ts
        fi
        exit "${STUB_UP_RC:-0}" ;;
    *" exec "*)
        # `docker exec` roda no MOUNT NAMESPACE do container: e a unica leitura que
        # mostra o que o PROCESSO enxerga (STUB_CTR_DIR).
        while [ "$#" -gt 0 ] && [ "$1" != "exec" ]; do shift; done
        shift
        while [ "$#" -gt 0 ]; do case "$1" in -*) shift ;; *) break ;; esac; done
        cid="${1:-}"; tool="${2:-}"; path="${3:-}"
        if [ "$cid" != "ctr123" ]; then exit 1; fi   # so o container EM EXECUCAO
        src=$(ctr_path_to_src "$path" "$STUB_CTR_DIR")
        if [ ! -f "$src" ]; then exit 1; fi
        case "$tool" in
            sha256sum)
                if [ "${STUB_NO_SHA256:-0}" = "1" ] || [ "${STUB_NO_READER:-0}" = "1" ]; then exit 126; fi
                sha256sum "$src" ;;
            cat)
                if [ "${STUB_NO_READER:-0}" = "1" ]; then exit 126; fi
                cat "$src" ;;
            *) exit 127 ;;
        esac
        exit 0 ;;
    *" cp "*)
        # `docker cp` NAO le pelo namespace do processo: para um bind mount o daemon
        # RE-RESOLVE o caminho de origem NO HOST. Por isso devolve os bytes NOVOS
        # mesmo com o container preso no inode antigo — verificar com isto seria
        # comparar host com host (tautologia).
        src_arg=""
        for a in "$@"; do case "$a" in *:/*) src_arg="${a#*:}" ;; esac; done
        src=$(ctr_path_to_src "$src_arg" "$STUB_REPO_OBS")
        if [ ! -f "$src" ]; then exit 1; fi
        tar -cf - -C "$(dirname "$src")" "$(basename "$src")"; exit 0 ;;
esac
exit 0
"""
        curl = """#!/bin/bash
echo "curl $*" >> "$STUB_LOG"
""" + bump + """url=""
for a in "$@"; do case "$a" in http*) url="$a" ;; esac; done
ts=$(cat "$STUB_TS_FILE" 2>/dev/null || echo 1000)
case "$url" in
    */-/reload)
        rc="${STUB_RELOAD_RC:-0}"
        if [ "$rc" = "0" ] || [ "${STUB_RELOAD_BUMP_ON_FAIL:-0}" = "1" ]; then bump_ts; fi
        exit "$rc" ;;
    */-/ready)
        n=0
        if [ -f "$STUB_READY_COUNT" ]; then n=$(cat "$STUB_READY_COUNT"); fi
        n=$((n + 1)); echo "$n" > "$STUB_READY_COUNT"
        if [ "$n" -le "${STUB_READY_FAILS:-0}" ]; then exit 7; fi
        exit "${STUB_READY_RC:-0}" ;;
    */metrics)
        echo "go_goroutines 42"
        echo "prometheus_config_last_reload_successful ${STUB_RELOAD_OK:-1}"
        echo "prometheus_config_last_reload_success_timestamp_seconds $ts"
        if [ "${STUB_BIG_METRICS:-1}" = "1" ]; then
            i=0
            while [ "$i" -lt 4000 ]; do
                echo "prometheus_tsdb_padding_metric_number_$i 1.2345678901234"
                i=$((i + 1))
            done
        fi
        exit 0 ;;
    */api/v1/rules)
        if [ "${STUB_RULES_STATUS:-success}" != "success" ]; then
            printf '{"status":"error"}'; exit 0
        fi
        n="${STUB_RULES_LOADED:-}"
        if [ -z "$n" ]; then
            # o que o CONTAINER enxerga (todos os rule files, inclusive subdirs)
            n=$(find "$STUB_CTR_DIR" -name '*.yml' ! -name 'prometheus.yml' -exec cat {} + 2>/dev/null \\
                | grep -cE '^[[:space:]]*-[[:space:]]*(alert|record):' || echo 0)
        fi
        printf '{"status":"success","data":{"groups":[{"name":"g","rules":['
        i=0
        while [ "$i" -lt "$n" ]; do
            if [ "$i" -gt 0 ]; then printf ','; fi
            printf '{"name":"A","query":"up == 0","type":"alerting"}'
            i=$((i + 1))
        done
        printf ']}]}}'
        exit 0 ;;
esac
exit 0
"""
        for name, body in (("docker", docker), ("curl", curl)):
            p = self.bin / name
            p.write_text(body, encoding="utf-8", newline="\n")
            os.chmod(p, 0o755)

    # ---- runner ----------------------------------------------------------
    def run_obs(self, *args: str, **env_over: str):
        """Executa obs-apply.sh via wrapper (env nao atravessa Windows->WSL)."""
        env = {
            "REPO_DIR": _bash_path(self.repo),
            "STATE_DIR": _bash_path(self.state),
            "DOCKER_BIN": _bash_path(self.bin / "docker"),
            "CURL_BIN": _bash_path(self.bin / "curl"),
            "STUB_LOG": _bash_path(self.stub_log),
            "STUB_CTR_DIR": _bash_path(self.ctr),
            "STUB_REPO_OBS": _bash_path(self.repo / "obs"),
            "STUB_TS_FILE": _bash_path(self.ts_file),
            "STUB_READY_COUNT": _bash_path(self.tmp) + "/ready_count",
            "VERIFY_RETRIES": "2",
            "VERIFY_INTERVAL": "0",
            "READY_TIMEOUT": "20",
            "READY_INTERVAL": "1",
        }
        env.update(env_over)
        for key, value in env.items():
            self.assertIsNotNone(value, f"path nao traduzivel para bash: {key}")
        exports = "\n".join(f'export {k}="{v}"' for k, v in env.items())
        script = _bash_path(self.repo / "scripts" / "obs-apply.sh")
        wrapper = self.tmp / "run.sh"
        wrapper.write_text(
            f'#!/bin/bash\n{exports}\nexec bash "{script}" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(wrapper, 0o755)
        return subprocess.run(
            [BASH, _bash_path(wrapper), *args], capture_output=True, text=True, timeout=300
        )

    def calls(self) -> str:
        return self.stub_log.read_text(encoding="utf-8")

    def reset_calls(self):
        self.stub_log.write_text("", encoding="utf-8")

    def pending(self) -> dict:
        p = self.state / "obs_pending"
        if not p.exists():
            return {}
        out = {}
        for line in p.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                out[k] = v
        return out

    def write_pending(self, action: str, escalated: str, sha: str):
        (self.state / "obs_pending").write_text(
            f"action={action}\nescalated={escalated}\nsha={sha}\n",
            encoding="utf-8",
            newline="\n",
        )


class TestObsApplyBasics(BashHarness):
    def test_sintaxe_bash(self):
        for path in (OBS_APPLY, DEPLOY, LEGACY_DEPLOY, LAUNCHER, INSTALLER):
            res = subprocess.run([BASH, "-n", _bash_path(path)], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"{path.name}: {res.stderr}")

    def test_deploy_sem_mudanca_de_obs_nao_toca_prometheus(self):
        (self.repo / "README.md").write_text("x\n", encoding="utf-8", newline="\n")
        sha1 = self._commit("nada de obs")
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("noop", res.stdout)
        self.assertEqual(self.calls().strip(), "", "Prometheus tocado num deploy sem obs")

    def test_alerts_mudou_valida_e_recarrega_sem_recriar(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()  # mount de diretorio: container ve o arquivo novo
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        self.assertIn("/bin/promtool", calls, "validou antes de aplicar?")
        self.assertIn("-X POST http://127.0.0.1:9090/-/reload", calls)
        self.assertNotIn(" up -d", calls, "reload nao pode recriar o container")
        self.assertEqual(self.pending(), {}, "pendencia deveria ter sido limpa")
        self.assertLess(
            calls.index("promtool"), calls.index("/-/reload"), "validacao tem de vir ANTES"
        )

    def test_check_isolado_nao_toca_container(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("check", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        self.assertIn("promtool", calls)
        self.assertNotIn("/-/reload", calls)
        self.assertNotIn(" up -d", calls)

    def test_resume_sem_pendencia_e_noop(self):
        res = self.run_obs("resume")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(self.calls().strip(), "")

    def test_host_sem_stack_pula_silenciosamente(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("skip", res.stdout)

    def test_host_sem_marcador_ainda_guarda_a_mudanca(self):
        """Primeira mudanca de obs num host sem `obs_seen`: se a stack estiver
        apenas temporariamente fora, descartar a mudanca a perderia para sempre."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 0, "host sem stack nao pode ser quebrado")
        self.assertEqual(self.pending().get("action"), "reload", "mudanca descartada sem pendencia")

        # a stack sobe: o tick seguinte aplica pela pendencia, sem depender do diff
        self.reset_calls()
        self._sync_container()
        res2 = self.run_obs("resume")
        self.assertEqual(res2.returncode, 0, res2.stdout + res2.stderr)
        self.assertEqual(self.pending(), {})

    def test_prometheus_que_sumiu_e_falha_nao_skip(self):
        (self.state / "obs_seen").write_text("prometheus\n", encoding="utf-8", newline="\n")
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 1, "stack que existia e sumiu nao pode virar sucesso")
        self.assertIn("fora do ar", res.stdout)

    def test_force_faz_bootstrap_do_mount_novo(self):
        """Bootstrap manual do host: recria mesmo sem diff (migracao do mount)."""
        self._sync_container()
        res = self.run_obs("force")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        self.assertIn("promtool", calls)
        forced = [c for c in calls.splitlines() if "--force-recreate" in c]
        self.assertEqual(len(forced), 1, "bootstrap recria uma unica vez")
        self.assertIn("/-/reload", calls, "recriacao tambem tem de recarregar")
        self.assertEqual(self.pending(), {})

    def test_reload_sem_sucesso_de_config_falha(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_RELOAD_OK="0")
        self.assertEqual(res.returncode, 1)
        self.assertIn("prometheus_config_last_reload_successful=0", res.stdout)

    def test_metrics_grande_nao_vira_falso_negativo(self):
        """`printf | grep -q` sob pipefail: grep sai no 1o match, produtor leva
        SIGPIPE(141) e a verificacao reprovava um reload que funcionou."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_BIG_METRICS="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("--force-recreate", self.calls(), "reload ok nao pode escalar")

    def test_verificacao_usa_container_em_execucao_nao_efemero(self):
        """`ps -a` traz os containers do `compose run`; verificar contra um deles
        (que monta o bind novo) devolveria sucesso com o Prometheus real velho."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        res = self.run_obs("apply", self.sha0, sha1)  # container real segue no velho
        self.assertEqual(res.returncode, 1, "verificou contra o container errado")
        for line in self.calls().splitlines():
            if " ps " in line:
                self.assertNotIn(" -aq", line, "listagem nao pode incluir containers efemeros")
                self.assertNotIn(" -a ", line)


class TestObsApplyIncidente(BashHarness):
    """O incidente literal e suas variantes de sucesso falso."""

    def test_inode_preso_e_detectado_e_escalado_uma_unica_vez(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        # container NAO sincronizado: continua lendo a versao antiga (inode preso)
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 1, "sucesso falso com container servindo bytes velhos")
        self.assertIn("divergencia", res.stdout)
        calls = self.calls()
        self.assertIn("/-/reload", calls)
        forced = [c for c in calls.splitlines() if "--force-recreate" in c]
        self.assertEqual(len(forced), 1, "escala para UMA recriacao ao detectar inode preso")
        self.assertEqual(self.pending().get("escalated"), "1")

        # tick seguinte (LOCAL==REMOTE): retoma sem recriar de novo -> sem loop
        self.reset_calls()
        res2 = self.run_obs("resume")
        self.assertEqual(res2.returncode, 1)
        self.assertNotIn("--force-recreate", self.calls(), "nao pode recriar a cada tick")

        # a recriacao resolve: o container passa a ler o arquivo novo
        self.reset_calls()
        self._sync_container()
        res3 = self.run_obs("resume")
        self.assertEqual(res3.returncode, 0, res3.stdout + res3.stderr)
        self.assertEqual(self.pending(), {}, "pendencia tem de ser limpa apos verificar")

    def test_regras_nao_carregadas_nao_e_sucesso(self):
        """Arquivo com 2 regras, API ainda com 1: exit NAO pode ser 0 (o incidente
        original era 21 no disco x 18 na API, com todo o resto parecendo saudavel)."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        self._sync_container()  # bytes batem; so a API ficou para tras
        res = self.run_obs("apply", self.sha0, sha1, STUB_RULES_LOADED="1")
        self.assertEqual(res.returncode, 1, "regras nao carregadas viraram sucesso")
        self.assertIn("arquivo=2 carregadas=1", res.stdout)

    def test_frescor_reload_que_nao_avanca_timestamp_reprova(self):
        """`prometheus_config_last_reload_successful` e sticky: continua 1 de um
        carregamento antigo. So o timestamp avancando prova que recarregou agora."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_RELOAD_STICKY="1")
        self.assertEqual(res.returncode, 1, "reload que nao aconteceu virou sucesso")
        self.assertIn("frescor", res.stdout)

    def test_recreate_sempre_recarrega(self):
        """`up -d` vira no-op quando a compose mudou sem alterar o servico
        (comentario, outro bloco). Sem reload depois, a regra nova nunca carrega —
        e ready + booleano sticky + bytes iguais fariam a verificacao passar."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V1)
        sha1 = self._commit("compose com comentario + regra nova")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        ups = [c for c in calls.splitlines() if " up -d" in c]
        self.assertEqual(len(ups), 1, f"recriacao tem de ser unica: {ups}")
        self.assertIn("--no-deps", ups[0], "so o prometheus pode ser tocado")
        self.assertNotIn("--remove-orphans", ups[0])
        self.assertIn(
            "-X POST http://127.0.0.1:9090/-/reload",
            calls,
            "todo up/recriacao tem de ser seguido de reload",
        )
        self.assertLess(
            calls.index(" up -d"), calls.index("/-/reload"), "reload vem DEPOIS do up"
        )


class TestVisaoDoContainer(BashHarness):
    """A leitura dos bytes tem de ser a do PROCESSO, nao a do daemon."""

    def test_bytes_lidos_pela_visao_do_container(self):
        """Bind de ARQUIVO com inode trocado: host tem NEW, o namespace do processo
        continua em OLD. `docker cp` mentiria (o daemon re-resolve o caminho no host
        e devolve NEW), então a comparação viraria host×host — tautologia."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras no host")
        # container preso no arquivo antigo (1 regra), mas a API "concorda" com o
        # arquivo novo: só a leitura pelo namespace pode denunciar a divergência
        res = self.run_obs("apply", self.sha0, sha1, STUB_RULES_LOADED="2")
        self.assertEqual(res.returncode, 1, "verificacao tautologica: leu o host, nao o container")
        self.assertIn("divergencia", res.stdout)
        self.assertNotIn("docker cp", self.calls(), "docker cp nao prova o que o processo le")

    def test_directory_bind_passa(self):
        """Mesmo cenário com mount de diretório: o container acompanha a troca de
        inode, os bytes batem e a verificação passa."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        self._sync_container()  # semantica do bind de DIRETORIO
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("--force-recreate", self.calls())

    def test_sem_leitor_no_container_falha_fechado(self):
        """Imagem sem sha256sum e sem cat: nao ha como provar o que o processo le."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_READER="1")
        self.assertEqual(res.returncode, 1, "sem leitor tem de reprovar, nao presumir sucesso")
        self.assertIn("visao do container", res.stdout)

    def test_fallback_para_cat_quando_nao_ha_sha256sum(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_SHA256="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


class TestEscaladaSoComEvidencia(BashHarness):
    """Recriar um Prometheus que servia a ultima config boa pode virar crash loop
    e reiniciar o WAL replay: so escala com evidencia de que recriar conserta."""

    def setUp(self):
        super().setUp()
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        self.sha1 = self._commit("2 regras")
        self._sync_container()

    def test_post_recusado_nao_recria(self):
        res = self.run_obs("apply", self.sha0, self.sha1, STUB_RELOAD_RC="7")
        self.assertEqual(res.returncode, 1)
        self.assertNotIn("--force-recreate", self.calls(), "POST recusado nao se conserta recriando")
        self.assertNotEqual(self.pending(), {})

    def test_reload_rejeitado_nao_recria(self):
        res = self.run_obs("apply", self.sha0, self.sha1, STUB_RELOAD_OK="0")
        self.assertEqual(res.returncode, 1)
        self.assertNotIn("--force-recreate", self.calls(), "config rejeitada viraria crash loop")
        self.assertIn("PROCESSO", res.stdout)

    def test_never_ready_nao_recria(self):
        res = self.run_obs(
            "apply", self.sha0, self.sha1, STUB_READY_RC="7", READY_TIMEOUT="2", READY_INTERVAL="1"
        )
        self.assertEqual(res.returncode, 1)
        self.assertNotIn(
            "--force-recreate", self.calls(), "recriar no meio de um WAL replay reinicia o replay"
        )

    def test_conteudo_divergente_ainda_escala(self):
        """O caminho legitimo da escalada continua valendo."""
        self.ctr.joinpath("alerts.yml").write_text(self.ALERTS_1, encoding="utf-8", newline="\n")
        res = self.run_obs("apply", self.sha0, self.sha1)
        self.assertEqual(res.returncode, 1)
        self.assertIn("--force-recreate", self.calls(), "assinatura do inode preso deve escalar")


class TestRuleFilesResolucao(BashHarness):
    """`rule_files` com glob/subpath: basename + sem glob dava 0 declarado."""

    PROM_GLOB = (
        "global:\n  scrape_interval: 15s\n"
        "rule_files:\n  - /etc/prometheus/alerts.yml\n  - /etc/prometheus/rules/*.yml\n"
    )

    def test_glob_e_subdiretorio_sao_resolvidos(self):
        (self.repo / "obs" / "rules").mkdir()
        (self.repo / "obs" / "rules" / "extra.yml").write_text(
            "groups:\n  - name: x\n    rules:\n      - alert: C\n        expr: up == 2\n",
            encoding="utf-8",
            newline="\n",
        )
        (self.repo / "obs" / "prometheus.yml").write_text(
            self.PROM_GLOB, encoding="utf-8", newline="\n"
        )
        (self.repo / "obs" / "alerts.yml").write_text(
            self.ALERTS_2, encoding="utf-8", newline="\n"
        )
        sha1 = self._commit("regras em subdir por glob")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("arquivo=3 carregadas=3", res.stdout, "glob/subdir nao entrou na contagem")
        # o byte-check tem de cobrir os arquivos resolvidos, nao so alerts.yml
        self.assertIn("/etc/prometheus/rules/extra.yml", self.calls())

    def test_glob_sem_correspondencia_falha_fechado(self):
        (self.repo / "obs" / "prometheus.yml").write_text(
            self.PROM_GLOB, encoding="utf-8", newline="\n"
        )
        (self.repo / "obs" / "alerts.yml").write_text(
            self.ALERTS_2, encoding="utf-8", newline="\n"
        )
        sha1 = self._commit("glob que nao casa com nada")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 1, "0 declarado nao pode ser tratado como sucesso")
        self.assertIn("sem correspondencia", res.stdout + res.stderr)
        self.assertNotIn(
            "--force-recreate", self.calls(), "config quebrada nao se conserta recriando"
        )

    def test_rule_file_fora_do_mount_falha(self):
        (self.repo / "obs" / "prometheus.yml").write_text(
            "global:\n  scrape_interval: 15s\nrule_files:\n  - /var/lib/outro/a.yml\n",
            encoding="utf-8",
            newline="\n",
        )
        sha1 = self._commit("rule_file fora do mount")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 1)
        self.assertIn("fora do diretorio montado", res.stdout + res.stderr)


class TestObsApplyPendencia(BashHarness):
    def test_pendencia_escalada_nao_engole_recreate_novo(self):
        """`escalated` de um reload antigo nao pode rebaixar uma troca real de mount."""
        self.write_pending("reload", "1", self.sha0)
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V1)
        sha1 = self._commit("mount novo")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn(" up -d", self.calls(), "mudanca de compose foi pulada pela pendencia")

    def test_escalated_com_reload_falho_nao_vira_sucesso(self):
        """`do_reload || true` engolia o POST falho e ainda limpava a pendencia.

        Cenario deliberadamente cruel: tudo o MAIS parece saudavel (bytes batem,
        regras batem e o timestamp ate avancou, porque outra coisa recarregou a
        config) — o unico sinal de que a aplicacao nao aconteceu e o POST recusado.
        """
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")
        self._sync_container()
        self.write_pending("reload", "1", sha1)
        res = self.run_obs(
            "apply", self.sha0, sha1, STUB_RELOAD_RC="7", STUB_RELOAD_BUMP_ON_FAIL="1"
        )
        self.assertEqual(res.returncode, 1, "POST falho virou sucesso")
        self.assertIn("FAIL POST /-/reload", res.stdout)
        self.assertNotEqual(self.pending(), {}, "falha nao pode limpar a pendencia")

    def test_kill_switch_preserva_pendencia(self):
        """OBS_ENABLED=0 e pausa operacional, nao 'esquece o que faltava aplicar'."""
        self.write_pending("recreate", "0", self.sha0)
        res = self.run_obs("resume", OBS_ENABLED="0")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.pending().get("action"), "recreate", "kill-switch apagou a pendencia")
        self.assertEqual(self.calls().strip(), "", "kill-switch nao pode tocar no Prometheus")

    def test_kill_switch_grava_a_mudanca_detectada(self):
        """Pausa com mudanca NOVA: sem gravar a pendencia, ao religar o tick tem
        LOCAL==REMOTE, nada para retomar e a mudanca se perde em silencio."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V1)
        sha1 = self._commit("mount novo + regra nova")
        res = self.run_obs("apply", self.sha0, sha1, OBS_ENABLED="0")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(
            self.pending().get("action"), "recreate", "pausa descartou a mudanca detectada"
        )
        self.assertEqual(self.calls().strip(), "")

        # religou: o tick seguinte (LOCAL==REMOTE) retoma pela pendencia
        self.reset_calls()
        self._sync_container()
        res2 = self.run_obs("resume")
        self.assertEqual(res2.returncode, 0, res2.stdout + res2.stderr)
        self.assertIn(" up -d", self.calls())
        self.assertEqual(self.pending(), {})

    def test_stack_fora_do_ar_grava_a_pendencia(self):
        """O deploy ja fez `git reset --hard`: se a mudanca nao virar pendencia,
        o proximo tick sai 0 (systemd volta a success) e os diffs seguintes nao
        contem mais aquela mudanca — perda silenciosa."""
        (self.state / "obs_seen").write_text("prometheus\n", encoding="utf-8", newline="\n")
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("regra nova")
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(self.pending().get("action"), "reload", "falha nao deixou pendencia")

        # Prometheus voltou: o tick seguinte aplica sem depender do diff antigo
        self.reset_calls()
        self._sync_container()
        res2 = self.run_obs("resume")
        self.assertEqual(res2.returncode, 0, res2.stdout + res2.stderr)
        self.assertIn("/-/reload", self.calls())
        self.assertEqual(self.pending(), {})

    def test_recriacao_que_falha_nao_tranca_a_pendencia(self):
        """Marcar `escalated` antes do `up` dar certo trancaria a pendencia num
        estado que so faz reload — e reload nao conserta inode preso."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")  # container fica no arquivo velho
        res = self.run_obs("apply", self.sha0, sha1, STUB_FORCE_UP_RC="1")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(self.pending().get("escalated"), "0", "pendencia trancada sem recriar")

        self.reset_calls()
        self._sync_container()
        res2 = self.run_obs("resume")
        self.assertEqual(res2.returncode, 0, res2.stdout + res2.stderr)
        self.assertEqual(self.pending(), {})

    def test_pendencia_no_formato_antigo_e_lida(self):
        (self.state / "obs_pending").write_text("escalated\n", encoding="utf-8", newline="\n")
        self._sync_container()
        res = self.run_obs("resume")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("retomando pendencia", res.stdout)

    def test_resume_de_pendencia_antiga_recria_quando_preciso(self):
        """O marcador antigo `escalated` representa um episodio que precisou de
        RECRIACAO. Lido como `reload`, um `resume` nunca recria — e reload nao
        conserta inode preso: fica falhando a cada 2 min para sempre."""
        (self.state / "obs_pending").write_text("escalated\n", encoding="utf-8", newline="\n")
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        self._commit("2 regras")  # container fica no arquivo velho
        res = self.run_obs("resume", STUB_UP_RECREATES="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn(" up -d", self.calls(), "pendencia antiga foi rebaixada para reload")
        self.assertEqual(self.pending(), {})

    def test_pendencia_antiga_sem_sha_nao_bloqueia_a_recriacao(self):
        """O marcador antigo `escalated` so era gravado apos uma recriacao (logo,
        acao = recreate) e nao carrega SHA. Se ele for lido como `reload` ou se a
        ausencia de SHA pular o reset de episodio, o inode preso fica sem conserto
        por episodios inteiros — falhando a cada 2 min sem nunca recriar."""
        (self.state / "obs_pending").write_text("escalated\n", encoding="utf-8", newline="\n")
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("2 regras")  # container fica no arquivo velho
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "--force-recreate",
            self.calls(),
            "episodio novo tem de poder recriar apesar da pendencia antiga",
        )


class TestObsApplyOperacional(BashHarness):
    def test_promtool_inexecutavel_nao_derruba_o_deploy_do_app(self):
        """`check` reprovado faz o deploy dar `git reset --hard`: so rejeicao de
        sintaxe COMPROVADA pode chegar la (daemon fora/imagem ausente nao)."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        env = dict(
            STUB_PROMTOOL_RC="125",
            STUB_PROMTOOL_OUT="docker: Error response from daemon: no space left on device",
        )
        res = self.run_obs("check", self.sha0, sha1, **env)
        self.assertEqual(res.returncode, 0, "indisponibilidade operacional derrubou o deploy")
        self.assertIn("INDISPONIVEL", res.stdout)
        # o apply, esse sim, sinaliza a falha
        res2 = self.run_obs("apply", self.sha0, sha1, **env)
        self.assertEqual(res2.returncode, 1)
        self.assertNotEqual(self.pending(), {}, "pendencia mantida para o proximo tick")

    def test_config_invalida_comprovada_reprova_o_check(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("regra quebrada")
        res = self.run_obs(
            "check",
            self.sha0,
            sha1,
            STUB_PROMTOOL_RC="1",
            STUB_PROMTOOL_OUT="  FAILED: parsing YAML file /etc/prometheus/alerts.yml",
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("config INVALIDA", res.stdout)
        self.assertNotIn("/-/reload", self.calls(), "nao pode recarregar config invalida")

    def test_check_nao_derruba_deploy_quando_a_stack_esta_fora(self):
        (self.state / "obs_seen").write_text("prometheus\n", encoding="utf-8", newline="\n")
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("check", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        res2 = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res2.returncode, 1)

    def test_startup_lento_nao_forca_recriacao(self):
        """WAL replay: /-/ready demora. Confundir 'ainda subindo' com 'nao aplicou'
        recriaria o container no meio do replay, repetidamente."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_READY_FAILS="8")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("--force-recreate", self.calls(), "recriou durante o WAL replay")
        self.assertIn("ready apos", res.stdout)

    def test_prometheus_que_nunca_fica_ready_falha(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()
        res = self.run_obs(
            "apply", self.sha0, sha1, STUB_READY_RC="7", READY_TIMEOUT="2", READY_INTERVAL="1"
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("nao ficou ready", res.stdout)

    def test_git_diff_quebrado_nao_vira_noop(self):
        """Deteccao que falha em silencio esconde justamente o deploy que precisava
        do reload — a acao conservadora e assumir que mudou."""
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        self._commit("nova regra")
        self._sync_container()
        res = self.run_obs("apply", "0000000000000000000000000000000000000000", "HEADHEAD")
        self.assertIn("WARN", res.stdout, "falha de deteccao tem de ser explicita")
        self.assertNotEqual(self.calls().strip(), "", "noop silencioso apos git diff quebrado")

    def test_api_de_regras_invalida_nao_e_sucesso(self):
        self._write_repo_files(self.ALERTS_2, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_RULES_STATUS="error")
        self.assertEqual(res.returncode, 1)
        self.assertIn("status=success", res.stdout)


@unittest.skipUnless(BASH, "bash nao disponivel")
class TestLauncherRuntime(unittest.TestCase):
    """O launcher tem de rodar SEMPRE a versao do repo (anti-drift)."""

    @classmethod
    def setUpClass(cls):
        if _bash_path(LAUNCHER) is None:
            raise unittest.SkipTest("bash nao consegue ler o path do repo")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="launcher-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        self.target = self.repo / "scripts" / "roleta-deploy-pull.sh"
        # copia "instalada" em /usr/local, que NAO deve ser atualizada nunca mais
        self.installed = self.tmp / "usr-local-roleta-deploy-pull.sh"
        shutil.copyfile(LAUNCHER, self.installed)

    def _run(self, *args: str):
        wrapper = self.tmp / "run.sh"
        wrapper.write_text(
            "#!/bin/bash\n"
            f'export REPO_DIR="{_bash_path(self.repo)}"\n'
            f'exec bash "{_bash_path(self.installed)}" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(wrapper, 0o755)
        return subprocess.run(
            [BASH, _bash_path(wrapper), *args], capture_output=True, text=True, timeout=120
        )

    def test_roda_a_versao_do_repo_e_acompanha_mudancas(self):
        self.target.write_text(
            '#!/bin/bash\necho "VERSAO-1 args=$*"\n', encoding="utf-8", newline="\n"
        )
        res = self._run("apply", "x")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("VERSAO-1 args=apply x", res.stdout)

        # deploy novo chega pelo git: a copia instalada NAO muda, mas o comportamento sim
        self.target.write_text('#!/bin/bash\necho "VERSAO-2"\n', encoding="utf-8", newline="\n")
        res2 = self._run()
        self.assertIn("VERSAO-2", res2.stdout, "launcher congelou a versao antiga (drift)")

    def test_propaga_codigo_de_saida(self):
        self.target.write_text("#!/bin/bash\nexit 3\n", encoding="utf-8", newline="\n")
        self.assertEqual(self._run().returncode, 3)

    def test_falha_explicita_se_o_checkout_sumir(self):
        res = self._run()
        self.assertEqual(res.returncode, 1)
        self.assertIn("LAUNCHER FAIL", res.stderr)


@unittest.skipUnless(BASH, "bash nao disponivel")
class TestInstaladorDoEntrypoint(unittest.TestCase):
    """Bootstrap/atualizacao do entrypoint: idempotente, auditavel e reversivel."""

    @classmethod
    def setUpClass(cls):
        if _bash_path(INSTALLER) is None:
            raise unittest.SkipTest("bash nao consegue ler o path do repo")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="installer-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copyfile(LAUNCHER, self.repo / "scripts" / "roleta-deploy-launcher.sh")
        shutil.copyfile(INSTALLER, self.repo / "scripts" / "roleta-deploy-install.sh")
        self.entrypoint = self.tmp / "usr-local" / "roleta-deploy-pull.sh"
        self.entrypoint.parent.mkdir(parents=True)
        self.backup_dir = self.tmp / "backup"

    def _run(self, *args: str, **env_over: str):
        extra = "\n".join(f'export {k}="{v}"' for k, v in env_over.items())
        wrapper = self.tmp / "run.sh"
        wrapper.write_text(
            "#!/bin/bash\n"
            f'export REPO_DIR="{_bash_path(self.repo)}"\n'
            f'export ENTRYPOINT="{_bash_path(self.entrypoint.parent)}/roleta-deploy-pull.sh"\n'
            f'export BACKUP_DIR="{_bash_path(self.backup_dir.parent)}/backup"\n'
            f"{extra}\n"
            f'exec bash "{_bash_path(self.repo / "scripts" / "roleta-deploy-install.sh")}" "$@"\n',
            encoding="utf-8",
            newline="\n",
        )
        os.chmod(wrapper, 0o755)
        return subprocess.run(
            [BASH, _bash_path(wrapper), *args], capture_output=True, text=True, timeout=120
        )

    def _freeze_copy(self):
        """Estado real de producao hoje: uma copia congelada do deploy."""
        self.entrypoint.write_text(
            "#!/bin/bash\n# copia congelada do deploy\necho antigo\n",
            encoding="utf-8",
            newline="\n",
        )

    def test_check_detecta_copia_congelada(self):
        self._freeze_copy()
        res = self._run("--check")
        self.assertEqual(res.returncode, 1, "copia congelada precisa ser sinalizada")
        self.assertIn("DRIFT", res.stdout)
        self.assertIn("roleta-deploy-install.sh", res.stdout, "log tem de dizer como corrigir")

    def test_check_distingue_launcher_desatualizado_de_copia_congelada(self):
        """Hash diferente NAO prova que o deploy versionado parou de chegar: um
        launcher de outra versao continua fazendo `exec` do script do repo."""
        antigo = LAUNCHER.read_text(encoding="utf-8") + "\n# variacao de versao anterior\n"
        self.entrypoint.write_text(antigo, encoding="utf-8", newline="\n")
        res = self._run("--check")
        self.assertEqual(res.returncode, 0, "launcher desatualizado nao e drift")
        self.assertIn("DESATUALIZADO", res.stdout)
        self.assertNotIn("DRIFT", res.stdout)

        # ja uma copia SEM o marcador continua sendo drift
        self._freeze_copy()
        res2 = self._run("--check")
        self.assertEqual(res2.returncode, 1)
        self.assertIn("DRIFT", res2.stdout)

    def test_check_e_silencioso_quando_esta_em_dia(self):
        """Roda a cada tick (ExecStartPre + fim do deploy): nao pode poluir o log."""
        self._run()  # instala
        res = self._run("--check")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "", "sonda em dia nao pode logar a cada 2 min")

    def test_check_verboso_quando_pedido(self):
        self._run()
        res = self._run("--check", OBS_VERBOSE="1")
        self.assertEqual(res.returncode, 0)
        self.assertIn("ok", res.stdout)

    def test_check_nao_escreve_nada(self):
        self._freeze_copy()
        antes = self.entrypoint.read_bytes()
        self._run("--check")
        self.assertEqual(self.entrypoint.read_bytes(), antes, "--check tem de ser read-only")

    def test_instala_com_backup_e_e_idempotente(self):
        self._freeze_copy()
        congelado = self.entrypoint.read_bytes()

        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(
            self.entrypoint.read_bytes(),
            LAUNCHER.read_bytes(),
            "entrypoint tem de virar o launcher versionado",
        )
        backup = self.backup_dir.parent / "backup" / "roleta-deploy-pull.sh.bak"
        self.assertTrue(backup.exists(), "sem backup nao ha rollback")
        self.assertEqual(backup.read_bytes(), congelado)
        self.assertEqual(self._run("--check").returncode, 0)

        # idempotencia: segunda passada nao reescreve nada
        mtime = self.entrypoint.stat().st_mtime_ns
        res2 = self._run()
        self.assertEqual(res2.returncode, 0)
        self.assertIn("nada a fazer", res2.stdout)
        self.assertEqual(self.entrypoint.stat().st_mtime_ns, mtime)

    def test_rollback_restaura_o_entrypoint_anterior(self):
        self._freeze_copy()
        congelado = self.entrypoint.read_bytes()
        self._run()
        res = self._run("--rollback")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.entrypoint.read_bytes(), congelado)

    def test_instala_quando_nao_existe_entrypoint(self):
        res = self._run()
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertEqual(self.entrypoint.read_bytes(), LAUNCHER.read_bytes())

    def test_modo_desconhecido_falha(self):
        self.assertEqual(self._run("--zzz").returncode, 2)


if __name__ == "__main__":
    unittest.main()
