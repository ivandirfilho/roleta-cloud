#!/bin/bash
# ROLETA-DEPLOY-SHIM — marcador estavel; NAO remover esta linha.
# (scripts/roleta-deploy-install.sh --check procura por ela para reconhecer o
#  entrypoint como "dirigido pelo repo" e nao como copia congelada.)
#
# SHIM IMUTAVEL do deploy — instalado UMA vez em /usr/local/bin/roleta-deploy-pull.sh
# (o mesmo slot que a unit systemd ja chama; ver "POR QUE O MESMO PATH", abaixo).
#
# O QUE ELE FAZ, A CADA TICK
#   1) git fetch origin main            -> traz a verdade do repo
#   2) git show origin/main:<deploy>    -> materializa o script de deploy da MAIN
#      em $STATE_DIR (auditavel: e exatamente o arquivo que rodou)
#   3) bash -n <script>                 -> GATE de sintaxe
#   4) exec bash <script>               -> roda a logica versionada
#
# POR QUE ISSO E SEGURO (a objecao historica, respondida com engenharia)
#   `scripts/roleta-deploy-pull.sh` documenta desde 05/08 a decisao de NAO se
#   auto-instalar: "um deploy que reescreve o proprio entrypoint pode se tornar
#   irrecuperavel se o arquivo novo estiver quebrado". A objecao e legitima e
#   continua valendo — para quem SOBRESCREVE o entrypoint. Este shim inverte o
#   problema:
#     - ele NAO se auto-atualiza (e minusculo e sem logica de deploy: nunca
#       precisa mudar). O que muda a cada tick e o ALVO, nao o shim;
#     - ele le o alvo da MAIN *antes* de executa-lo. Logo `git revert` de um PR
#       que quebrou o deploy CURA o deploy no tick seguinte, sem tocar no host —
#       a propriedade que faltava para tornar o self-update aceitavel;
#     - o gate `bash -n` recusa executar um alvo sintaticamente quebrado, e sai
#       != 0 (unit `failed`, visivel) em vez de rodar meio script.
#
# POR QUE O MESMO PATH DO ENTRYPOINT (e nao um ExecStart novo)
#   Apontar a unit para um path novo exigiria um drop-in `systemctl edit` — ou
#   seja, MAIS UM artefato de producao fora do git, exatamente a classe de
#   problema que este sprint elimina. Ocupando o slot que a unit ja chama, o
#   bootstrap do dono e um comando e a unit versionada continua valendo.
#
# DEGRADACAO DELIBERADA
#   - `git fetch` falhou (rede/GitHub fora): usa a copia do working tree (que e
#     a ultima main conhecida) e loga. O self-heal local continua rodando durante
#     um incidente de rede — que e justamente quando ele importa.
#   - alvo ausente na main ou reprovado no `bash -n`: NAO executa nada e sai != 0.
#     Cura = `git revert` do PR culpado; o tick seguinte ja pega a versao boa.
#
# INSTALACAO (uma vez, no servidor)
#   bash /root/roleta-cloud/scripts/roleta-deploy-install.sh install-shim
#
# ROLLBACK
#   bash /root/roleta-cloud/scripts/roleta-deploy-install.sh --rollback
#   (restaura o entrypoint anterior a partir de /usr/local/lib/roleta-deploy/)
set -euo pipefail

REPO_DIR="${REPO_DIR:-/root/roleta-cloud}"
STATE_DIR="${STATE_DIR:-/var/lib/roleta-deploy}"
LOG_FILE="${LOG_FILE:-/var/log/roleta-deploy.log}"
DEPLOY_BRANCH="${DEPLOY_BRANCH:-main}"
DEPLOY_REL="${DEPLOY_REL:-scripts/roleta-deploy-pull.sh}"
# Marcador do entrypoint canonico (existe no cabecalho do deploy versionado).
DEPLOY_MARKER="${DEPLOY_MARKER:-ROLETA-DEPLOY-PULL}"

# stderr vai para o journald (a unit e oneshot); o arquivo mantem o historico
# no mesmo lugar em que o deploy escreve.
log() {
    local line="[$(date -u +%FT%TZ)] SHIM $*"
    echo "$line" >&2
    echo "$line" >> "$LOG_FILE" 2>/dev/null || true
}

cd "$REPO_DIR" 2>/dev/null || { log "FAIL checkout ausente: $REPO_DIR"; exit 1; }
mkdir -p "$STATE_DIR" 2>/dev/null || true

STAGED="$STATE_DIR/deploy-from-${DEPLOY_BRANCH}.sh"
fresh=0

if git fetch --quiet origin "$DEPLOY_BRANCH" 2>/dev/null; then
    if ! git cat-file -e "origin/$DEPLOY_BRANCH:$DEPLOY_REL" 2>/dev/null; then
        log "FAIL $DEPLOY_REL ausente em origin/$DEPLOY_BRANCH — nada executado (cure com revert do PR culpado)"
        exit 1
    fi
    if ! git show "origin/$DEPLOY_BRANCH:$DEPLOY_REL" > "$STAGED.tmp" 2>/dev/null; then
        rm -f "$STAGED.tmp" 2>/dev/null || true
        log "FAIL nao consegui materializar $DEPLOY_REL em $STAGED (STATE_DIR sem escrita?)"
        exit 1
    fi
    mv -f "$STAGED.tmp" "$STAGED"
    fresh=1
else
    # Rede/GitHub fora: o working tree e a ultima main conhecida. Rodar a copia
    # local mantem o self-heal vivo durante o incidente.
    if [ -f "$REPO_DIR/$DEPLOY_REL" ]; then
        cp -f "$REPO_DIR/$DEPLOY_REL" "$STAGED"
        log "FETCH FAIL — rodando a copia local de $DEPLOY_REL (ultima main conhecida)"
    else
        log "FAIL fetch falhou e nao ha copia local de $DEPLOY_REL"
        exit 1
    fi
fi

# GATE 1: script vazio/truncado passa em `bash -n` e sai 0 — seria "sucesso" eterno
# sem deploy, sem self-heal e sem conf. Exige tamanho e o marcador do script canonico.
if [ ! -s "$STAGED" ]; then
    log "GATE $DEPLOY_REL veio VAZIO (origem=$([ "$fresh" = "1" ] && echo "origin/$DEPLOY_BRANCH" || echo 'copia local')) — nada executado"
    exit 1
fi
if ! grep -q "$DEPLOY_MARKER" "$STAGED" 2>/dev/null; then
    log "GATE $DEPLOY_REL sem o marcador '$DEPLOY_MARKER' — nao parece o deploy canonico; nada executado"
    log "GATE cure com 'git revert' do PR culpado; o tick seguinte ja executa a versao boa"
    exit 1
fi

# GATE 2: um alvo quebrado nao roda pela metade — recusa e sai != 0.
if ! bash -n "$STAGED" 2>/dev/null; then
    log "GATE bash -n REPROVOU $DEPLOY_REL (origem=$([ "$fresh" = "1" ] && echo "origin/$DEPLOY_BRANCH" || echo 'copia local')) — nada executado"
    log "GATE cure com 'git revert' do PR culpado; o tick seguinte ja executa a versao boa"
    exit 1
fi

exec bash "$STAGED" "$@"
