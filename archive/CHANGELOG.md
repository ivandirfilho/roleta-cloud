# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado
- `backtest_from_db.py` - Ferramenta de backtest integrada com banco de dados
- Análise separada por direção (CW/CCW) no backtest
- Campo `bet_placed` no heartbeat para sincronização correta do overlay
- Auditoria completa do sistema (`auditoria_sistema.md`)

### Corrigido
- **Martingale Sync**: Overlay não sincroniza gale quando ação é PULAR
- **test_core.py**: Corrigido import do módulo core
- **Content.js**: Timer mostra "Aguardando aposta" quando PULAR

### Alterado
- `.gitignore` reorganizado com melhor estrutura e comentários
- `handleStateSync()` agora verifica `bet_placed` antes de atualizar gale

## [1.0.0] - 2026-01-21

### Adicionado
- Sistema de heartbeat para sincronização em tempo real
- Separação de históricos: `performance_sda17` vs `performance_bet`
- Martingale independente por direção (CW/CCW)
- Triple Rate Advisor com análise C4/M6/L12
- Database SQLite para logging de decisões
- Tabelas `gale_windows` e `window_plays` para análise ML

### Corrigido
- Contaminação de performance tracking entre direções
- Martingale atualizado incorretamente em jogadas puladas

---

## Formato de Commits

Este projeto usa [Conventional Commits](https://www.conventionalcommits.org/):

```
<tipo>[escopo opcional]: <descrição>

[corpo opcional]

[rodapé opcional]
```

### Tipos
- `feat`: Nova funcionalidade
- `fix`: Correção de bug
- `docs`: Documentação
- `style`: Formatação (não afeta código)
- `refactor`: Refatoração
- `test`: Testes
- `chore`: Manutenção

### Exemplos
```
fix(overlay): não sincroniza gale quando PULAR
feat(backtest): adiciona análise por direção CW/CCW
docs: atualiza README com novos endpoints
```
