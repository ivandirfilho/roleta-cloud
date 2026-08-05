# Auditoria sênior — Azure, HostDime e migração Roleta Cloud

**Data:** 2026-08-05
**Branch auditada:** `ivandirfilho-project-health-overview`
**HEAD:** `59ba329` (com `origin/main` integrado)
**Escopo:** arquitetura, runtime Azure, lift-and-shift HostDime → Azure, persistência,
CI/CD, segurança operacional, backup/restore, PostgreSQL, Caddy e documentação.

> Esta auditoria foi executada sem alterar `main`, sem fazer cutover DNS, sem
> desligar a HostDime e sem ligar `dual_write_pg`. A correção de código está nesta
> branch; a publicação na VM Azure continua sendo um passo controlado posterior.

## 1. Veredito executivo

O desenho em duas ondas continua correto:

1. **Onda 1 — lift-and-shift:** VM Azure + Caddy + SQLite autoritativo + Blob
   para backup; PostgreSQL preparado, mas não autoritativo.
2. **Onda 2 — modernização:** PostgreSQL/CDC/dual-write somente após soak,
   reconciliação e gate humano.

O canário Azure registrado no plano estava saudável antes desta auditoria
(`/healthz` 200, WebSocket alcançável, portas do app em loopback), mas a imagem
então publicada (`azure-80fe40c`) antecedia a V5 e a correção de eleição do PR
#47. Portanto, **não havia autorização para cutover**. A esteira ACR criada nesta
branch corrige a origem da imagem, mas ainda precisa ser executada após a entrega
do PR e validada na VM.

**Conclusão:** a arquitetura é viável e a preparação foi bem direcionada, porém
o cutover permanece bloqueado até a imagem nova, o ensaio de restore, a validação
de Caddy/TLS e a cópia final com freeze humano.

## 2. Estado verificado

| Área | Estado | Evidência/observação |
|---|---|---|
| Código | `origin/main` integrado na branch | Merge local `59ba329`; `main` não foi alterado |
| VM Azure | Canário previamente saudável | Debian 12, Docker/Compose, Caddy nativo e volume em `/opt/roleta/data` |
| ACR | Existente; imagem anterior defasada | Nova esteira publica `roleta-cloud` e `roleta-cdc-worker` por SHA/digest |
| Key Vault | Existente e usado por Managed Identity | API key, PG, domínio e e-mail são lidos em runtime |
| Storage | Existente para backups | MI deve manter `Storage Blob Data Contributor` |
| PostgreSQL | Schema/grants aplicados até `0010_dir3_phase_columns` | `roleta_app` teve escrita em `shared.outbox` validada |
| SQLite | Fonte autoritativa da Onda 1 | Cópia anterior validada com contagens e checksums |
| `state.json` | Persistência no bind `/opt/roleta/data` | Seed canário agora exige autorização explícita |
| `dual_write_pg` | **OFF** | Não é ligado pela simples presença da DSN |
| CDC | Profile Azure adicionado, default inerte | Só sobe com `--with-pg --with-cdc` |
| DNS/TLS | Não executado | Domínio real só deve ser carregado após o flip |
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
| A-02 | Crítica | Imagem Azure ficaria anterior à V5/#47 | `.github/workflows/acr-image.yml` publica app e CDC a partir de `main`, com tags por SHA e digest no summary | Código corrigido; workflow ainda precisa rodar |
| A-03 | Alta | Frontend da imagem não era sincronizado para `/var/www/roleta` | `deploy-azure.sh` extrai e valida `index.html`, `app.js`, `style.css`; publica após health com backup local | Código corrigido; precisa redeploy |
| A-04 | Alta | `state.json` ausente podia virar seed sintético sem distinção de produção | Seed agora é default-OFF; ausência ou `__canary_seed__` bloqueia deploy sem `--allow-canary-seed` | Código corrigido |
| A-05 | Alta | DSN PG era montada com senha crua e podia desaparecer silenciosamente | URL encoding via Python; DSN é preservada por padrão e só é removida com `--without-pg`; argumentos desconhecidos falham | Código corrigido |
| A-06 | Alta | `CADDY_EMAIL` era staged, mas não consumido pelo Caddyfile | Diretiva global `email {$CADDY_EMAIL}`; `kv-to-env.sh` prepara domínio/e-mail em arquivo separado; drop-in systemd foi versionado | Código corrigido; Caddy deve ser validado na VM |
| A-07 | Alta | Backup não fazia `integrity_check`, mascarava erro RBAC e não tinha restore operacional | Backup valida SQLite/JSON, grava manifesto SHA-256 e não mascara `container create`; novo restore pareado e seguro | Código corrigido; drill humano pendente |
| A-08 | Média | Não havia retenção/lifecycle versionado para Blob | `set-blob-lifecycle.sh` reconcilia somente a regra Roleta e preserva regras existentes | Código corrigido; aplicar no Storage |
| A-09 | Alta | Onda PG não tinha `cdc-worker` no compose Azure | Serviço adicionado no profile `cdc`, com imagem própria no ACR e default inerte | Código corrigido; não ativar sem gate |
| A-10 | Média | `COPY . .` podia assar banco/estado/modelos binários em camadas | `.dockerignore` exclui `data/`, bancos e artefatos binários; mantém código fonte em `models/` | Código corrigido |
| A-11 | Média | Scripts legados de archive faziam push/reset/deploy direto em `main` e tinham destino HostDime fixo | `archive/deploy.sh` e `archive/deploy.ps1` removidos; histórico textual permanece apenas como snapshot | Corrigido |
| A-12 | Média | Runbooks usavam `docker-compose.azure.yml`, embora o arquivo real fosse `compose.azure.yml` | Referências operacionais corrigidas no plano e README | Corrigido |

### Riscos ainda existentes, não automatizados

| ID | Severidade | Risco | Ação recomendada | Dono |
|---|---|---|---|---|
| R-01 | Crítica | A nova imagem ainda não foi publicada/reimplantada nesta branch | Executar workflow ACR, registrar digest e fazer deploy Azure por digest | Agente + aprovação |
| R-02 | Crítica | Freeze e cópia final semântica ainda não ocorreram | Parar escrita HostDime, `.backup`, validar hash/contagens, restaurar em `/opt/roleta/data` | Humano |
| R-03 | Crítica | DNS e revogação de credenciais podem deixar dois escritores | Aplicar C-01…C-25; revogar `SERVER_*`/`SSH_PRIVATE_KEY` após cutover | Humano |
| R-04 | Alta | `CADDY_EMAIL` pode quebrar reload se o `EnvironmentFile` não estiver instalado | Instalar `/etc/caddy/caddy.env`, executar `caddy validate` e só então recarregar | Humano |
| R-05 | Alta | A política de purge protection do Key Vault estava desativada | Ativar purge protection/soft delete conforme política Azure | Humano |
| R-06 | Alta | Não há IaC versionado para reconstruir RG/VNet/NSG/MI/PG/Storage | Criar Bicep/Terraform em sprint próprio, com plan e aprovação | Próximo sprint |
| R-07 | Média | Backup diário implica RPO potencial de até 24 horas | Durante o soak, reduzir para intervalo compatível com RPO acordado e medir restore | Humano + SRE |
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
| `python -m pytest tests/ -q --tb=short` | **775 passed, 9 skipped, 1 xfailed** |
| `python tools/lint_silent_except.py` | OK (124 exceções catalogadas) |
| `git diff --check` | OK |
| `origin/main` integrado | OK (`59ba329` contém `19ba0ca`) |
| Validação Caddy local | Não disponível: binário `caddy` não instalado neste workspace |
| Deploy real após as correções | Ainda não executado; exige PR/ação controlada na VM |

Os testes Python e o lint local estão verdes. Ainda faltam os testes de
integração Azure: a ausência de Caddy local não deve ser convertida em
aprovação; a VM precisa executar `caddy validate` com o `EnvironmentFile` real.

## 7. Gates humanos obrigatórios

1. Confirmar OIDC do GitHub e `AcrPush` para a identidade do workflow.
2. Executar `Publish Azure images` a partir do `main` e registrar os dois digests.
3. Copiar os artefatos desta branch para `/opt/roleta`, executar o deploy sem
   seed canário e validar saúde, frontend, WSS e portas loopback.
4. Aplicar `set-blob-lifecycle.sh` e executar backup/restore em diretório de
   ensaio; registrar RPO/RTO medidos.
5. Fazer freeze da HostDime, parar timers/units/ingress conforme C-01…C-15,
   gerar `.backup` final e reconciliar `rowid`, contagens, `spin_seq` e hashes.
6. Restaurar no caminho efetivo `/opt/roleta/data`, validar o estado e só então
   iniciar a Azure com a imagem por digest.
7. Aprovar C-24, alterar DNS em C-25 e validar HTTPS/WSS externamente.
8. Depois de estabilizar, revogar credenciais de deploy HostDime e manter
   `HOSTDIME_DEPLOY_ENABLED` ausente ou `false`.
9. Não ligar `dual_write_pg` nem o CDC como parte do cutover SQLite; isso exige
   uma janela e um plano de reconciliação próprios.

## 8. Próximos passos recomendados

| Ordem | Passo | Critério de saída |
|---:|---|---|
| 1 | Entregar esta branch por PR e revisar o diff | CI verde, sem mudança de estratégia |
| 2 | Publicar imagens ACR por OIDC | Digest app/CDC registrado e reproduzível |
| 3 | Redeploy do canário | health 200, frontend da mesma imagem, WSS OK |
| 4 | Drill backup/restore + lifecycle | `integrity_check=ok`, RTO medido, política preservada |
| 5 | Ensaio final de cutover | Paridade de contagens/estado e rollback documentado |
| 6 | Freeze + DNS + fencing | Um único escritor e credenciais antigas revogadas |
| 7 | IaC e hardening | Azure reconstruível, purge protection e SLO/RPO formalizados |
| 8 | Onda PG | CDC/dual-write somente após soak e reconciliação |

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

**A preparação Azure é tecnicamente aproveitável, mas o cutover ainda não está
autorizado.** Os bugs de automação, seed, frontend, DSN, Caddy, backup, CDC,
contexto Docker e fencing CI foram corrigidos na branch. Permanecem como gates
reais: publicar/reimplantar a imagem atual, fazer o drill de restore, executar
freeze/cópia final, apontar DNS e revogar o caminho de deploy HostDime. Nenhuma
dessas ações deve ser inferida a partir de um teste local ou executada
automaticamente pelo PR.
