# Auditoria LGPD — Roleta Cloud

Sprint `Sx-LGPD` do `plano_implentacao_pos_sessao_24_05.md`.
Última revisão: 2026-05-24 (pós S0.5 / pré S5).

---

## 1. Escopo de dados

| Camada | Conteúdo | Tipo |
|---|---|---|
| Browser (cliente) | número da roleta, força, decisão, resultado | Operacional, **sem PII** |
| WebSocket `:8765` | mesma carga, transit-only | Operacional |
| SQLite `data/decisions.db` | `decisions(session_id, ts, direction, force, hit, …)` | Operacional + `session_id` (UUID, sem link a pessoa) |
| PG `roleta-pg` (S4+) | `shared.strategy_versions`, `shared.feature_flags`, `cw/ccw.spins_vectors` | Operacional + vetores numéricos derivados |
| Logs (`roleta.log`, journald) | logs estruturados JSON; sem campos `email`, `cpf`, `phone` | Operacional |
| Repo Git | código + planos `.md` (este inclusive); **sem dumps de dados** | N/A |

**Sem dados pessoais de jogadores reais.** O sistema opera sobre números da roleta e
estatísticas derivadas; `session_id` é UUID4 gerado client-side, não derivado de
identidade.

---

## 2. Bases legais (Art. 7º LGPD)

Como **não há tratamento de PII**, LGPD Art. 7º não exige base legal específica
para a operação. As bases que se aplicam **se um dia incluirmos PII**:

| Base | Quando se aplicaria |
|---|---|
| Consentimento (Art. 7º I) | Se coletássemos email/telefone do operador via UI |
| Execução de contrato (V) | Se houvesse contas pagas → IDs faturáveis |
| Legítimo interesse (IX) | Telemetria anônima de uso |

**Estado atual: nenhum dos casos aplica.** Documento revisado a cada sprint que
toque schema do PG (vide `migrations/versions/*.py`).

---

## 3. Princípios LGPD aplicados

| Princípio (Art. 6º) | Cumprimento atual |
|---|---|
| Finalidade | Análise estatística da roleta; sem desvio |
| Adequação | Dados coletados batem com finalidade |
| Necessidade | Só persistimos features numéricas; sem fields cosméticos |
| Livre acesso | N/A (sem PII) — operador tem `docker exec` ao banco |
| Qualidade dos dados | INV-3 (zero skip) garante completude; validação em `database/models.py` |
| Transparência | Este documento + `plano_*.md` |
| Segurança | TLS via nginx (Let's Encrypt) + PG bind 127.0.0.1 + chave PG `chmod 600` |
| Prevenção | Backups + `docs/runbooks/rollback.md` |
| Não discriminação | N/A |
| Responsabilização | Owner único; trilha em `git log` |

---

## 4. Retenção

| Dado | Política | Onde |
|---|---|---|
| SQLite decisions | Indefinido (volume baixo, < 50MB/ano esperado) | `data/decisions.db` |
| PG `spins_vectors` | TTL 12 meses a partir de S6 (cron de purge a ser criado em S10) | `cw/ccw.spins_vectors.ts` |
| Logs JSON | 30 dias rotação (logrotate configurar em Sx-OBS) | `roleta.log` + journald |
| Backups PG | 30 dias local + 90 dias B2 (S4-BAK) | `/backups/pg/` + Backblaze |

---

## 5. Direitos do titular (Art. 18)

Como não há titular identificado, não há solicitação possível. Se vier:
- **Acesso/portabilidade:** dump JSON do `session_id` (operador roda query).
- **Eliminação:** `DELETE FROM decisions WHERE session_id = ?` + replicar nos backups.
- **Anonimização:** já default — session_id ≠ identidade.

---

## 6. Hosting

| Componente | Local | Jurisdição |
|---|---|---|
| VPS Debian | HostDime Fortaleza/CE | 🇧🇷 Brasil |
| Backups B2 (S4-BAK) | Backblaze us-west-001 | 🇺🇸 USA |
| Repo Git | GitHub (Microsoft) | 🇺🇸 USA |
| Build CI | GitHub Actions | 🇺🇸 USA |

**Para PII brasileira**, mover backups para região br seria recomendado.
Atualmente irrelevante (sem PII). Se mudar: documentar via Termos B2 (Standard
Contractual Clauses) ou trocar provedor.

---

## 7. Gatilhos para reaudit

Reauditar este documento **automaticamente** sempre que:
- [ ] Schema PG ganhar coluna que pareça nome/email/phone/cpf/endereço
- [ ] Frontend ganhar tela de login com credenciais
- [ ] App passar a chamar API externa enviando dados de operador
- [ ] Backup sair do BR sem clausula contratual nova

Procedimento de reaudit: revisar este `.md`, atualizar tabela §1, regenerar
checklist §3, bumpar tag (`v.x.y-lgpd-revisão-YYYY-MM-DD`).

---

## 8. Conclusão

**Status atual: 🟢 Conforme.** Sistema processa dados operacionais não-pessoais;
nenhuma das obrigações específicas de PII (DPO, ROPA detalhado, AIPD) é
exigível. Documento existe para evitar virada silenciosa de escopo.
