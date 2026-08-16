# ADENDO ISO — 16/08/2026 · Última milha do deploy (shim + instalação do `roleta.conf`)

**Origem:** `SPR-D2`, aberto pelo Diretor logo após o merge do `SPR-D1` (PR #74).
**Antecessor:** `docs/iso/adendos/2026-08-16-diagnostico-502-self-heal.md` (§5 — "Limite conhecido").
**Documento-mãe:** `Manutenabilidade_iso.md` (histórico; não recebe append).

## 1. O problema que o D1 provou e não pôde resolver

O SPR-D1 entregou o self-heal do tick NOOP e as sondas `/health` e `/metrics` no
`roleta.conf` — e, ao entregá-las, provou empiricamente uma falha de **classe**:

> Duas peças críticas de produção vivem **fora do alcance de qualquer merge**:
> `/usr/local/bin/roleta-deploy-pull.sh` (o que o systemd realmente executa) e o
> `roleta.conf` que o nginx lê. Nenhum deploy instalava nenhuma das duas.

A consequência é a inversão silenciosa do contrato do repo: **`main` deixa de ser
produção**. O PR mergeia, o CI fica verde, o BOARD fecha o sprint — e o host continua
rodando o código de antes. Foi exatamente o que aconteceu: o `roleta.conf` do D1 (com
`location = /health`) estava mergeado enquanto a sonda externa devolvia `404`.

Pior: a falha é **auto-selante**. Se o entrypoint congelado for um deploy quebrado, ele
não consegue nem fazer o `git fetch/reset` que traria a correção. O `git revert` — a
rede de segurança de todo o modelo zero-humano deste repo — **não chega ao host**. A
única saída era ssh, isto é, a intervenção manual que o contrato agêntico proíbe.

## 2. O que mudou

### 2.1 `scripts/roleta-deploy-shim.sh` — entrypoint que se auto-sincroniza

Instalado por `roleta-deploy-install.sh install-shim` **no mesmo caminho do entrypoint**
(`/usr/local/bin/roleta-deploy-pull.sh`). A cada tick:

```
git fetch origin main
git show origin/main:scripts/roleta-deploy-pull.sh > $STATE_DIR/deploy-from-main.sh
bash -n  (gate)
exec bash "$STAGED" "$@"
```

O host passa a executar **o que está em `origin/main`**, não o que está no checkout nem
o que foi copiado um dia. `git revert` volta a curar produção em ≤2 min, sem ssh.

Quatro decisões de desenho que não são cosméticas:

- **Não toca a working tree.** A versão óbvia (`git reset --hard origin/main` antes do
  `exec`) **quebraria o deploy**: o gate de NOOP compara `HEAD` com `origin/main`, e um
  reset prévio deixaria os dois sempre iguais — o script cairia no ramo "nada a fazer"
  para sempre e nunca mais faria build/alembic/`up -d`. Por isso o alvo é materializado
  com `git show` em `$STATE_DIR`, e o `reset` continua sendo responsabilidade do deploy.
  Há teste travando essa propriedade (`test_shim_nao_toca_a_working_tree`).
- **Gate `bash -n` antes do `exec`.** Script inválido em `main` ⇒ `exit 1` visível e host
  intacto; nada é executado pela metade.
- **Gate de identidade antes do `bash -n`.** Alvo vazio/truncado passa em `bash -n` e sai
  `0` — o host reportaria "deploy ok" indefinidamente sem deployar nada, que é o pior modo
  de falha possível num self-healer. Exige arquivo não-vazio **e** o marcador
  `ROLETA-DEPLOY-PULL` do entrypoint canônico.
- **Falha de rede degrada, não interrompe.** `fetch` falhou ⇒ loga `FETCH FAIL` e executa
  a cópia do checkout. Uma indisponibilidade do GitHub não pode virar uma janela sem deploy.
- **Instalado no caminho do entrypoint, sem drop-in do systemd.** O brief previa
  `ExecStart=…/roleta-deploy-shim.sh` via drop-in. Preferimos manter o caminho:
  a unit não muda (`test_unit_systemd_continua_apontando_para_usr_local` segue válido), o
  bootstrap do dono encolhe para um comando, e não existe o estado intermediário "shim
  instalado mas unit ainda apontando para o arquivo velho" — que seria uma nova variante
  do mesmo bug que estamos corrigindo.

### 2.2 A objeção histórica anti-self-update — por que ela não se aplica ao shim

O próprio deploy documenta, desde 05/08, por que **não** se auto-instala:

> "reescrever o próprio entrypoint em execução pode deixar o host sem deploy funcional se
> o arquivo novo estiver quebrado — a correção é um comando único e reversível."

A objeção continua correta, e o shim **não a viola**: ele nunca reescreve
`/usr/local/bin`. O que se auto-atualiza é *a escolha do que executar*, não o executor.
A distinção é o núcleo do desenho:

| | Auto-instalação (rejeitada) | Shim (adotado) |
|---|---|---|
| O que muda a cada tick | o arquivo em `/usr/local/bin` | apenas o script **executado** |
| Estado quebrado possível | entrypoint corrompido ⇒ host sem deploy | nenhum: o shim é imutável e mínimo |
| Como se recupera | ssh + reinstalar | `git revert` (o shim já busca `main` no tick seguinte) |
| Superfície | o deploy inteiro (centenas de linhas) | ~60 linhas sem lógica de negócio |

O shim é *menos* arriscado do que o launcher que ele substitui: o launcher executava o
**checkout**, que só é atualizado pelo próprio script que ele executa — um laço fechado.
O shim quebra o laço com a única fonte de verdade que não depende do host.

### 2.3 O deploy passa a instalar o `roleta.conf`

Bloco `# >>> SPR-D2 NGINX CONF BEGIN/END` em `scripts/roleta-deploy-pull.sh`, executado
depois do healthcheck OK (junto do sync de `frontend/`) e também no ramo NOOP. Idempotente
por `cmp -s`: conf igual ⇒ não escreve, não faz backup, não recarrega, não loga.

Havendo diferença, a sequência é **validar antes de tocar o destino**:

1. copia para `<dir>/.roleta.conf.roleta-deploy.tmp` — nome **com ponto** de propósito:
   `include /etc/nginx/sites-enabled/*;` é um glob sem filtro de extensão, e `glob(3)` não
   casa dotfiles; o arquivo em voo nunca é carregado como configuração. Mesmo diretório ⇒
   o `mv` final é rename atômico;
2. **pré-valida o candidato** num prefixo nginx isolado (`mktemp -d` com
   `pid/error_log/events{}/http{ include <candidato>; }`, `nginx -t -p … -c …`). Reprovou
   ⇒ `ABORTADO`, **destino intacto**, nenhum reload;
3. backup em `/var/lib/roleta-deploy/nginx/roleta.conf.bak` + `.bak.<TS>` (prune mantém as
   `NGINX_BACKUP_KEEP` mais recentes);
4. `mv` atômico;
5. `nginx -t` **global** — autoridade final, porque vê o `http{}` real. Reprovou ⇒ restaura
   o backup, reconfere e loga `ROLLBACK ok` ou `ROLLBACK INSTAVEL`;
6. `systemctl reload nginx`.

**Por que pré-validar em vez de instalar-e-testar.** `nginx -t` só valida o que já está no
disco. Instalar primeiro abre uma janela — pequena, mas real — em que um reload de terceiro
(certbot renovando certificado, por exemplo) carregaria um vhost quebrado e derrubaria o
site. Com a pré-validação, a janela é zero: o destino só é tocado por um candidato que já
provou ser válido.

**Por que o backup não fica em `/etc/nginx/`.** Um `roleta.conf.bak` em `sites-enabled/`
seria **carregado** pelo glob, duplicando o `server{}` e fazendo o `nginx -t` falhar
sozinho — o backup viraria o incidente. Daí `/var/lib/roleta-deploy/nginx/`.

O passo é **não-fatal para o app** (que já está saudável no SHA novo) e **visível**:
falhou ⇒ `NGINX_CONF_FAIL`, log `DEPLOY PARCIAL` e `exit 1`, unit `failed`. Nunca "sucesso"
com o vhost desatualizado.

**Três modos de falso sucesso fechados depois de um review adversarial** (o review encontrou
o que o harness inicial não cobria — vale registrar, porque os três eram silenciosos):

| Modo | Como se manifestaria | Defesa |
|---|---|---|
| Reload perdido | SIGKILL/reboot entre o `mv` e o `reload`, ou reload que falha: no tick seguinte `cmp` dá igual ⇒ no-op ⇒ nginx serve a config velha **para sempre** | marca `.reload-pending` criada antes do `mv` e apagada **só** após o reload confirmado; com a marca presente, o tick revalida e recarrega mesmo em dia |
| Destino inativo | vhost em `sites-available` sem symlink em `sites-enabled`: `nginx -t`, reload e healthcheck passam todos, e nada do que é servido mudou | confere no `nginx -T` (lista dos arquivos realmente carregados) se o destino está lá; não está ⇒ `DESTINO INATIVO` |
| Destino ambíguo | dois arquivos reais distintos entre os candidatos: atualiza um, o ativo é o outro | `MULTIPLOS DESTINOS` ⇒ falha fechada pedindo `NGINX_CONF_DST` explícito |

Na mesma passada: pré-validação **falha fechada** se o `mktemp` falhar (antes instalava sem
validar), o rollback também virou `mv` atômico (um `cp` interrompido deixaria o vhost
truncado) e fonte versionada ausente virou falha em vez de skip silencioso.

### 2.4 `roleta-deploy-install.sh` — instalação atômica e ciente do shim

- `atomic_install()`: gate `bash -n` no candidato → temp oculto no diretório de destino →
  `mv -f`. Nunca existe entrypoint meio-escrito, nem se o disco encher no meio da cópia.
  O `--rollback` passa `nogate` de propósito: ele restaura **exatamente** o que estava lá.
- modo `install-shim` (novo) ao lado de `install`, `--check`, `--rollback`.
- `--check` reconhece as duas famílias (`ROLETA-DEPLOY-SHIM` e `ROLETA-DEPLOY-LAUNCHER`):
  em dia (silencioso) · `DESATUALIZADO` (mesma família, outra versão — as mudanças
  versionadas continuam chegando) · `DRIFT` (sem marcador = cópia congelada).
- `install` **não rebaixa** um shim instalado para launcher (evita regressão acidental por
  um bootstrap antigo copiado de outra doc).

### 2.5 Testes — `tests/test_spr_d2_ultima_milha.py`

17 testes (52 asserts nos harnesses); os funcionais executam os blocos **do script real**,
extraídos por sentinelas, com `nginx`/`systemctl` stubados (conf) e **repositórios git de
verdade** (shim). Cobrem os cenários do brief: (a) conf diferente ⇒ instala + backup +
reload; (b) conf igual ⇒ no-op silencioso; (c) pré-validação reprova ⇒ destino intacto /
`nginx -t` global reprova ⇒ backup restaurado; (d) script quebrado em `main` ⇒ gate segura,
`exit ≠ 0`, nada executado; (e) shim executa a versão de `origin/main`, **não** a do
checkout, sem sujar a working tree. Mais os cenários nascidos do review: symlink preservado,
reload pendente (com e sem falha de reload), destino inativo, destino ambíguo, deploy vazio
e deploy impostor.

O harness foi verificado contra **mutações deliberadas** do script de produção (remover a
pré-validação, remover o rollback, remover a idempotência): as três foram detectadas. Um
harness que passa sempre é pior do que nenhum — a checagem de mutação é o que separa
"testado" de "coberto".

## 3. Flags e defaults

| Variável | Default | Efeito |
|---|---|---|
| `NGINX_CONF_SYNC` | `1` | `0` desliga a instalação do conf |
| `NGINX_CONF_PREVALIDATE` | `1` | `0` pula só o gate isolado (o `nginx -t` global permanece) |
| `NGINX_CONF_DST` | — | caminho exato do vhost |
| `NGINX_CONF_CANDIDATES` | `sites-available` → `sites-enabled` → `conf.d` | busca do destino (symlink resolve para o alvo) |
| `NGINX_BACKUP_KEEP` | `10` | backups datados retidos |
| `DEPLOY_BRANCH` / `DEPLOY_REL` (shim) | `main` / `scripts/roleta-deploy-pull.sh` | o que o shim busca e executa |

**Por que nascem LIGADOS, contra a regra "flag default-OFF".** A regra protege mudança de
comportamento do **produto** — nada aqui toca estratégia, stake ou INV-3. São ações
corretivas e idempotentes num caminho que hoje simplesmente não existe. Nascer OFF
significaria entregar a correção da falha "mergeou ≠ implantado" **desligada**, dependendo
de um segundo PR para valer — precisamente a "ação humana pendente" que o contrato proíbe.
Kill switches imediatos existem para os dois passos. **Nenhuma flag do `docker-compose.yml`
foi tocada ⇒ não há espelho `deploy/azure/compose.azure.yml` a sincronizar** (confirmado).

## 4. O que este PR **não** resolve sozinho (honestidade obrigatória)

O entrypoint atual do host é uma cópia congelada; ela não executa nada deste PR. É preciso
**um** comando do dono, uma última vez (issue #76):

```bash
bash /root/roleta-cloud/scripts/roleta-deploy-install.sh install-shim
```

Depois dele, esta classe de intervenção acaba: entrypoint, deploy e `roleta.conf` passam a
seguir o repo sozinhos, e a rota de emergência volta a ser `git revert`. A issue #76 **só
fecha** quando o dono confirmar `/health` → 200 — o merge, por si, não é evidência de cura.
Essa distinção é a lição inteira deste sprint.

## 5. Como reverter

- **Cirúrgico, sem deploy:** `NGINX_CONF_SYNC=0` (ou `NGINX_CONF_PREVALIDATE=0`) no
  `Environment=` da unit + `systemctl daemon-reload`.
- **Total:** `git revert` do PR do SPR-D2 — e, com o shim instalado, o tick seguinte já
  executa a versão revertida (≤2 min, sem ssh). Sem schema, sem flag de produto, sem
  migração.
- **Só o conf:** o rollback já é automático em falha de `nginx -t`; manualmente, o backup
  está em `/var/lib/roleta-deploy/nginx/roleta.conf.bak`.
- **Só o entrypoint:** `roleta-deploy-install.sh --rollback` restaura o anterior a partir
  de `/usr/local/lib/roleta-deploy/`.

## 6. Lições ISO 25010 / 14764

- **"Mergeado" não é um estado de produção** (14764 · *gestão de configuração*). Enquanto
  existir um artefato de runtime que nenhum deploy instala, o pipeline mente: o verde do CI
  descreve o repo, não o host. Regra que fica: **todo arquivo que o runtime lê tem de ter um
  instalador versionado — ou é dívida silenciosa esperando um incidente.**
- **Rede de segurança que depende do componente quebrado não é rede** (25010 ·
  *Recuperabilidade*). O `git revert` era a garantia de reversão do repo inteiro, mas
  passava pelo próprio entrypoint que podia estar quebrado. Regra que fica: **o caminho de
  recuperação tem de ser independente daquilo de que ele recupera.**
- **Objeção antiga merece releitura, não obediência** (14764 · *manutenção evolutiva*). O
  "não se auto-instale" de 05/08 estava certo — para *aquele* desenho. Tratá-lo como dogma
  teria travado a correção; tratá-lo como lixo teria recriado o risco. O caminho foi separar
  o que a objeção realmente protege (o executor imutável) do que ela nunca protegeu (a
  escolha do que executar).
- **Validar antes de substituir, não depois** (25010 · *Tolerância a falhas*). "Instalar e
  então testar" só parece equivalente enquanto ninguém mais recarrega o serviço. A janela
  existe e é usada por certbot, por um `reload` de operador, por outro deploy. Regra que
  fica: **em configuração compartilhada, o candidato prova sua validade antes de encostar no
  destino.**
- **O backup pode ser o incidente.** Um `.bak` guardado dentro de um diretório varrido por
  glob vira configuração ativa. Regra que fica: **backup mora fora do caminho de leitura do
  serviço.**
- **Teste que nunca falha não testa** (14764 · *manutenção preventiva*). Harness de bash
  passa com facilidade suspeita; mutar o script de produção e exigir que o harness quebre é
  o mínimo para acreditar nele.
- **Num self-healer, o modo de falha a caçar é o sucesso falso** (25010 · *Analisabilidade*).
  Os três buracos achados no review (reload perdido, vhost inativo, alvo vazio) tinham a mesma
  assinatura: todos os gates passavam, o log dizia "ok" e nada mudava em produção — a versão
  microscópica do próprio "mergeou ≠ implantado" que este sprint existe para matar. Regra que
  fica: **para cada passo, pergunte "como isto reportaria sucesso sem ter efeito?" e feche esse
  caminho antes de fechar o caminho do erro barulhento.**
- **Cobertura que pula em silêncio é a mesma mentira, um nível acima** (14764 · *manutenção
  preventiva*). O cenário (c5) — destino em symlink, que é o layout padrão do Debian
  (`sites-enabled` → `sites-available`) e portanto o caminho **mais provável** em produção —
  se auto-pulava quando o filesystem não criava symlink, e o log do CI não dizia que tinha
  pulado. Suíte verde, cenário nunca executado. Fechado no follow-up: o harness conta os
  próprios asserts (`TOTAL n`) contra um número duro, um cenário pulado imprime `SKIP`
  explícito, e pular em host POSIX virou erro de setup (`exit 92`). Regra que fica: **um teste
  que pode se ausentar sem barulho não é cobertura — é a esperança de cobertura.**

## 7. Replay envelope

| Item | Valor |
|---|---|
| Sprint / PR | `SPR-D2` · PR aberto com base `main` (título `SPR-D2: …`) |
| Modelo | Claude Opus 5 (executor), sessão Copilot CLI em worktree isolado |
| Skills / MCPs | `sprint-executor` (agente), `gh` CLI, harness bash próprio, sem MCP externo |
| Turnos / duração | ~40 turnos · sessão única de 16/08/2026 |
| Validação | `pytest tests/ --ignore=tests/test_obs_reload.py` → 1254 passed · contratos CI-only (`TestDeployEntrypoint`, `TestInstaladorDoEntrypoint`, `TestLauncherRuntime`, `TestComposeMount…`) → 32 passed · `bash -n` nos 4 scripts · mutação 3/3 detectada |
| Sem ssh | nenhum acesso ao host; implantação real depende do bootstrap da issue #76 |
