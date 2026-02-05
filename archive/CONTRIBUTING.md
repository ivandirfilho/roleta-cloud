# Como Contribuir

## Estrutura de Branches

```
main          ← Produção (deploy automático)
  └── develop ← Desenvolvimento integrado
       └── feature/* ← Novas funcionalidades
       └── fix/* ← Correções
       └── hotfix/* ← Correções urgentes
```

## Fluxo de Trabalho

1. **Criar branch** a partir de `develop`:
   ```bash
   git checkout develop
   git pull
   git checkout -b feature/nome-da-feature
   ```

2. **Fazer commits** seguindo Conventional Commits:
   ```bash
   git commit -m "feat(scope): descrição curta"
   ```

3. **Push e Pull Request**:
   ```bash
   git push origin feature/nome-da-feature
   ```
   - Criar PR para `develop`
   - Aguardar review

## Padrões de Código

### Python
- Seguir PEP 8
- Type hints obrigatórios
- Docstrings em funções públicas
- Testes para lógica crítica

### Commits
- Mensagens em português ou inglês (consistente)
- Primeira linha até 50 caracteres
- Corpo opcional explicando "por quê"

## Checklist de PR

- [ ] Testes passando (`python test_core.py`)
- [ ] Sem erros de sintaxe (`python -m py_compile arquivo.py`)
- [ ] Documentação atualizada (se aplicável)
- [ ] CHANGELOG.md atualizado
- [ ] Sem secrets/credenciais no código
