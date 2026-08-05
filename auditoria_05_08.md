# Auditoria sênior — Azure, HostDime e migração Roleta Cloud

**Data:** 2026-08-05
**Branch auditada:** `ivandirfilho-project-health-overview`
**Base funcional:** `origin/main` em `f165f91` (V5.1 + metodologia de sprints)
**Entrega da auditoria:** `cfd7fad`
**Sincronização V5.1:** `b82d2bfc17af`
**Hardening pré-cutover:** `a0eac98`, `3afa970`, `5da3132`, `cd2250a`
**Escopo:** arquitetura, runtime Azure, lift-and-shift HostDime → Azure, persistência,
CI/CD, segurança operacional, backup/restore, PostgreSQL, Caddy e documentação.

> Esta auditoria foi executada sem alterar `main`, sem fazer cutover DNS, sem
> desligar a HostDime e sem ligar `dual_write_pg`. A imagem foi publicada por
> digest imutável, o canário foi redeployado e a réplica quente foi ativada. O
> cutover continua bloqueado apenas pelos gates humanos de freeze, promoção,
> abertura do WebSocket e DNS.

## 1. Veredito executivo

O desenho em duas ondas continua correto:

1. **Onda 1 — lift-and-shift:** VM Azure + Caddy + SQLite autoritativo + Blob
   para backup; PostgreSQL preparado, mas não autoritativo.
2. **Onda 2 — modernização:** PostgreSQL/CDC/dual-write somente após soak,
   reconciliação e gate humano.

O runtime atual usa a imagem `azure-a0eac98`, digest
`sha256:75018ac2ba0e46dafaeefd9401df4b3099b6485e3e46a2f16462050cbf69c8ff`.
Frontend, health, persistência por WebSocket e restart foram comprovados. O
canário HTTPS responde em `20-226-77-194.sslip.io` com certificado público e
TLS 1.3, mas o WebSocket externo permanece bloqueado em 403.

A HostDime continua como único escritor. Ela produz snapshots consistentes a
cada 10 minutos no container dedicado `hostdime-standby`; a Azure consulta os
manifests a cada 2 minutos e atualiza somente `/opt/roleta/standby`. Três
restores completos mediram 5,142 s, 5,049 s e 4,904 s. O pipeline automático
foi observado aplicando `20260805T201513Z` às `20:16:08Z` e, após o hardening,
`20260805T202906Z` com idade de 12 s; o ciclo seguinte aplicou
`20260805T203000Z` automaticamente.

**Conclusão:** a preparação técnica pré-cutover está concluída. Não resta
construção de infraestrutura para a janela; resta a decisão humana irreversível
de congelar a HostDime, promover um stamp final explícito, abrir o WebSocket e
alterar o DNS.

## 2. Estado verificado

| Área | Estado | Evidência/observação |
|---|---|---|
| Código | Hardening pré-cutover publicado na branch/PR | `a0eac98`, `3afa970`, `5da3132`, `cd2250a`; `main` não foi alterado |
| VM Azure | Canário saudável | Debian 12, Docker/Compose, Caddy nativo e volume em `/opt/roleta/data` |
| ACR | Imagem V5.2 por digest | `roleta-cloud:azure-a0eac98`, digest `sha256:75018ac…c8ff` |
| Key Vault | Existente e usado por Managed Identity | API key, PG, domínio e e-mail são lidos em runtime |
| Storage | Backup e réplica quente validados | Versioning + soft delete 30 d; lifecycle cool 7 d/delete 30 d nos três prefixes |
| PostgreSQL | Schema/grants aplicados até `0010_dir3_phase_columns` | `roleta_app` teve escrita em `shared.outbox` validada |
| SQLite | Fonte autoritativa da Onda 1 | Origem viva na HostDime; snapshots `.backup` e standby com `integrity_check=ok` |
| `state.json` | Replicado junto do DB | JSON e SHA-256 validados antes da troca atômica no standby |
| `dual_write_pg` | **OFF** | Consultado em `shared.feature_flags`; DSN preparada não altera o flag |
| CDC | **Ausente/inativo** | Profile só sobe com `--with-pg --with-cdc` |
| DNS/TLS | TLS canário provado; DNS intacto | HTTPS 200, redirect 308, certificado Let's Encrypt/TLS 1.3; WSS externo 403 |
| HostDime | Produção e único escritor | Snapshot timer ativo; freeze, fencing e revogação continuam gates humanos |

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

HostDime autoritativa
  └─ snapshot 10 min → Blob hostdime-standby/snapshots/
                         └─ poll 2 min → /opt/roleta/standby
                                            (não montado no app)

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
- **TLS canário por `sslip.io`:** prova 443/ACME sem antecipar o domínio real nem
  liberar escrita; o TLS de produção continua condicionado ao DNS.
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
| A-07 | Alta | Backup não fazia `integrity_check`, mascarava erro RBAC e não tinha restore operacional | Backup valida SQLite/JSON, grava manifesto SHA-256 e não mascara `container create`; novo restore pareado e seguro | Backup e três restores OK |
| A-08 | Média | Não havia retenção/lifecycle versionado para Blob | `set-blob-lifecycle.sh` reconcilia somente a regra Roleta e preserva regras existentes | Aplicado a `backups/sqlite/`, `backups/azure-local/` e `hostdime-standby/snapshots/` |
| A-09 | Alta | Onda PG não tinha `cdc-worker` no compose Azure | Serviço adicionado no profile `cdc`, com imagem própria no ACR e default inerte | Código corrigido; não ativar sem gate |
| A-10 | Média | `COPY . .` podia assar banco/estado/modelos binários em camadas | `.dockerignore` exclui `data/`, bancos e artefatos binários; mantém código fonte em `models/` | Código corrigido |
| A-11 | Média | Scripts legados de archive faziam push/reset/deploy direto em `main` e tinham destino HostDime fixo | `archive/deploy.sh` e `archive/deploy.ps1` removidos; histórico textual permanece apenas como snapshot | Corrigido |
| A-12 | Média | Runbooks usavam `docker-compose.azure.yml`, embora o arquivo real fosse `compose.azure.yml` | Referências operacionais corrigidas no plano e README | Corrigido |
| A-13 | Alta | O `show` de lifecycle devolve regras em `policy.rules`, mas o reconciliador lia somente o nível raiz; a MI da VM também não possui permissão de plano de controle | Script aceita a forma real do payload e separa `AZURE_AUTH_MODE=identity|user`; runbook orienta execução por operador/CI sem ampliar RBAC da VM | Corrigido; regra aplicada por Owner |
| A-14 | Crítica | O canário aceitava escritores WebSocket públicos sem autenticação funcional | Caddy aplica allowlist por CIDR e responde 403 por padrão; arquivo de cutover libera somente na janela | Corrigido e provado externamente |
| A-15 | Alta | Frontend retornava 403 por diretório staging 0700 | Deploy normaliza diretórios 0755/arquivos 0644 e valida os três assets por HTTP com rollback | Corrigido; três assets em 200 |
| A-16 | Alta | A Azure tinha dados stale e nenhum pipeline contínuo HostDime → standby | Snapshot manifest-last, container dedicado e units systemd instalados em ambos os hosts | Corrigido; avanço automático observado |
| A-17 | Alta | O primeiro restore deixava WAL/SHM e quebrava a segunda execução | Snapshot restaurado é normalizado para `journal_mode=DELETE`; o script falha se gerar sidecar | Corrigido; três restores consecutivos OK |
| A-18 | Alta | Timers sincronizados podiam perder o snapshot novo; listagem Blob truncaria após 5.000 objetos e permitia rollback silencioso | Fonte 10 min, poll 2 min, `AccuracySec=1s`, manifesto filtrado server-side com paginação total, guard monotônico e stale gate de 900 s | Corrigido e implantado |
| A-19 | Alta | O domínio staged era o FQDN técnico da VM; ao trocar para dois domínios reais, `SITE_ADDRESS` sem aspas quebrava o shell | `ROLETA-DOMAIN` corrigido no Key Vault e `kv-to-env.sh` passou a serializar o valor entre aspas | Staging regenerado e `caddy validate` OK; canário ativo preservado |

### Riscos ainda existentes, não automatizados

| ID | Severidade | Risco | Ação recomendada | Dono |
|---|---|---|---|---|
| R-01 | Crítica | O workflow OIDC ainda depende de secrets Azure não configurados no repositório | Manter o digest manual registrado até configurar OIDC e repetir a esteira a partir de `main` | Humano |
| R-02 | Crítica | Freeze e promoção final ainda não ocorreram | Parar escrita HostDime, gerar stamp final, validar hash/contagens e promover esse stamp em `/opt/roleta/data` | Humano |
| R-03 | Crítica | DNS e revogação de credenciais podem deixar dois escritores | Aplicar C-01…C-25; revogar `SERVER_*`/`SSH_PRIVATE_KEY` após cutover | Humano |
| R-04 | Alta | Ambiente Caddy de produção ainda depende do domínio real | `cutover-caddy.sh` faz validate/reload/rollback; TLS canário já passou | Aplicar arquivo staged no cutover |
| R-05 | Alta | A política de purge protection do Key Vault estava desativada | Ativar purge protection/soft delete conforme política Azure | Humano |
| R-06 | Alta | Não há IaC versionado para reconstruir RG/VNet/NSG/MI/PG/Storage | Criar Bicep/Terraform em sprint próprio, com plan e aprovação | Próximo sprint |
| R-07 | Média | Falha dos timers precisa ser observada fora do journal | Poll falha se o snapshot tiver >900 s e grava status; integrar esse estado ao monitoramento após o cutover | SRE |
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
- lista somente manifests com paginação total e recusa regressão de stamp;
- falha se a réplica automática tiver idade superior a 900 s;
- usa `quick_check` no no-op e `integrity_check` na aplicação;
- normaliza o DB para journal DELETE e rejeita WAL/SHM residuais;
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
| `python -m pytest tests/ -q --tb=short` | **809 passed, 10 skipped, 1 xfailed** |
| `python tools/lint_silent_except.py` | OK (128 exceções catalogadas) |
| `git diff --check` | OK |
| `origin/main` integrado | `f165f91`; somente metodologia/sprints após a base V5.1 |
| Validação Caddy na VM | Config ativa e staging de produção: `caddy validate` OK |
| CI do PR #43 | OK: guardrails + Python 3.11/3.12/3.13 |

Os testes locais, a CI e os testes de integração na VM estão verdes. O Caddy foi
validado com o `EnvironmentFile` ativo e com o staging dos dois domínios reais.

## 6.1 Evidências Azure executadas

| Verificação | Resultado |
|---|---|
| Imagem app | `roleta-cloud:azure-a0eac98`, digest `sha256:75018ac…c8ff` |
| Deploy canário | Backend 4.4.1 saudável; volume ativo preservado |
| Persistência real | 101 spins via protocolo WebSocket isolado; `spin_seq` 55→156; restart OK; INV-3 sempre `APOSTAR` |
| Backend/Caddy | `/healthz` 200; app somente em `127.0.0.1:8765/8766` |
| Frontend | `/`, `/app.js` e `/style.css`: HTTPS 200 |
| TLS | `20-226-77-194.sslip.io`; redirect 308; Let's Encrypt; TLS 1.3; validade até 2026-11-03 |
| WebSocket | externo 403 no canário; abertura pública somente pelo ambiente staged |
| PostgreSQL/CDC | DSN preparada, `dual_write_pg=false`, worker ausente |
| Snapshot HostDime | timer 10 min ativo; SAS Create+Write revogável; manifest-last e `integrity_check=ok` |
| Standby Azure | poll 2 min ativo; `/opt/roleta/standby`; stale gate 900 s |
| Restore | três execuções: 5,142 s / 5,049 s / 4,904 s; no-op 1,883 s; sem WAL/SHM |
| Prova automática | `201513Z` restaurado às `20:16:08Z`; `202906Z` com 12 s; ciclo seguinte `203000Z` aplicado às `20:32:05Z` com 122 s |
| Backup Azure-local | timer 6 h ativo; manifests `20260805T200537Z` e `20260805T201200Z` |
| Lifecycle | cool 7 d/delete 30 d em todos os prefixes de SQLite e standby |

## 7. Gates humanos obrigatórios

1. Configurar OIDC do GitHub (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_SUBSCRIPTION_ID`) e repetir a esteira a partir de `main`; o publish
   manual desta auditoria já está registrado por digest.
2. Aprovar a janela e congelar o único escritor: bloquear `/ws`, parar o
   container HostDime e desabilitar o timer de deploy.
3. Executar o snapshot final manual, registrar o stamp e comparar manifesto,
   contagens, último timestamp, `spin_seq` e hashes.
4. Parar o app Azure, mover o canário ativo para backup e restaurar **esse stamp
   explícito** em `/opt/roleta/data`; não promover apenas “o latest”.
5. Validar o estado, iniciar Azure ainda com WSS bloqueado, aplicar o ambiente
   Caddy staged e alterar DNS.
6. Confirmar HTTPS/WSS externamente e manter a HostDime fenced.
7. Revogar `hostdime-migration-push`, credenciais de deploy HostDime e manter
   `HOSTDIME_DEPLOY_ENABLED` ausente ou `false`.
8. Não ligar `dual_write_pg` nem o CDC como parte do cutover SQLite; isso exige
   uma janela e um plano de reconciliação próprios.

## 8. Próximos passos recomendados

| Ordem | Passo | Critério de saída |
|---:|---|---|
| 1 | Entregar esta branch por PR e revisar o diff | CI verde, sem mudança de estratégia |
| 2 | Configurar OIDC e repetir publicação a partir de `main` | Digest app/CDC registrado pela esteira |
| 3 | Freeze + promoção do stamp final | Paridade de contagens/estado e app Azure healthy |
| 4 | Caddy + DNS + fencing | Um único escritor, HTTPS/WSS e credenciais antigas revogadas |
| 5 | IaC/monitoramento | Azure reconstruível e stale gate integrado a alerta |
| 6 | Onda PG | CDC/dual-write somente após soak e reconciliação |

## 9. Limitações do Graphify e rastreabilidade

O `graphify update .` final reconstruiu o grafo de código com **1.454 nós,
1.654 arestas e 156 comunidades**. O transporte do MCP Graphify permaneceu
fechado; por isso a auditoria usou o CLI local, o grafo regenerado e a leitura
dos arquivos efetivos. As consultas semânticas de documentos continuam
dependentes de backend LLM, mas isso não afeta a prova operacional executada nos
dois hosts.

`graphify-out/` continua fora do versionamento. A atualização do grafo deve ser
feita localmente após o merge, sem adicionar o artefato pesado ao PR.

## 10. Resultado final

**A Azure está tecnicamente pronta para o cutover, mas o cutover ainda não está
autorizado.** Imagem, frontend, health, persistência, TLS, backup, três restores
e réplica quente automática foram comprovados. O caminho de dados permanece
unidirecional e a HostDime é o único escritor. Restam somente ações humanas
deliberadamente irreversíveis: freeze, snapshot final, promoção explícita,
abertura do WSS, DNS e fencing/revogação. O PostgreSQL e o CDC não fazem parte
dessa janela.
