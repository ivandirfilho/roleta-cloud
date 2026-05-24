# Gestão de Secrets — sops + age — Sx-SEC

Sprint `Sx-SEC` do `plano_implentacao_pos_sessao_24_05.md` (revisada A3:
sem Azure Key Vault; sops + age é o substituto Debian-first).

---

## Motivação

Hoje os secrets estão espalhados:

| Secret | Onde está | Risco |
|---|---|---|
| Senha PG | `/root/.pg_password` (chmod 600) | Backup do servidor traz; ngm além do root vê |
| `.env.pg` | `/root/roleta-cloud/.env.pg` | Gitignored ok |
| GitHub Actions secrets | repo Settings > Secrets (`SERVER_HOST`, `SSH_PRIVATE_KEY`, etc.) | Bom — fora do repo |
| Chave SSH operador | `~/.ssh/id_rsa` (Windows) | Local-only |

**O que sops resolve:** quando precisarmos versionar secrets junto ao código
(ex.: `.env.prod` com DSN, tokens, chaves de API de terceiros) sem expor em
texto plano. Cada operador autorizado tem sua chave `age`; o secret é
criptografado uma vez, decifrável pelas chaves listadas no `.sops.yaml`.

---

## Plano de adoção (faseado)

### Fase 1 — Preparação (sem risco, sem deploy)

1. **Gerar chave age do operador principal** (uma vez por máquina):
   ```bash
   # Linux/Mac
   age-keygen -o ~/.config/sops/age/keys.txt
   # Windows (PowerShell, via scoop ou choco)
   scoop install age
   age-keygen -o "$env:USERPROFILE\.config\sops\age\keys.txt"
   ```

   Anotar `# public key: age1...` — vai no `.sops.yaml`.

2. **Gerar chave age do servidor Debian**:
   ```bash
   ssh root@187.45.181.75 'mkdir -p /etc/sops && age-keygen -o /etc/sops/age.key && chmod 600 /etc/sops/age.key && grep "public key" /etc/sops/age.key'
   ```

3. **Criar `.sops.yaml`** na raiz do repo:
   ```yaml
   creation_rules:
     - path_regex: \.enc\.yaml$
       age: >-
         age1OPERADOR_PUBKEY,
         age1SERVER_PUBKEY
     - path_regex: secrets/.*\.enc\.(json|yaml)$
       age: >-
         age1OPERADOR_PUBKEY,
         age1SERVER_PUBKEY
   ```

### Fase 2 — Migrar secrets atuais

1. **PG password → `secrets/pg.enc.yaml`**:
   ```bash
   cat > /tmp/pg.yaml <<EOF
   pg_password: $(cat /root/.pg_password)
   EOF
   sops --encrypt --in-place /tmp/pg.yaml
   mv /tmp/pg.yaml secrets/pg.enc.yaml
   ```

2. **Commitar arquivo criptografado**: ok versionar, ninguém sem chave age decifra.

3. **No deploy**: `sops --decrypt secrets/pg.enc.yaml | yq '.pg_password' > /root/.pg_password`

### Fase 3 — Integração CI

Adicionar `SOPS_AGE_KEY` aos secrets do GitHub Actions (conteúdo de
`keys.txt` da máquina CI dedicada — gerar nova chave, não reusar a do
operador). Workflow decifra durante deploy.

---

## Por que NÃO fazer agora

- **Operador único** → vazamento da `/root/.pg_password` só acontece se atacante
  já for root. sops só agrega valor com múltiplos operadores ou múltiplos
  ambientes (staging/prod).
- **Custo de erro alto** → perder a chave age = perder acesso aos secrets
  criptografados. Precisa de backup da chave em local independente do servidor.
- **GitHub Secrets cobre 95%** dos casos atuais (SSH key, server host).

---

## Critérios para ativar

Adotar sops + age **quando**:
- [ ] Houver 2º operador com necessidade de produção
- [ ] Houver ambiente staging separado do prod
- [ ] Aparecer 3º secret novo (API key de provedor externo, JWT signing key, etc.)

Antes disso: 🟡 **DEFERRED** — política documentada, implementação adiada.

---

## Procedimento de rollback

Se sops for adotado e algo der errado:
1. Os secrets em `/root/.pg_password` continuam existindo (não vamos apagar até Fase 3 completar)
2. `docker compose --env-file .env.pg` continua funcionando
3. Reverter Fase 3 = remover `SOPS_AGE_KEY` do CI, voltar deploy.yml ao path antigo
4. Reverter Fase 2 = `git revert` dos commits que adicionaram `secrets/*.enc.yaml`

---

## Backup obrigatório

A chave `~/.config/sops/age/keys.txt` (operador) e `/etc/sops/age.key` (servidor)
**precisam** ter backup independente:

- **Operador**: pendrive USB criptografado + cópia em cofre físico
- **Servidor**: backup no Backblaze B2 sob path `secrets/age-key-server-YYYY-MM-DD.gpg` (cifrado com passphrase forte)

Sem backup → cenário catastrófico de perder acesso a todos os secrets. ⚠️
