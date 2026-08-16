#!/bin/bash
# Instalador/atualizador do entrypoint de deploy — idempotente e reversível.
#
# POR QUE ESTE SCRIPT EXISTE
#   O systemd executa /usr/local/bin/roleta-deploy-pull.sh, que fica FORA do repo.
#   Historicamente esse arquivo era uma COPIA congelada do script de deploy: melhorias
#   versionadas (por exemplo o passo de observabilidade do OBS-INODE) so chegavam em
#   producao se alguem lembrasse de reinstalar a copia — e ninguem lembrava, porque
#   nada tornava o congelamento visivel. `scripts/roleta-deploy-launcher.sh` resolve o
#   futuro (o entrypoint vira um ponteiro para o script versionado), mas alguem precisa
#   INSTALAR o launcher uma vez, com segurança e de forma auditavel. E este script.
#
# USO
#   roleta-deploy-install.sh              instala/atualiza o launcher (idempotente)
#   roleta-deploy-install.sh install-shim instala/atualiza o SHIM (SPR-D2) — o
#                                         entrypoint que le o deploy da main a
#                                         cada tick; e o modo recomendado hoje
#   roleta-deploy-install.sh --check    diagnostica:
#                                         0 = em dia (ou launcher/shim de outra
#                                             versao: as mudancas versionadas
#                                             CHEGAM)
#                                         1 = copia congelada (o deploy versionado
#                                             NAO esta rodando)
#                                         2 = erro
#   roleta-deploy-install.sh --rollback restaura o entrypoint anterior do backup
#
# LIMITE CONHECIDO DA SONDA
#   Quem chama `--check` no fim do deploy e o script VERSIONADO. Enquanto o
#   entrypoint for a copia congelada de antes deste PR, essa copia nunca executa a
#   sonda — ou seja, a sonda NAO detecta o congelamento ATUAL, so protege contra um
#   re-congelamento FUTURO. Por isso o bootstrap manual e obrigatorio, e a unit
#   systemd tambem chama a sonda em ExecStartPre (nao-fatal), o que a torna
#   independente de qual script esta instalado.
#
# GARANTIAS
#   - idempotente: se o entrypoint ja for o launcher/shim, nao escreve nada;
#   - reversivel: o entrypoint anterior e copiado para $BACKUP_DIR antes de qualquer
#     substituicao, e --rollback o traz de volta;
#   - atomico (SPR-D2): a escrita passa por um arquivo temporario no MESMO diretorio
#     + `mv` (rename) — nunca existe um entrypoint pela metade, mesmo se a maquina
#     cair no meio da instalacao;
#   - com gate (SPR-D2): `bash -n` recusa instalar um entrypoint sintaticamente
#     quebrado (era o risco que justificava manter tudo manual);
#   - nao mexe na unit systemd: o caminho e o nome do arquivo instalado nao mudam;
#   - --check e read-only e serve de sonda (o deploy o chama para logar o drift).
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
LAUNCHER_SRC="${LAUNCHER_SRC:-$REPO_DIR/scripts/roleta-deploy-launcher.sh}"
SHIM_SRC="${SHIM_SRC:-$REPO_DIR/scripts/roleta-deploy-shim.sh}"
ENTRYPOINT="${ENTRYPOINT:-/usr/local/bin/roleta-deploy-pull.sh}"
BACKUP_DIR="${BACKUP_DIR:-/usr/local/lib/roleta-deploy}"

log() { echo "[$(date -u +%FT%TZ)] INSTALL $*"; }

# `--check` roda a cada tick (ExecStartPre + fim do deploy): silencioso quando esta
# tudo certo, para nao encher o journal. OBS_VERBOSE=1 forca o log.
log_ok() { if [ "${OBS_VERBOSE:-0}" = "1" ]; then log "$@"; fi; }

# Marcadores: distinguem "e um entrypoint dirigido pelo repo (talvez de outra
# versao)" de "e uma copia congelada do deploy".
LAUNCHER_MARK="ROLETA-DEPLOY-LAUNCHER"
SHIM_MARK="ROLETA-DEPLOY-SHIM"

is_launcher() {
    [ -f "$1" ] && grep -q "$LAUNCHER_MARK" "$1" 2>/dev/null
}

is_shim() {
    [ -f "$1" ] && grep -q "$SHIM_MARK" "$1" 2>/dev/null
}

sha() {
    if [ ! -f "$1" ]; then
        printf ''
        return 0
    fi
    sha256sum < "$1" | awk '{print $1}'
}

# Escrita ATOMICA do entrypoint (SPR-D2): gate de sintaxe -> arquivo temporario no
# mesmo diretorio -> `mv` (rename atomico no mesmo filesystem). Sem isto, uma queda
# no meio de um `cp` deixaria o systemd chamando um arquivo truncado.
# $3 = "nogate" pula o `bash -n` (usado no --rollback: restaurar o estado anterior
# e uma acao explicita do dono e nao pode ser bloqueada por uma sonda).
atomic_install() {
    local src="$1" dst="$2" gate="${3:-gate}" tmp
    if [ "$gate" = "gate" ] && ! bash -n "$src" 2>/dev/null; then
        log "FAIL $src reprovado no gate 'bash -n' — $dst NAO foi tocado"
        return 1
    fi
    tmp="$(dirname "$dst")/.$(basename "$dst").install.$$"
    if ! install -m755 "$src" "$tmp" 2>/dev/null; then
        rm -f "$tmp" 2>/dev/null || true
        log "FAIL nao consegui escrever o arquivo temporario $tmp"
        return 1
    fi
    if ! mv -f "$tmp" "$dst"; then
        rm -f "$tmp" 2>/dev/null || true
        log "FAIL mv atomico para $dst falhou"
        return 1
    fi
    return 0
}

mode="${1:-install}"

if [ ! -f "$LAUNCHER_SRC" ]; then
    log "FAIL launcher ausente no repo: $LAUNCHER_SRC"
    exit 2
fi

src_sha="$(sha "$LAUNCHER_SRC")"
shim_sha="$(sha "$SHIM_SRC")"
cur_sha="$(sha "$ENTRYPOINT")"

case "$mode" in
    --check)
        if [ -z "$cur_sha" ]; then
            log "DRIFT entrypoint ausente: $ENTRYPOINT"
            exit 1
        fi
        if [ -n "$shim_sha" ] && [ "$cur_sha" = "$shim_sha" ]; then
            log_ok "ok — $ENTRYPOINT e o shim versionado (${shim_sha:0:12})"
            exit 0
        fi
        if [ "$cur_sha" = "$src_sha" ]; then
            log_ok "ok — $ENTRYPOINT e o launcher versionado (${src_sha:0:12})"
            exit 0
        fi
        # Hash diferente NAO significa, sozinho, que o deploy versionado parou de
        # chegar: um launcher/shim de outra versao continua executando o script do
        # repo. So a AUSENCIA dos marcadores prova que voltou a ser uma copia.
        if is_shim "$ENTRYPOINT"; then
            log "DESATUALIZADO $ENTRYPOINT e um shim de outra versao (instalado=${cur_sha:0:12} repo=${shim_sha:0:12})"
            log "DESATUALIZADO o deploy da main CONTINUA sendo executado a cada tick; atualize quando puder: bash $REPO_DIR/scripts/roleta-deploy-install.sh install-shim"
            exit 0
        fi
        if is_launcher "$ENTRYPOINT"; then
            log "DESATUALIZADO $ENTRYPOINT e um launcher de outra versao (instalado=${cur_sha:0:12} repo=${src_sha:0:12})"
            log "DESATUALIZADO as mudancas versionadas CONTINUAM chegando; atualize quando puder: bash $REPO_DIR/scripts/roleta-deploy-install.sh"
            exit 0
        fi
        log "DRIFT $ENTRYPOINT NAO e um launcher: instalado=${cur_sha:0:12} repo=${src_sha:0:12}"
        log "DRIFT o deploy em uso e uma copia congelada — mudancas versionadas do deploy NAO estao chegando"
        log "DRIFT corrija com: bash $REPO_DIR/scripts/roleta-deploy-install.sh install-shim"
        exit 1
        ;;

    --rollback)
        backup="$BACKUP_DIR/$(basename "$ENTRYPOINT").bak"
        if [ ! -f "$backup" ]; then
            log "FAIL sem backup em $backup"
            exit 2
        fi
        if ! atomic_install "$backup" "$ENTRYPOINT" nogate; then
            exit 2
        fi
        log "rollback ok — $ENTRYPOINT restaurado de $backup"
        exit 0
        ;;

    install-shim)
        if [ ! -f "$SHIM_SRC" ]; then
            log "FAIL shim ausente no repo: $SHIM_SRC"
            exit 2
        fi
        if [ "$cur_sha" = "$shim_sha" ]; then
            log "ok — nada a fazer, $ENTRYPOINT ja e o shim (${shim_sha:0:12})"
            exit 0
        fi
        mkdir -p "$BACKUP_DIR"
        if [ -n "$cur_sha" ]; then
            install -m755 "$ENTRYPOINT" "$BACKUP_DIR/$(basename "$ENTRYPOINT").bak"
            log "backup do entrypoint anterior (${cur_sha:0:12}) em $BACKUP_DIR"
        else
            log "entrypoint inexistente — instalando pela primeira vez"
        fi
        if ! atomic_install "$SHIM_SRC" "$ENTRYPOINT"; then
            exit 2
        fi
        log "shim instalado em $ENTRYPOINT (${shim_sha:0:12})"
        log "a partir daqui cada tick le $REPO_DIR/scripts/roleta-deploy-pull.sh de origin/main antes de executar"
        log "consequencia pratica: 'git revert' de um PR que quebrou o deploy cura o deploy no tick seguinte, sem tocar no host"
        log "rollback: bash $REPO_DIR/scripts/roleta-deploy-install.sh --rollback"
        exit 0
        ;;

    install)
        # Nao rebaixa um shim ja instalado para launcher: o shim e estritamente
        # mais forte (le a main a cada tick). Trocar exige o modo explicito.
        if is_shim "$ENTRYPOINT"; then
            log "ok — nada a fazer, $ENTRYPOINT ja e o shim (mais recente que o launcher)"
            log "ok — para atualizar o shim: bash $REPO_DIR/scripts/roleta-deploy-install.sh install-shim"
            exit 0
        fi
        if [ "$cur_sha" = "$src_sha" ]; then
            log "ok — nada a fazer, $ENTRYPOINT ja e o launcher (${src_sha:0:12})"
            exit 0
        fi
        mkdir -p "$BACKUP_DIR"
        if [ -n "$cur_sha" ]; then
            install -m755 "$ENTRYPOINT" "$BACKUP_DIR/$(basename "$ENTRYPOINT").bak"
            log "backup do entrypoint anterior (${cur_sha:0:12}) em $BACKUP_DIR"
        else
            log "entrypoint inexistente — instalando pela primeira vez"
        fi
        if ! atomic_install "$LAUNCHER_SRC" "$ENTRYPOINT"; then
            exit 2
        fi
        log "launcher instalado em $ENTRYPOINT (${src_sha:0:12})"
        log "a partir daqui o deploy roda sempre $REPO_DIR/scripts/roleta-deploy-pull.sh (via git)"
        log "rollback: bash $REPO_DIR/scripts/roleta-deploy-install.sh --rollback"
        exit 0
        ;;

    *)
        log "FAIL modo desconhecido: $mode (use: install | install-shim | --check | --rollback)"
        exit 2
        ;;
esac
