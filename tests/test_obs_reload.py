"""OBS-INODE (05/08/2026) — regressao do bug operacional das regras Prometheus.

Incidente real: apos o deploy do SPR-V1, `obs/alerts.yml` no servidor tinha 21 regras e o
container `roleta-prometheus` continuava servindo 18. O deploy usa `git reset --hard`, que
reescreve arquivos via temp+rename (NOVO INODE), e a compose montava `obs/alerts.yml` como
bind DE ARQUIVO — que fixa o inode. `POST /-/reload` nao resolvia; so recriar o container.

Duas familias de teste:
  1. estaticos — a compose precisa continuar montando o DIRETORIO `obs/` (se alguem voltar
     ao bind de arquivo, o bug volta silencioso e nenhum outro teste percebe);
  2. funcionais — `scripts/obs-apply.sh` roda de verdade contra stubs de `docker`/`curl`,
     cobrindo noop / reload / recriacao / promtool reprovado / INODE PRESO / pendencia.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COMPOSE_OBS = REPO / "docker-compose.obs.yml"
OBS_APPLY = REPO / "scripts" / "obs-apply.sh"

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


class TestComposeMountKeepsUpWithInodeSwap(unittest.TestCase):
    """O mount de diretorio e a raiz da correcao — travado aqui."""

    def setUp(self):
        self.text = COMPOSE_OBS.read_text(encoding="utf-8")
        # bloco do servico prometheus (ate o proximo servico no mesmo nivel)
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


class TestDeployScriptsChamamObsApply(unittest.TestCase):
    def setUp(self):
        self.scripts = {
            name: (REPO / name).read_text(encoding="utf-8")
            for name in ("scripts/roleta-deploy-pull.sh", "tools/deploy_pull.sh")
        }

    def test_hook_presente_nos_dois_scripts(self):
        for name, body in self.scripts.items():
            self.assertIn("obs-apply.sh", body, f"{name} nao chama o passo de observabilidade")
            self.assertIn("obs_run apply", body, name)
            self.assertIn("obs_run check", body, name)

    def test_pendencia_retomada_antes_do_gate_noop(self):
        """Sem isso, a falha some no tick seguinte (LOCAL==REMOTE -> exit 0)."""
        for name, body in self.scripts.items():
            resume = body.find("obs_run resume")
            noop = body.find('if [ "$LOCAL" = "$REMOTE" ]')
            start = body.find("DEPLOY START")
            self.assertGreater(resume, noop, f"{name}: resume precisa estar dentro do gate NOOP")
            self.assertLess(resume, start, f"{name}: resume precisa vir antes do deploy normal")

    def test_falha_de_obs_e_explicita(self):
        for name, body in self.scripts.items():
            self.assertIn("DEPLOY PARCIAL", body, f"{name}: falha de obs sem sinal explicito")

    def test_nunca_remove_orphans(self):
        def code_lines(text: str) -> str:
            return "\n".join(
                ln for ln in text.splitlines() if not ln.lstrip().startswith("#")
            )

        self.assertNotIn("--remove-orphans", code_lines(OBS_APPLY.read_text(encoding="utf-8")))
        for name, script in self.scripts.items():
            self.assertNotIn("--remove-orphans", code_lines(script), name)


@unittest.skipUnless(BASH, "bash nao disponivel")
class TestObsApplyRuntime(unittest.TestCase):
    """Roda o script de verdade contra stubs de `docker` e `curl`."""

    ALERTS_V0 = "groups:\n  - name: r\n    rules:\n      - alert: A\n        expr: up == 0\n"
    ALERTS_V1 = (
        "groups:\n  - name: r\n    rules:\n      - alert: A\n        expr: up == 0\n"
        "      - alert: B\n        expr: up == 1\n"
    )
    PROM_YML = "global:\n  scrape_interval: 15s\nrule_files:\n  - /etc/prometheus/alerts.yml\n"
    COMPOSE_V0 = "services:\n  prometheus:\n    image: prom/prometheus:v2.51.2\n"
    COMPOSE_V1 = COMPOSE_V0 + "    mem_limit: 512m\n"

    @classmethod
    def setUpClass(cls):
        if _bash_path(OBS_APPLY) is None:
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

        shutil.copyfile(OBS_APPLY, self.repo / "scripts" / "obs-apply.sh")
        self._write_stubs()
        self._git_repo()

    # ---- fixture helpers -------------------------------------------------
    def _git(self, *args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()

    def _write_repo_files(self, alerts: str, compose: str):
        (self.repo / "obs" / "alerts.yml").write_text(alerts, encoding="utf-8", newline="\n")
        (self.repo / "obs" / "prometheus.yml").write_text(
            self.PROM_YML, encoding="utf-8", newline="\n"
        )
        (self.repo / "docker-compose.obs.yml").write_text(compose, encoding="utf-8", newline="\n")

    def _sync_container(self):
        """Container passa a enxergar exatamente o que esta no repo."""
        for name in ("alerts.yml", "prometheus.yml"):
            shutil.copyfile(self.repo / "obs" / name, self.ctr / name)

    def _git_repo(self):
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, capture_output=True)
        self._git("config", "user.email", "t@t")
        self._git("config", "user.name", "t")
        self._write_repo_files(self.ALERTS_V0, self.COMPOSE_V0)
        self._git("add", "-A")
        self._git("commit", "-qm", "v0")
        self.sha0 = self._git("rev-parse", "HEAD")
        self._sync_container()

    def _commit(self, msg: str) -> str:
        self._git("add", "-A")
        self._git("commit", "-qm", msg)
        return self._git("rev-parse", "HEAD")

    def _write_stubs(self):
        docker = """#!/bin/bash
echo "docker $*" >> "$STUB_LOG"
args=" $* "
case "$args" in
    *" ps "*)
        if [ "${STUB_NO_PROM:-0}" = "1" ]; then exit "${STUB_PS_RC:-0}"; fi
        # `ps -a` inclui os containers efemeros do `compose run` (nome ordena antes)
        case "$args" in *" -aq "*|*" -a "*) echo "oneoff-run-999" ;; esac
        echo "ctr123"; exit 0 ;;
    *promtool*)  exit "${STUB_PROMTOOL_RC:-0}" ;;
    *" up "*)
        case "$args" in
            *--force-recreate*) exit "${STUB_FORCE_UP_RC:-${STUB_UP_RC:-0}}" ;;
        esac
        exit "${STUB_UP_RC:-0}" ;;
    *" cp "*)
        # simula o que o CONTAINER enxerga: tar do arquivo em $STUB_CTR_DIR.
        # Um container efemero do `run` enxergaria SEMPRE o bind novo -> se o script
        # verificar contra ele, o falso sucesso volta.
        src=""
        for a in "$@"; do case "$a" in *:/*) src="${a#*:}" ;; esac; done
        case " $* " in
            *oneoff-run*) dir="$STUB_REPO_OBS" ;;
            *)            dir="$STUB_CTR_DIR" ;;
        esac
        base=$(basename "$src")
        if [ ! -f "$dir/$base" ]; then exit 1; fi
        tar -cf - -C "$dir" "$base"; exit 0 ;;
esac
exit 0
"""
        curl = """#!/bin/bash
echo "curl $*" >> "$STUB_LOG"
url=""
for a in "$@"; do case "$a" in http*) url="$a" ;; esac; done
case "$url" in
    */-/reload) exit "${STUB_RELOAD_RC:-0}" ;;
    */-/ready)  exit "${STUB_READY_RC:-0}" ;;
    */metrics)
        # /metrics real tem centenas de KB e a metrica aparece CEDO: reproduz o
        # cenario de SIGPIPE que quebrava `printf | grep -q` sob pipefail.
        echo "go_goroutines 42"
        echo "prometheus_config_last_reload_successful ${STUB_RELOAD_OK:-1}"
        if [ "${STUB_BIG_METRICS:-1}" = "1" ]; then
            i=0
            while [ "$i" -lt 4000 ]; do
                echo "prometheus_tsdb_padding_metric_number_$i 1.2345678901234"
                i=$((i + 1))
            done
        fi
        exit 0 ;;
    */api/v1/rules) printf '%s' "${STUB_RULES_JSON:-}"; exit 0 ;;
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
            "VERIFY_RETRIES": "1",
            "VERIFY_INTERVAL": "0",
        }
        env.update(env_over)
        for key, value in env.items():
            self.assertIsNotNone(value, f"path nao traduzivel para bash: {key}")
        exports = "\n".join(f'export {k}="{v}"' for k, v in env.items())
        script = _bash_path(self.repo / "scripts" / "obs-apply.sh")
        wrapper = self.tmp / "run.sh"
        wrapper.write_text(
            f'#!/bin/bash\n{exports}\nexec bash "{script}" "$@"\n',
            encoding="utf-8", newline="\n",
        )
        os.chmod(wrapper, 0o755)
        return subprocess.run(
            [BASH, _bash_path(wrapper), *args], capture_output=True, text=True, timeout=180
        )

    def calls(self) -> str:
        return self.stub_log.read_text(encoding="utf-8")

    def pending(self) -> str:
        p = self.state / "obs_pending"
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""

    # ---- cenarios --------------------------------------------------------
    def test_sintaxe_bash(self):
        for rel in ("scripts/obs-apply.sh", "scripts/roleta-deploy-pull.sh", "tools/deploy_pull.sh"):
            res = subprocess.run(
                [BASH, "-n", _bash_path(REPO / rel)], capture_output=True, text=True
            )
            self.assertEqual(res.returncode, 0, f"{rel}: {res.stderr}")

    def test_deploy_sem_mudanca_de_obs_nao_toca_prometheus(self):
        (self.repo / "README.md").write_text("x\n", encoding="utf-8", newline="\n")
        sha1 = self._commit("nada de obs")
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("noop", res.stdout)
        self.assertEqual(self.calls().strip(), "", "Prometheus tocado num deploy sem obs")

    def test_alerts_mudou_valida_e_recarrega_sem_recriar(self):
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()  # mount de diretorio: container ve o arquivo novo
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        self.assertIn("/bin/promtool", calls, "validou antes de aplicar?")
        self.assertIn("check config", calls)
        self.assertIn("-X POST http://127.0.0.1:9090/-/reload", calls)
        self.assertNotIn(" up -d", calls, "reload nao pode recriar o container")
        self.assertEqual(self.pending(), "", "pendencia deveria ter sido limpa")
        self.assertLess(
            calls.index("promtool"), calls.index("/-/reload"), "validacao tem de vir ANTES"
        )

    def test_compose_mudou_recria_uma_vez_preservando_volume(self):
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V1)
        sha1 = self._commit("mount novo")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        ups = [c for c in calls.splitlines() if " up -d" in c]
        self.assertEqual(len(ups), 1, f"recriacao tem de ser unica: {ups}")
        self.assertIn("--no-deps", ups[0], "so o prometheus pode ser tocado")
        self.assertIn("prometheus", ups[0])
        self.assertNotIn("--remove-orphans", ups[0])
        self.assertNotIn("-v", ups[0].split("up -d")[1], "volume TSDB nao pode ser removido")
        self.assertNotIn("/-/reload", calls, "compose novo nao precisa de reload extra")

    def test_promtool_reprovado_aborta_sem_aplicar(self):
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("regra quebrada")
        res = self.run_obs("apply", self.sha0, sha1, STUB_PROMTOOL_RC="1")
        self.assertEqual(res.returncode, 1)
        calls = self.calls()
        self.assertNotIn("/-/reload", calls, "nao pode recarregar config invalida")
        self.assertNotIn(" up -d", calls, "nao pode recriar com config invalida")
        self.assertIn("promtool reprovou", res.stdout)

    def test_check_isolado_nao_toca_container(self):
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("check", self.sha0, sha1)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        self.assertIn("promtool", calls)
        self.assertNotIn("/-/reload", calls)
        self.assertNotIn(" up -d", calls)

    def test_inode_preso_e_detectado_e_escalado_uma_unica_vez(self):
        """O incidente literal: reload responde 200 e o container segue no arquivo velho."""
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("21 regras")
        # container NAO sincronizado: continua lendo a versao antiga (inode preso)
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 1, "sucesso falso com container servindo bytes velhos")
        self.assertIn("divergencia", res.stdout)
        calls = self.calls()
        self.assertIn("/-/reload", calls)
        forced = [c for c in calls.splitlines() if "--force-recreate" in c]
        self.assertEqual(len(forced), 1, "escala para UMA recriacao ao detectar inode preso")
        self.assertEqual(self.pending(), "escalated", "pendencia precisa sobreviver ao deploy")

        # tick seguinte (LOCAL==REMOTE): retoma sem recriar de novo -> sem loop de restart
        self.stub_log.write_text("", encoding="utf-8")
        res2 = self.run_obs("resume")
        self.assertEqual(res2.returncode, 1)
        self.assertNotIn("--force-recreate", self.calls(), "nao pode recriar a cada tick")

        # operador/recriacao resolve: o container passa a ler o arquivo novo
        self.stub_log.write_text("", encoding="utf-8")
        self._sync_container()
        res3 = self.run_obs("resume")
        self.assertEqual(res3.returncode, 0, res3.stdout + res3.stderr)
        self.assertEqual(self.pending(), "", "pendencia tem de ser limpa apos verificar")

    def test_reload_sem_sucesso_de_config_falha(self):
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_RELOAD_OK="0")
        self.assertEqual(res.returncode, 1)
        self.assertIn("prometheus_config_last_reload_successful != 1", res.stdout)

    def test_host_sem_stack_pula_silenciosamente(self):
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("skip", res.stdout)

    def test_prometheus_que_sumiu_e_falha_nao_skip(self):
        (self.state / "obs_seen").write_text("prometheus\n", encoding="utf-8", newline="\n")
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 1, "stack que existia e sumiu nao pode virar sucesso")
        self.assertIn("ausente", res.stdout)

    def test_force_faz_bootstrap_do_mount_novo(self):
        """Bootstrap manual do host: recria mesmo sem diff (migracao do mount)."""
        self._sync_container()
        res = self.run_obs("force")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        calls = self.calls()
        self.assertIn("promtool", calls)
        forced = [c for c in calls.splitlines() if "--force-recreate" in c]
        self.assertEqual(len(forced), 1)
        self.assertEqual(self.pending(), "")

    def test_resume_sem_pendencia_e_noop(self):
        res = self.run_obs("resume")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(self.calls().strip(), "")

    # ---- regressoes vindas do code review --------------------------------
    def test_metrics_grande_nao_vira_falso_negativo(self):
        """`printf | grep -q` sob pipefail: grep sai no 1o match, produtor leva
        SIGPIPE(141) e a verificacao reprovava um reload que funcionou."""
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        self._sync_container()
        res = self.run_obs("apply", self.sha0, sha1, STUB_BIG_METRICS="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("--force-recreate", self.calls(), "reload ok nao pode escalar")

    def test_verificacao_usa_container_em_execucao_nao_efemero(self):
        """`ps -a` traz os containers do `compose run`; verificar contra um deles
        (que monta o bind novo) devolveria sucesso com o Prometheus real velho."""
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("21 regras")
        # container real segue no arquivo velho; o efemero veria o novo
        res = self.run_obs("apply", self.sha0, sha1)
        self.assertEqual(res.returncode, 1, "verificou contra o container errado")
        for line in self.calls().splitlines():
            if " ps " in line:
                self.assertNotIn(" -aq", line, "listagem nao pode incluir containers efemeros")
                self.assertNotIn(" -a ", line)

    def test_check_nao_derruba_deploy_quando_a_stack_esta_fora(self):
        """A falha do `check` faz o deploy dar `git reset --hard`: stack ausente
        nao pode abortar um deploy de aplicacao valido."""
        (self.state / "obs_seen").write_text("prometheus\n", encoding="utf-8", newline="\n")
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("nova regra")
        res = self.run_obs("check", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        # ja o apply, esse sim, sinaliza a stack fora do ar
        res2 = self.run_obs("apply", self.sha0, sha1, STUB_NO_PROM="1")
        self.assertEqual(res2.returncode, 1)

    def test_recriacao_que_falha_nao_tranca_a_pendencia(self):
        """Marcar `escalated` antes do `up` dar certo trancaria a pendencia num
        estado que so faz reload — e reload nao conserta inode preso."""
        self._write_repo_files(self.ALERTS_V1, self.COMPOSE_V0)
        sha1 = self._commit("21 regras")  # container fica no arquivo velho
        res = self.run_obs("apply", self.sha0, sha1, STUB_FORCE_UP_RC="1")
        self.assertEqual(res.returncode, 1)
        self.assertEqual(self.pending(), "reload", "pendencia tem de permitir nova recriacao")

        # tick seguinte: pode (e deve) tentar a recriacao de novo
        self.stub_log.write_text("", encoding="utf-8")
        self._sync_container()
        res2 = self.run_obs("resume")
        self.assertEqual(res2.returncode, 0, res2.stdout + res2.stderr)
        self.assertEqual(self.pending(), "")


if __name__ == "__main__":
    unittest.main()
