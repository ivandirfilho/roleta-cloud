"""SPR-D2 — contratos da ultima milha do deploy (conf do nginx + shim do entrypoint).

O SPR-D1 provou que `main` verde nao implica producao curada: `roleta.conf` e o
entrypoint `/usr/local/bin/roleta-deploy-pull.sh` viviam FORA do repo e nenhum
deploy os instalava. Este arquivo trava as duas metades da correcao:

1. `sync_nginx_conf()` (bloco `# >>> SPR-D2 NGINX CONF` do deploy) instala o
   `roleta.conf` versionado com pre-validacao do CANDIDATO, `mv` atomico,
   `nginx -t` global e rollback do backup — e nao encosta no nginx quando nao ha
   diferenca.
2. `scripts/roleta-deploy-shim.sh` le o script de deploy de `origin/main` a cada
   tick, com gate `bash -n`. E o que torna `git revert` uma cura de producao:
   o tick seguinte ja executa a versao revertida.

Os cenarios (a)-(e) do brief estao nos harnesses bash abaixo; a extracao por
sentinela segue o padrao do SPR-D1 (guards altos para sub/sobre-captura, para o
teste nunca sourcear o fluxo de deploy real no checkout de quem roda).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO / "scripts" / "roleta-deploy-pull.sh"
SHIM_SH = REPO / "scripts" / "roleta-deploy-shim.sh"
INSTALL_SH = REPO / "scripts" / "roleta-deploy-install.sh"

BASH = shutil.which("bash")
GIT = shutil.which("git")


def _bash(script: str, *args: str) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, newline="\n") as fh:
        fh.write(script)
        path = fh.name
    try:
        return subprocess.run(
            [BASH, path, *args], capture_output=True, text=True, timeout=180
        )
    finally:
        Path(path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Cenarios (a), (b), (c): instalacao do conf do nginx pelo deploy.
# Stubs de `nginx` e `systemctl` sao funcoes bash; `command -v nginx` encontra
# funcoes, entao o guard "nginx ausente no host" nao dispara.
# ---------------------------------------------------------------------------
HARNESS_CONF = r"""
set -uo pipefail
SRC="$1"
BLOCK="$(mktemp)"
awk '/^# >>> SPR-D2 NGINX CONF BEGIN/{f=1} /^# <<< SPR-D2 NGINX CONF END/{f=0} f' "$SRC" > "$BLOCK"
# Guard de SUB-captura: os marcadores sumiram/mudaram.
grep -q 'sync_nginx_conf()' "$BLOCK" || { echo "BLOCO-NAO-EXTRAIDO"; exit 90; }
# Guard de SOBRE-captura: sem o marcador final o awk iria ate o EOF e o `source`
# executaria o deploy REAL (git reset --hard) no checkout de quem roda o teste.
if grep -qE 'git reset --hard|git fetch|docker compose build|alembic upgrade' "$BLOCK"; then
    echo "BLOCO-EXCEDIDO"; exit 91
fi

WORK="$(mktemp -d)"
REPO_DIR="$WORK/repo";     mkdir -p "$REPO_DIR"
STATE_DIR="$WORK/state";   mkdir -p "$STATE_DIR"
NGINX_DIR="$WORK/nginx";   mkdir -p "$NGINX_DIR"
NGINX_CONF_SRC="$REPO_DIR/roleta.conf"
NGINX_CONF_DST="$NGINX_DIR/roleta.conf"
NGINX_BACKUP_DIR="$STATE_DIR/nginx"
LOG_LAST=""
log() { LOG_LAST="$LOG_LAST$*"$'\n'; }

# shellcheck disable=SC1090
source "$BLOCK"

RELOADS=0
NGINX_T_DUMP=""
nginx() {
    local a conf="" prev="" inc
    if [ "${1:-}" = "-T" ]; then
        # dump da config carregada (vazio = "nao sei", como um nginx que recusa -T)
        printf '%s' "$NGINX_T_DUMP"
        return 0
    fi
    for a in "$@"; do
        if [ "$prev" = "-c" ]; then conf="$a"; fi
        prev="$a"
    done
    if [ -n "$conf" ]; then
        # modo isolado: valida o CANDIDATO incluido pelo conf de teste
        inc="$(awk '/include /{print $2}' "$conf" | tr -d ';')"
        if [ -f "$inc" ] && grep -q 'BROKEN' "$inc"; then
            echo "nginx: [emerg] diretiva BROKEN" >&2
            return 1
        fi
        return 0
    fi
    # modo global: valida o que esta instalado no destino real
    if [ -f "$NGINX_CONF_DST" ] && grep -q 'GLOBALFAIL' "$NGINX_CONF_DST"; then
        echo "nginx: [emerg] conflito no contexto global" >&2
        return 1
    fi
    return 0
}
systemctl() {
    if [ "${1:-}" = "reload" ]; then RELOADS=$((RELOADS + 1)); fi
    return 0
}

fail=0
ok() { # nome obtido esperado
    if [ "$2" = "$3" ]; then
        echo "PASS  $1"
    else
        echo "FAIL  $1 (obtido='$2' esperado='$3')"; fail=1
    fi
}
run() { LOG_LAST=""; RELOADS=0; sync_nginx_conf; RC=$?; }

# --- (a) conf diferente -> instala + backup + 1 reload ---------------------
printf 'server { listen 80; server_name a; }\n' > "$NGINX_CONF_SRC"
printf 'server { listen 80; server_name VELHO; }\n' > "$NGINX_CONF_DST"
run
ok "(a) rc"                "$RC" "0"
ok "(a) reloads"           "$RELOADS" "1"
if cmp -s "$NGINX_CONF_SRC" "$NGINX_CONF_DST"; then inst=sim; else inst=nao; fi
ok "(a) conf instalado"    "$inst" "sim"
if grep -q VELHO "$NGINX_BACKUP_DIR/roleta.conf.bak" 2>/dev/null; then bkp=sim; else bkp=nao; fi
ok "(a) backup do anterior" "$bkp" "sim"
if ls "$NGINX_BACKUP_DIR"/roleta.conf.bak.* >/dev/null 2>&1; then ts=sim; else ts=nao; fi
ok "(a) backup datado"     "$ts" "sim"
case "$LOG_LAST" in *"NGINX CONF instalado"*) l=sim;; *) l=nao;; esac
ok "(a) log de instalacao" "$l" "sim"

# --- (b) conf igual -> no-op absoluto (nem reload, nem backup novo) --------
antes="$(ls "$NGINX_BACKUP_DIR" | wc -l)"
run
ok "(b) rc"                "$RC" "0"
ok "(b) reloads"           "$RELOADS" "0"
ok "(b) sem backup novo"   "$(ls "$NGINX_BACKUP_DIR" | wc -l)" "$antes"
ok "(b) silencioso"        "$LOG_LAST" ""

# --- (c1) candidato invalido -> destino NAO e tocado (janela zero) ---------
printf 'server { BROKEN listen 80; }\n' > "$NGINX_CONF_SRC"
antes_dst="$(cat "$NGINX_CONF_DST")"
run
ok "(c1) rc"               "$RC" "1"
ok "(c1) reloads"          "$RELOADS" "0"
ok "(c1) destino intacto"  "$(cat "$NGINX_CONF_DST")" "$antes_dst"
case "$LOG_LAST" in *"ABORTADO"*) l=sim;; *) l=nao;; esac
ok "(c1) log ABORTADO"     "$l" "sim"
if ls "$NGINX_DIR"/.roleta.conf.* >/dev/null 2>&1; then lixo=sim; else lixo=nao; fi
ok "(c1) sem temp orfao"   "$lixo" "nao"

# --- (c2) nginx -t global falha DEPOIS de instalar -> rollback do backup ---
printf 'server { listen 80; server_name bom; }\n' > "$NGINX_CONF_DST"
printf 'server { GLOBALFAIL listen 80; }\n' > "$NGINX_CONF_SRC"
antes_dst="$(cat "$NGINX_CONF_DST")"
run
ok "(c2) rc"               "$RC" "1"
ok "(c2) reloads"          "$RELOADS" "0"
ok "(c2) backup restaurado" "$(cat "$NGINX_CONF_DST")" "$antes_dst"
case "$LOG_LAST" in *"ROLLBACK ok"*) l=sim;; *) l=nao;; esac
ok "(c2) log ROLLBACK"     "$l" "sim"

# --- (c3) destino nao resolvido -> falha VISIVEL, nunca silenciosa ---------
NGINX_CONF_DST=""
NGINX_CONF_CANDIDATES="$WORK/nao/existe.conf $WORK/tambem/nao.conf"
printf 'server { listen 80; }\n' > "$NGINX_CONF_SRC"
run
ok "(c3) rc"               "$RC" "1"
case "$LOG_LAST" in *"DESTINO NAO ENCONTRADO"*) l=sim;; *) l=nao;; esac
ok "(c3) log do destino"   "$l" "sim"

# --- (c5) destino e symlink -> escreve no ALVO e preserva o link -----------
# Layout Debian real: sites-enabled/x -> sites-available/x. Um `mv` sobre o link
# o trocaria por arquivo comum e deixaria sites-available com a copia velha.
SA="$WORK/sa"; SE="$WORK/se"; mkdir -p "$SA" "$SE"
printf 'server { listen 80; server_name alvo-velho; }\n' > "$SA/roleta.conf"
ln -s "$SA/roleta.conf" "$SE/roleta.conf" 2>/dev/null || true
if [ -L "$SE/roleta.conf" ]; then
    NGINX_CONF_DST=""
    NGINX_CONF_CANDIDATES="$SE/roleta.conf"
    printf 'server { listen 80; server_name alvo-novo; }\n' > "$NGINX_CONF_SRC"
    run
    ok "(c5) rc"               "$RC" "0"
    if grep -q 'alvo-novo' "$SA/roleta.conf"; then a=sim; else a=nao; fi
    ok "(c5) alvo atualizado"  "$a" "sim"
    if [ -L "$SE/roleta.conf" ]; then a=sim; else a=nao; fi
    ok "(c5) symlink preservado" "$a" "sim"
else
    echo "PASS  (c5) pulado — o filesystem nao cria symlink"
fi

# --- (c6) reload pendente de um tick anterior -> recarrega mesmo em dia -----
# Cobre SIGKILL/reboot entre o `mv` e o `reload`, e reload que falhou: sem a marca,
# `cmp` igual devolveria no-op e o nginx serviria a config velha para sempre.
NGINX_CONF_DST="$NGINX_DIR/roleta.conf"
printf 'server { listen 80; server_name pend; }\n' > "$NGINX_CONF_SRC"
cp -f "$NGINX_CONF_SRC" "$NGINX_CONF_DST"
mkdir -p "$NGINX_BACKUP_DIR"; : > "$NGINX_RELOAD_PENDING"
run
ok "(c6) rc"               "$RC" "0"
ok "(c6) recarregou"       "$RELOADS" "1"
case "$LOG_LAST" in *"RELOAD PENDENTE"*) l=sim;; *) l=nao;; esac
ok "(c6) log da pendencia" "$l" "sim"
if [ -f "$NGINX_RELOAD_PENDING" ]; then l=sim; else l=nao; fi
ok "(c6) marca limpa"      "$l" "nao"
# e o reload que falha PRESERVA a marca para o proximo tick
systemctl() { return 1; }
printf 'server { listen 80; server_name pend2; }\n' > "$NGINX_CONF_SRC"
run
ok "(c6) rc do reload ruim" "$RC" "1"
if [ -f "$NGINX_RELOAD_PENDING" ]; then l=sim; else l=nao; fi
ok "(c6) marca mantida"    "$l" "sim"
systemctl() { if [ "${1:-}" = "reload" ]; then RELOADS=$((RELOADS + 1)); fi; return 0; }
run; rm -f "$NGINX_RELOAD_PENDING"

# --- (c7) destino inativo (nginx -T nao carrega o arquivo) -> falha visivel -
# Sem isso, instalar num vhost desabilitado passaria em tudo e mentiria "ok".
printf 'server { listen 80; server_name inativo; }\n' > "$NGINX_CONF_SRC"
NGINX_T_DUMP="# configuration file /etc/nginx/nginx.conf: server { listen 80; }"
run
ok "(c7) rc"               "$RC" "1"
case "$LOG_LAST" in *"DESTINO INATIVO"*) l=sim;; *) l=nao;; esac
ok "(c7) log do inativo"   "$l" "sim"
printf 'server { listen 80; server_name ativo; }\n' > "$NGINX_CONF_SRC"
NGINX_T_DUMP="# configuration file $NGINX_CONF_DST: server { listen 80; }"
run
ok "(c7) rc quando ativo"  "$RC" "0"
NGINX_T_DUMP=""

# --- (c8) dois destinos REAIS distintos -> nao adivinha, falha fechada ------
CA="$WORK/ca"; CB="$WORK/cb"; mkdir -p "$CA" "$CB"
printf 'server { listen 80; server_name um; }\n'   > "$CA/roleta.conf"
printf 'server { listen 80; server_name dois; }\n' > "$CB/roleta.conf"
NGINX_CONF_DST=""
NGINX_CONF_CANDIDATES="$CA/roleta.conf $CB/roleta.conf"
run
ok "(c8) rc"               "$RC" "1"
case "$LOG_LAST" in *"MULTIPLOS DESTINOS"*) l=sim;; *) l=nao;; esac
ok "(c8) log da ambiguidade" "$l" "sim"
if grep -q 'server_name um' "$CA/roleta.conf"; then l=sim; else l=nao; fi
ok "(c8) nao tocou em nada" "$l" "sim"

# --- (c4) kill switch: NGINX_CONF_SYNC=0 nao encosta em nada --------------
NGINX_CONF_DST="$NGINX_DIR/roleta.conf"
NGINX_CONF_SYNC=0
printf 'server { listen 80; server_name novo; }\n' > "$NGINX_CONF_SRC"
run
ok "(c4) rc"               "$RC" "0"
ok "(c4) reloads"          "$RELOADS" "0"

rm -rf "$WORK" "$BLOCK"
exit $fail
"""


# ---------------------------------------------------------------------------
# Cenarios (d) e (e): o shim, exercitado contra repositorios git de verdade.
# ---------------------------------------------------------------------------
HARNESS_SHIM = r"""
set -uo pipefail
SHIM_SRC="$1"

export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.invalid
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.invalid

WORK="$(mktemp -d)"
SHIM="$WORK/shim.sh"
cat "$SHIM_SRC" > "$SHIM"
ORIGIN="$WORK/origin.git"
REPO="$WORK/repo"
PUB="$WORK/pub"
STATE="$WORK/state"
LOG="$WORK/deploy.log"
mkdir -p "$STATE"

git init --bare --quiet "$ORIGIN" || { echo "SETUP-FAIL init bare"; exit 92; }
git --git-dir="$ORIGIN" symbolic-ref HEAD refs/heads/main

git init --quiet "$REPO" || { echo "SETUP-FAIL init"; exit 92; }
cd "$REPO"
git symbolic-ref HEAD refs/heads/main
git remote add origin "$ORIGIN"
mkdir -p scripts
printf '#!/bin/bash\n# ROLETA-DEPLOY-PULL\necho "DEPLOY-V1 args=$*"\n' > scripts/roleta-deploy-pull.sh
git add -A && git commit --quiet -m v1 || { echo "SETUP-FAIL commit"; exit 92; }
git push --quiet origin main || { echo "SETUP-FAIL push"; exit 92; }

publica() { # $1 = conteudo do script de deploy na main
    rm -rf "$PUB"
    git clone --quiet "$ORIGIN" "$PUB" >/dev/null 2>&1 || return 1
    printf '%s' "$1" > "$PUB/scripts/roleta-deploy-pull.sh"
    ( cd "$PUB" && git add -A && git commit --quiet -m pub && git push --quiet origin main ) >/dev/null 2>&1
}

fail=0
ok() { # nome obtido esperado
    if [ "$2" = "$3" ]; then
        echo "PASS  $1"
    else
        echo "FAIL  $1 (obtido='$2' esperado='$3')"; fail=1
    fi
}
roda_shim() {
    OUT="$(REPO_DIR="$REPO" STATE_DIR="$STATE" LOG_FILE="$LOG" bash "$SHIM" 2>&1)"
    RC=$?
}
tem() { case "$OUT" in *"$1"*) echo sim;; *) echo nao;; esac; }

# --- (e) o shim puxa a main NOVA antes do exec ----------------------------
# A working tree do servidor segue em v1; a main ja tem v2. O tick tem de
# executar v2 — e por isso que `git revert` cura o deploy sem tocar no host.
publica '#!/bin/bash
# ROLETA-DEPLOY-PULL
echo "DEPLOY-V2 args=$*"
' || { echo "SETUP-FAIL publica v2"; exit 92; }
roda_shim
ok "(e) rc"                   "$RC" "0"
ok "(e) executou a main nova" "$(tem 'DEPLOY-V2')" "sim"
ok "(e) nao executou a local" "$(tem 'DEPLOY-V1')" "nao"
if grep -q 'DEPLOY-V1' "$REPO/scripts/roleta-deploy-pull.sh"; then wt=intacta; else wt=mexida; fi
ok "(e) working tree intacta" "$wt" "intacta"
if grep -q 'DEPLOY-V2' "$STATE/deploy-from-main.sh" 2>/dev/null; then st=sim; else st=nao; fi
ok "(e) staged auditavel"     "$st" "sim"

# --- (d) main quebrada -> gate `bash -n` segura e sai != 0 ----------------
publica '#!/bin/bash
# ROLETA-DEPLOY-PULL
if [ ; then
echo "DEPLOY-V3"
' || { echo "SETUP-FAIL publica v3"; exit 92; }
roda_shim
ok "(d) rc != 0"              "$RC" "1"
ok "(d) log do gate"          "$(tem 'GATE')" "sim"
ok "(d) nada foi executado"   "$(tem 'DEPLOY-V3')" "nao"

# --- (f1) main com o deploy VAZIO -> recusa (passaria em `bash -n` e sairia 0)
# Sem este gate, um truncamento viraria "deploy ok" silencioso para sempre.
publica '' || { echo "SETUP-FAIL publica vazio"; exit 92; }
roda_shim
ok "(f1) rc != 0"             "$RC" "1"
ok "(f1) log do vazio"        "$(tem 'VAZIO')" "sim"

# --- (f2) main com script que nao e o entrypoint canonico -> recusa ---------
publica '#!/bin/bash
echo "IMPOSTOR"
' || { echo "SETUP-FAIL publica impostor"; exit 92; }
roda_shim
ok "(f2) rc != 0"             "$RC" "1"
ok "(f2) log do marcador"     "$(tem 'marcador')" "sim"
ok "(f2) nada executado"      "$(tem 'IMPOSTOR')" "nao"

# --- (d2) main sem o script -> recusa explicita ---------------------------
rm -rf "$PUB"
git clone --quiet "$ORIGIN" "$PUB" >/dev/null 2>&1
( cd "$PUB" && git rm --quiet scripts/roleta-deploy-pull.sh && git commit --quiet -m drop && git push --quiet origin main ) >/dev/null 2>&1
roda_shim
ok "(d2) rc != 0"             "$RC" "1"
ok "(d2) log de ausencia"     "$(tem 'ausente em origin/main')" "sim"

# --- (d3) fetch falhou (rede fora) -> degrada para a copia local ----------
# Durante um incidente de rede o self-heal precisa continuar rodando.
git -C "$REPO" remote set-url origin "$WORK/inexistente.git"
roda_shim
ok "(d3) rc"                  "$RC" "0"
ok "(d3) avisou o fetch"      "$(tem 'FETCH FAIL')" "sim"
ok "(d3) rodou a copia local" "$(tem 'DEPLOY-V1')" "sim"

rm -rf "$WORK"
exit $fail
"""


class TestShimContrato(unittest.TestCase):
    """O shim so vale se for pequeno, sem logica de deploy e sempre lendo a main."""

    @classmethod
    def setUpClass(cls):
        cls.src = SHIM_SH.read_text(encoding="utf-8")

    def test_shim_existe_e_e_versionado(self):
        self.assertTrue(SHIM_SH.exists(), "o shim tem de viver no repo, nao no host")

    def test_marcador_permite_reconhecer_o_entrypoint(self):
        """Sem marcador, `--check` classificaria o shim como copia congelada."""
        self.assertIn("ROLETA-DEPLOY-SHIM", self.src)

    def test_le_o_deploy_de_origin_main_antes_de_executar(self):
        self.assertIn("git fetch", self.src)
        self.assertIn('git show "origin/$DEPLOY_BRANCH:$DEPLOY_REL"', self.src)
        self.assertIn("exec bash", self.src)

    def test_gate_de_sintaxe_antes_do_exec(self):
        """Um alvo quebrado nao pode rodar pela metade."""
        gate = self.src.index("bash -n")
        self.assertLess(gate, self.src.index("exec bash"), "o gate tem de vir antes do exec")

    def test_shim_nao_tem_logica_de_deploy(self):
        """O shim e imutavel por desenho: se precisasse mudar, viraria o problema
        que ele resolve (artefato de producao fora do git)."""
        code = "\n".join(
            ln for ln in self.src.splitlines() if not ln.lstrip().startswith("#")
        )
        for proibido in ("docker compose", "alembic", "git reset --hard", "curl"):
            self.assertNotIn(proibido, code, f"{proibido} nao pertence ao shim")

    def test_shim_nao_toca_a_working_tree(self):
        """`git reset --hard` no shim faria LOCAL==REMOTE e o deploy cairia no
        ramo NOOP para sempre — nunca mais faria build/alembic/up."""
        self.assertNotIn("git reset", self.src)
        self.assertNotIn("git checkout", self.src)
        self.assertNotIn("git pull", self.src)

    def test_instalador_conhece_o_shim(self):
        inst = INSTALL_SH.read_text(encoding="utf-8")
        self.assertIn("install-shim", inst)
        self.assertIn("ROLETA-DEPLOY-SHIM", inst)
        self.assertIn("atomic_install", inst)
        # a instalacao passa por temporario + rename: nunca um entrypoint pela metade
        atomic = inst.split("atomic_install() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("mv -f", atomic)
        self.assertIn("bash -n", atomic)


class TestDeployInstalaOConf(unittest.TestCase):
    """Contratos estaticos do bloco SPR-D2 do deploy."""

    @classmethod
    def setUpClass(cls):
        cls.src = DEPLOY_SH.read_text(encoding="utf-8")

    def test_sentinelas_presentes(self):
        self.assertIn("# >>> SPR-D2 NGINX CONF BEGIN", self.src)
        self.assertIn("# <<< SPR-D2 NGINX CONF END", self.src)

    def test_conf_e_sincronizado_tambem_no_tick_noop(self):
        """O vhost e estado convergente: um tick sem commit novo ainda reconcilia."""
        ramo = self.src.split('if [ "$LOCAL" = "$REMOTE" ]; then', 1)[1].split("\nfi\n", 1)[0]
        self.assertIn("sync_nginx_conf", ramo)
        self.assertLess(ramo.index("sync_nginx_conf"), ramo.index("exit 0"))

    def test_falha_de_conf_contamina_o_status_do_deploy(self):
        """Sem isto o systemd reportaria sucesso com o nginx servindo o vhost velho."""
        self.assertIn("NGINX_CONF_FAIL", self.src)
        self.assertIn("DEPLOY PARCIAL", self.src)

    def test_obs_roda_mesmo_com_o_conf_falhado(self):
        """Sair antes do obs esconderia um drift silencioso de Prometheus."""
        obs = self.src.index('obs_run apply "$LOCAL" "$REMOTE"')
        parcial = self.src.index('if [ "$NGINX_CONF_FAIL" != "0" ]; then')
        self.assertLess(obs, parcial)

    def test_valida_o_candidato_antes_de_tocar_no_destino(self):
        """Instalar e so entao testar deixa janela para um reload de terceiro
        (o hook do certbot, por exemplo) carregar um vhost invalido."""
        bloco = self.src.split("# >>> SPR-D2 NGINX CONF BEGIN", 1)[1].split(
            "# <<< SPR-D2 NGINX CONF END", 1
        )[0]
        self.assertIn("prevalidate_nginx_conf", bloco)
        self.assertLess(
            bloco.index("prevalidate_nginx_conf \"$tmp\""),
            bloco.index('mv -f "$tmp" "$dst"'),
            "a pre-validacao tem de vir antes do mv para o destino",
        )

    def test_troca_e_atomica(self):
        bloco = self.src.split("# >>> SPR-D2 NGINX CONF BEGIN", 1)[1].split(
            "# <<< SPR-D2 NGINX CONF END", 1
        )[0]
        self.assertIn('mv -f "$tmp" "$dst"', bloco)
        # temporario oculto: `include sites-enabled/*` nao pode pegar o arquivo em voo
        self.assertIn('tmp="$(dirname "$dst")/.$(basename "$dst")', bloco)

    def test_backup_fica_fora_das_pastas_do_nginx(self):
        """Um `.bak` dentro de sites-enabled/ seria incluido pelo glob e
        duplicaria o server block — `nginx -t` passaria a falhar sozinho."""
        bloco = self.src.split("# >>> SPR-D2 NGINX CONF BEGIN", 1)[1].split(
            "# <<< SPR-D2 NGINX CONF END", 1
        )[0]
        self.assertIn('NGINX_BACKUP_DIR="${NGINX_BACKUP_DIR:-$STATE_DIR/nginx}"', bloco)

    def test_destino_e_configuravel(self):
        """O layout do host e incerteza conhecida (o agente nao faz ssh)."""
        self.assertIn("NGINX_CONF_DST", self.src)
        self.assertIn("NGINX_CONF_CANDIDATES", self.src)


@unittest.skipUnless(BASH, "bash indisponivel")
class TestConfSyncFuncional(unittest.TestCase):
    """Cenarios (a), (b) e (c) do brief, executando o bloco real do deploy."""

    def test_cenarios(self):
        r = _bash(HARNESS_CONF, str(DEPLOY_SH))
        self.assertNotEqual(r.returncode, 90, f"sentinelas do bloco sumiram:\n{r.stdout}")
        self.assertNotEqual(r.returncode, 91, f"captura excedeu o bloco:\n{r.stdout}")
        self.assertEqual(r.returncode, 0, f"{r.stdout}\n{r.stderr}")
        self.assertIn("PASS", r.stdout)
        self.assertNotIn("FAIL", r.stdout)


@unittest.skipUnless(BASH and GIT, "bash/git indisponiveis")
class TestShimFuncional(unittest.TestCase):
    """Cenarios (d) e (e) do brief, com repositorios git de verdade."""

    def test_cenarios(self):
        r = _bash(HARNESS_SHIM, str(SHIM_SH))
        self.assertNotEqual(r.returncode, 92, f"setup do repo de teste falhou:\n{r.stdout}")
        self.assertEqual(r.returncode, 0, f"{r.stdout}\n{r.stderr}")
        self.assertIn("PASS", r.stdout)
        self.assertNotIn("FAIL", r.stdout)


if __name__ == "__main__":
    unittest.main()
