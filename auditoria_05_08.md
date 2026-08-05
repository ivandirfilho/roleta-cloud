# Auditoria sênior — Azure, HostDime e migração Roleta Cloud

**Data:** 2026-08-05
**Branch auditada:** `ivandirfilho-project-health-overview`
**Base funcional:** `origin/main` em `126ab48` (V5.1)
**Entrega da auditoria:** `cfd7fad`
**Sincronização V5.1:** `b82d2bfc17af`
**Escopo:** arquitetura, runtime Azure, lift-and-shift HostDime → Azure, persistência,
CI/CD, segurança operacional, backup/restore, PostgreSQL, Caddy e documentação.

> Esta auditoria foi executada sem alterar `main`, sem fazer cutover DNS, sem
> desligar a HostDime e sem ligar `dual_write_pg`. A imagem da auditoria foi
> publicada por tag imutável e o canário foi redeployado na VM; o cutover continua
> bloqueado pelos gates humanos.

## 1. Veredito executivo

O desenho em duas ondas continua correto:

1. **Onda 1 — lift-and-shift:** VM Azure + Caddy + SQLite autoritativo + Blob
   para backup; PostgreSQL preparado, mas não autoritativo.
2. **Onda 2 — modernização:** PostgreSQL/CDC/dual-write somente após soak,
   reconciliação e gate humano.

O canário Azure registrado no plano estava saudável antes desta auditoria
(`/healthz` 200, WebSocket alcançável, portas do app em loopback), mas a imagem
então publicada (`azure-80fe40c`) antecedia a V5 e a correção de eleição do PR
#47. A auditoria foi publicada como `azure-806c543` e, após o avanço do `main`
para V5.1 (#48), a branch foi sincronizada em `b82d2bfc17af`. A imagem atual foi
publicada como `azure-b82d2bfc17af`, o canário foi redeployado por digest e
Caddy/frontend foram validados novamente na VM. Portanto, a imagem não é mais o
bloqueio, mas **não há autorização para cutover**.

**Conclusão:** a arquitetura é viável e a preparação foi bem direcionada. A
imagem, Caddy, frontend, health, WebSocket, backup e lifecycle já foram
validados no canário; o cutover permanece bloqueado pelo ensaio de restore e
pela cópia final com freeze humano.

## 2. Estado verificado

| Área | Estado | Evidência/observação |
|---|---|---|
| Código | `origin/main` V5.1 integrado na branch | Merge local `b82d2bfc17af`; `main` não foi alterado |
| VM Azure | Canário previamente saudável | Debian 12, Docker/Compose, Caddy nativo e volume em `/opt/roleta/data` |
| ACR | Atualizado sem mover `azure-latest` | `roleta-cloud:azure-b82d2bfc17af` e `roleta-cdc-worker:azure-b82d2bfc17af` publicados por digest |
| Key Vault | Existente e usado por Managed Identity | API key, PG, domínio e e-mail são lidos em runtime |
| Storage | Backup validado; lifecycle aplicado | MI mantém `Storage Blob Data Contributor`; lifecycle foi aplicado por identidade Owner do operador |
| PostgreSQL | Schema/grants aplicados até `0010_dir3_phase_columns` | `roleta_app` teve escrita em `shared.outbox` validada |
| SQLite | Fonte autoritativa da Onda 1 | Cópia anterior validada com contagens e checksums |
| `state.json` | Persistência no bind `/opt/roleta/data` | Seed canário agora exige autorização explícita |
| `dual_write_pg` | **OFF** | Não é ligado pela simples presença da DSN |
| CDC | Profile Azure adicionado, default inerte | Só sobe com `--with-pg --with-cdc` |
| DNS/TLS | Não executado | Caddy validado em `:80`; domínio real só deve ser carregado após o flip |
| HostDime | Mantida como produção | Freeze, fencing e revogação continuam gates humanos |

## 3. Inventário arquitetural final

```text
Chrome extension / clientes
            |
        DNS + 80/443
            |
       Caddy na VM Azure
       |              |
   /healthz       /ws -> 127.0.0.1:8765
       |              |
       +-------- roleta-cloud
                    |
          /opt/roleta/data (disco gerenciado)
             |                 |
         state.json       decisions.db
             |                 |
             +------ SQLite autoritativo
                    |
       Blob backups + manifesto SHA-256

PostgreSQL Flexible Server e cdc-worker:
  preparados para a Onda 2; ambos permanecem fora do caminho autoritativo
  enquanto dual_write_pg estiver OFF.
```

### Decisões mantidas

- **SQLite primeiro:** reduz o risco de cutover e preserva o comportamento atual.
- **PostgreSQL preparado, não promovido:** evita transformar uma migração de
  infraestrutura em migração de semântica de dados.
- **CDC em profile:** a outbox não é drenada por acidente antes do soak.
- **Imagem por digest:** a VM não reconstrói dependências mutáveis.
- **Caddy com TLS somente depois do DNS:** evita falha ACME e não cria tráfego
  dividido durante a propagação.
- **INV-3 preservado:** a estratégia continua indicando `APOSTAR`; vetos apenas
  limitam stake via `min()`.

## 4. Achados e correções

### Bloqueadores corrigidos na branch

| ID | Severidade | Achado | Correção aplicada | Estado |
|---|---|---|---|---|
| A-01 | Crítica | Tags `v*` podiam acionar SSH/build na HostDime depois do DNS, criando split-brain | `.github/workflows/deploy.yml` agora é manual, exige `DEPLOY_HOSTDIME` e `HOSTDIME_DEPLOY_ENABLED=true`; tags não acionam deploy | Código corrigido; revogação de secrets é humana |
| A-02 | Crítica | Imagem Azure ficaria anterior à V5/#47 | `.github/workflows/acr-image.yml` publica app e CDC a partir de `main`, com tags por SHA e digest no summary | Código corrigido; tag imutável publicada manualmente; OIDC pendente |
| A-03 | Alta | Frontend da imagem não era sincronizado para `/var/www/roleta` | `deploy-azure.sh` extrai e valida `index.html`, `app.js`, `style.css`; publica após health com backup local | Código corrigido e validado no redeploy |
| A-04 | Alta | `state.json` ausente podia virar seed sintético sem distinção de produção | Seed agora é default-OFF; ausência ou `__canary_seed__` bloqueia deploy sem `--allow-canary-seed` | Código corrigido |
| A-05 | Alta | DSN PG era montada com senha crua e podia desaparecer silenciosamente | URL encoding via Python; DSN é preservada por padrão e só é removida com `--without-pg`; argumentos desconhecidos falham | Código corrigido |
| A-06 | Alta | `CADDY_EMAIL` era staged, mas não consumido pelo Caddyfile | Diretiva global `email {$CADDY_EMAIL}`; `kv-to-env.sh` prepara domínio/e-mail em arquivo separado; drop-in systemd foi versionado | Código corrigido; `caddy validate`/reload OK no canário |
| A-07 | Alta | Backup não fazia `integrity_check`, mascarava erro RBAC e não tinha restore operacional | Backup valida SQLite/JSON, grava manifesto SHA-256 e não mascara `container create`; novo restore pareado e seguro | Backup OK; restore de ensaio pendente |
| A-08 | Média | Não havia retenção/lifecycle versionado para Blob | `set-blob-lifecycle.sh` reconcilia somente a regra Roleta e preserva regras existentes | Código corrigido; regra aplicada e verificada |
| A-09 | Alta | Onda PG não tinha `cdc-worker` no compose Azure | Serviço adicionado no profile `cdc`, com imagem própria no ACR e default inerte | Código corrigido; não ativar sem gate |
| A-10 | Média | `COPY . .` podia assar banco/estado/modelos binários em camadas | `.dockerignore` exclui `data/`, bancos e artefatos binários; mantém código fonte em `models/` | Código corrigido |
| A-11 | Média | Scripts legados de archive faziam push/reset/deploy direto em `main` e tinham destino HostDime fixo | `archive/deploy.sh` e `archive/deploy.ps1` removidos; histórico textual permanece apenas como snapshot | Corrigido |
| A-12 | Média | Runbooks usavam `docker-compose.azure.yml`, embora o arquivo real fosse `compose.azure.yml` | Referências operacionais corrigidas no plano e README | Corrigido |
| A-13 | Alta | O `show` de lifecycle devolve regras em `policy.rules`, mas o reconciliador lia somente o nível raiz; a MI da VM também não possui permissão de plano de controle | Script aceita a forma real do payload e separa `AZURE_AUTH_MODE=identity|user`; runbook orienta execução por operador/CI sem ampliar RBAC da VM | Corrigido; regra aplicada por Owner |

### Riscos ainda existentes, não automatizados

| ID | Severidade | Risco | Ação recomendada | Dono |
|---|---|---|---|---|
| R-01 | Crítica | O workflow OIDC ainda depende de secrets Azure não configurados no repositório | Manter o digest manual registrado até configurar OIDC e repetir a esteira a partir de `main` | Humano |
| R-02 | Crítica | Freeze e cópia final semântica ainda não ocorreram | Parar escrita HostDime, `.backup`, validar hash/contagens, restaurar em `/opt/roleta/data` | Humano |
| R-03 | Crítica | DNS e revogação de credenciais podem deixar dois escritores | Aplicar C-01…C-25; revogar `SERVER_*`/`SSH_PRIVATE_KEY` após cutover | Humano |
| R-04 | Alta | `CADDY_EMAIL` pode quebrar reload se o `EnvironmentFile` não estiver instalado | `/etc/caddy/caddy.env` e drop-in instalados; `caddy validate` e reload passaram no canário | Resolvido no canário; repetir no cutover |
| R-05 | Alta | A política de purge protection do Key Vault estava desativada | Ativar purge protection/soft delete conforme política Azure | Humano |
| R-06 | Alta | Não há IaC versionado para reconstruir RG/VNet/NSG/MI/PG/Storage | Criar Bicep/Terraform em sprint próprio, com plan e aprovação | Próximo sprint |
| R-07 | Média | Backup diário implica RPO potencial de até 24 horas | Backup Blob executado com `integrity_check=ok`; durante o soak, reduzir para intervalo compatível com RPO acordado e medir restore | Humano + SRE |
| R-08 | Média | O container principal usa root e `SYS_PTRACE` | Avaliar remoção após confirmar OCR/diagnóstico; não alterar no cutover | Próximo hardening |
| R-09 | Média | Migrações Alembic com DSN contendo `%` podem quebrar `ConfigParser` | Corrigir o caminho de configuração para não interpolar segredo; workaround atual usa `PGPASSWORD` | Próximo sprint |
| R-10 | Baixa | Documentos históricos ainda citam topologia/IPs antigos | Marcar explicitamente como snapshot histórico e não usar como runbook | Documentação |

## 5. Correções técnicas detalhadas

### Deploy Azure

`deploy-azure.sh` agora:

- rejeita opções desconhecidas;
- exige `--with-pg` para `--with-cdc`;
- recusa `/mnt` como destino de dados;
- resolve tag para digest e faz pull pela MI;
- extrai configs e frontend da mesma imagem que será executada;
- não cria estado canário sem flag explícita;
- valida JSON do estado antes do `up`;
- mantém `compose up --no-build`;
- só publica o frontend depois do backend saudável e restaura a cópia anterior
  se os artefatos obrigatórios não estiverem presentes.

### Segredos e configuração

`kv-to-env.sh`:

- recria `.env` atomicamente com modo `0600`;
- nunca imprime valores;
- URL-encoda senha PostgreSQL;
- preserva `ROLETA_IMAGE`, `CDC_IMAGE` e DSN existente sem rebaixar
  configuração silenciosamente;
- exige `--without-pg` para limpar a DSN;
- prepara `caddy.cutover.env` separado do canário;
- rejeita valores com quebras de linha e nomes de host inválidos.

### Backup e restore

O backup usa a SQLite backup API, valida `PRAGMA integrity_check`, valida
`state.json`, publica manifesto SHA-256 e falha explicitamente em erro de
autorização Blob. O restore:

- escolhe DB e estado pelo mesmo stamp;
- valida os dois antes de tocar no destino;
- recusa sobrescrever sem `--force`;
- recusa restore com `roleta-cloud` rodando;
- mantém cópias `.pre-restore.<stamp>` quando `--force` é usado;
- faz validação final do SQLite após a instalação.

## 6. Evidências de validação local

Executado nesta branch:

| Verificação | Resultado |
|---|---|
| `bash -n` dos cinco scripts Azure | OK |
| `docker compose ... config --quiet` sem CDC | OK |
| `docker compose --profile cdc ... config --quiet` | OK |
| Parse YAML dos workflows | OK |
| `python -m pytest tests/ -q --tb=short` | **798 passed, 9 skipped, 1 xfailed** |
| `python tools/lint_silent_except.py` | OK (124 exceções catalogadas) |
| `git diff --check` | OK |
| `origin/main` V5.1 integrado | OK (`b82d2bfc17af` contém `126ab48`) |
| Validação Caddy local | Não disponível: binário `caddy` não instalado neste workspace |
| CI do PR #43 | OK: guardrails + Python 3.11/3.12/3.13 |

Os testes Python e o lint local estão verdes. Ainda faltam os testes de
integração Azure: a ausência de Caddy local não deve ser convertida em
aprovação; a VM precisa executar `caddy validate` com o `EnvironmentFile` real.

## 6.1 Evidências Azure executadas

| Verificação | Resultado |
|---|---|
| Imagem app | `roleta-cloud:azure-b82d2bfc17af`, digest `sha256:358a9f…` |
| Imagem CDC | `roleta-cdc-worker:azure-b82d2bfc17af`, digest `sha256:89e5ef…` |
| Deploy canário | `ROLETA_TAG=azure-b82d2bfc17af ./deploy-azure.sh --with-pg`; sem seed |
| Backend/Caddy | `/healthz` interno e via Caddy: HTTP 200 |
| WebSocket | handshake `/ws`: HTTP 101 |
| Frontend | `index.html`, `app.js` e `style.css` publicados da mesma imagem |
| Portas | app somente em `127.0.0.1:8765/8766`; Caddy em `*:80` no canário |
| SQLite | `integrity_check=ok`; contagens 10949/43594/9136/348/2168 |
| Estado | versão `2.0.0`; `__canary_seed__=false`; `dual_write_pg` permanece OFF |
| Backup Blob | stamp `20260805T172530Z`; DB, estado e manifesto SHA-256 enviados |
| Lifecycle | regra `roleta-sqlite-retention`: cool 7d, delete 30d |
| Restore | ensaio isolado OK; `integrity_check=ok`, contagens iguais e RTO canário de 12s |

## 7. Gates humanos obrigatórios

1. Configurar OIDC do GitHub (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`) e repetir a esteira a partir de `main`; o publish
   manual desta auditoria já está registrado por digest.
2. Repetir o restore em diretório de ensaio durante o ensaio final, comparar
   manifesto/contagens e manter RTO acordado; não usar `--force` no caminho ativo.
3. Fazer freeze da HostDime, parar timers/units/ingress conforme C-01…C-15,
   gerar `.backup` final e reconciliar `rowid`, contagens, `spin_seq` e hashes.
4. Restaurar no caminho efetivo `/opt/roleta/data`, validar o estado e só então
   iniciar a Azure com a imagem por digest.
5. Aprovar C-24, alterar DNS em C-25 e validar HTTPS/WSS externamente.
6. Depois de estabilizar, revogar credenciais de deploy HostDime e manter
   `HOSTDIME_DEPLOY_ENABLED` ausente ou `false`.
7. Não ligar `dual_write_pg` nem o CDC como parte do cutover SQLite; isso exige
   uma janela e um plano de reconciliação próprios.

## 8. Próximos passos recomendados

| Ordem | Passo | Critério de saída |
|---:|---|---|
| 1 | Entregar esta branch por PR e revisar o diff | CI verde, sem mudança de estratégia |
| 2 | Configurar OIDC e repetir publicação a partir de `main` | Digest app/CDC registrado pela esteira |
| 3 | Ensaio final de cutover | Paridade de contagens/estado e rollback documentado |
| 4 | Freeze + DNS + fencing | Um único escritor e credenciais antigas revogadas |
| 5 | IaC e hardening | Azure reconstruível, purge protection e SLO/RPO formalizados |
| 6 | Onda PG | CDC/dual-write somente após soak e reconciliação |

## 9. Limitações do Graphify e rastreabilidade

O grafo local reportou **7.352 nós, 8.417 arestas, 388 comunidades**, com
aproximadamente 96% das relações extraídas e 4% inferidas. Consultas MCP amplas
(`god_nodes`, listagem de PRs e algumas travessias) sofreram timeout/transport
closed por causa do tamanho do grafo. A auditoria usou os nós/artefatos já
indexados, consultas direcionadas e leitura dos arquivos efetivos; isso é uma
limitação de consulta, não uma evidência de que o grafo esteja vazio.

`graphify-out/` continua fora do versionamento. A atualização do grafo deve ser
feita localmente após o merge, sem adicionar o artefato pesado ao PR.

## 10. Resultado final

**A preparação Azure está funcional no canário, mas o cutover ainda não está
autorizado.** Os bugs de automação, seed, frontend, DSN, Caddy, backup, lifecycle,
CDC, contexto Docker e fencing CI foram corrigidos na branch. A imagem atual,
backup/lifecycle e restore de ensaio foram validados; permanecem o OIDC
reprodutível a partir de `main` e os gates de freeze/cópia final, DNS e fencing
humano. Nenhuma dessas ações deve ser inferida a partir de um teste local ou
executada automaticamente pelo PR.
