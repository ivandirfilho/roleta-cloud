# 🧪 Guia de Testes - Backend com Monitoramento

## ✅ Implementação Completa

O backend foi implementado com **abordagem zero-conflict**. Todas as funcionalidades antigas continuam funcionando + novas features de monitoramento.

---

## 📋 Pré-requisitos

1. ✅ Dashboard frontend instalado
2. ✅ Backend atualizado
3. ✅ Chrome com extensão recarregada

---

## 🧪 TESTE 1: Verificar Retrocompatibilidade

### Objetivo: Garantir que arquivo antigo continua funcionando

### Passos:
1. Carregue um arquivo JSON **ANTIGO** (sem campo `monitoring`)
2. Clique em "INICIAR ESCUTA"
3. Abra o Console do Service Worker

### ✅ Resultado Esperado:
```
🔄 Iniciando loop de 1 segundo
📊 Leitura #1: 13 elementos, 12 números: [14, 23, 8, 5, 17]
📌 Hash inicial definido: 14,23,8,5,17
```

### ✅ Dashboard:
- Traffic Light: ⏳ AGUARDANDO (amarelo)
- Saldo: R$ 0,00
- Na mesa: R$ 0,00
- Ficha: -

### ❌ Se falhar:
- Erro no console: "Cannot read property..."
- **PROBLEMA**: Código modificado incorretamente

---

## 🧪 TESTE 2: Simular Monitoramento com Dados Fake

### Objetivo: Testar dashboard sem arquivo v15

### Passos:
1. Abra Console do Service Worker
2. Cole este código:

```javascript
chrome.storage.local.get(['escutaState'], (data) => {
  const state = data.escutaState || {};
  state.monitoringData = {
    gameStatus: "FAÇAM SUAS APOSTAS",
    balance: 1380.00,
    currentBet: 50.00,
    activeChip: 2.5
  };
  chrome.storage.local.set({ escutaState: state }, () => {
    console.log('✅ Monitoramento simulado!');
  });
});
```

3. Abra o popup

### ✅ Resultado Esperado:
- Traffic Light: 🟢 ABERTO (verde)
- Saldo: R$ 1.380,00
- Na mesa: R$ 50,00
- Ficha: R$ 2,50

---

## 🧪 TESTE 3: Arquivo v15 com Seletores Inválidos

### Objetivo: Testar resiliência a erros

### Passos:
1. Use o arquivo `extrator_completo_v15_example.json`
2. Os seletores são de exemplo e não existem na página
3. Carregue o arquivo
4. Inicie a escuta

### ✅ Resultado Esperado:
- Console: `⚠️ Erro ao coletar monitoramento: ...`
- Grid de números: **Continua funcionando** ✅
- Dashboard: Valores padrão (R$ 0,00)
- **NÃO DEVE QUEBRAR A EXTENSÃO**

---

## 🧪 TESTE 4: Inspecionar BroadcastState

### Objetivo: Verificar estrutura de dados para o Executor

### Passos:
1. Com a escuta ativa
2. Abra Console do Service Worker
3. Cole:

```javascript
chrome.storage.local.get(['escutaState'], (data) => {
  console.log('📡 BroadcastState:', data.escutaState.broadcastState);
  console.log('💰 MonitoringData:', data.escutaState.monitoringData);
  console.log('🎯 Targets:', Object.keys(data.escutaState.broadcastState?.targets || {}));
});
```

### ✅ Resultado Esperado (com arquivo v15):
```javascript
📡 BroadcastState: {
  timestamp: 1702123456789,
  liveState: {
    status: "OPEN",
    balance: 1380.00,
    currentRoundBet: 50.00,
    activeChipValue: 2.50,
    lastResults: [14, 23, 8, ...]
  },
  executionConfig: { ... },
  availableChips: [0.5, 1, 2.5, ...],
  targets: {
    "0": "[data-bet-spot-id='0']",
    "17": "[data-bet-spot-id='17']",
    ...
  }
}
```

---

## 🧪 TESTE 5: Mudança de Status em Tempo Real

### Objetivo: Verificar atualização automática

### Passos:
1. Com escuta ativa e monitoramento funcionando
2. No console do Service Worker, simule mudança:

```javascript
// Simular mudança para FECHADO
chrome.storage.local.get(['escutaState'], (data) => {
  const state = data.escutaState;
  state.monitoringData.gameStatus = "NÃO ACEITAMOS MAIS APOSTAS";
  chrome.storage.local.set({ escutaState: state });
});
```

3. Abra o popup

### ✅ Resultado Esperado:
- Traffic Light muda para: 🔴 FECHADO (vermelho)

### Testar ABERTO novamente:
```javascript
chrome.storage.local.get(['escutaState'], (data) => {
  const state = data.escutaState;
  state.monitoringData.gameStatus = "FAÇAM SUAS APOSTAS";
  chrome.storage.local.set({ escutaState: state });
});
```

- Traffic Light muda para: 🟢 ABERTO (verde)

---

## 🧪 TESTE 6: Limpeza de Valores Financeiros

### Objetivo: Testar função cleanFinancialValue

### Passos:
1. Console do Service Worker:

```javascript
// Testar diferentes formatos
const valores = [
  "R$ 1.380,00",      // Esperado: 1380.00
  "R$ 50,00",         // Esperado: 50.00
  "1.234,56",         // Esperado: 1234.56
  "R$\u00A02.500,00", // Esperado: 2500.00 (com espaço não quebrável)
  "25",               // Esperado: 25.00
  "",                 // Esperado: 0
  null                // Esperado: 0
];

// Copie a função cleanFinancialValue do background.js
function cleanFinancialValue(rawText) {
  if (!rawText) return 0;
  let cleaned = rawText
    .replace(/R\$/g, '')
    .replace(/\u00A0/g, '')
    .replace(/\s+/g, '')
    .trim();
  cleaned = cleaned.replace(/\./g, '');
  cleaned = cleaned.replace(/,/g, '.');
  const value = parseFloat(cleaned);
  return isNaN(value) ? 0 : value;
}

// Testar
valores.forEach(v => {
  console.log(`"${v}" → ${cleanFinancialValue(v)}`);
});
```

### ✅ Resultado Esperado:
```
"R$ 1.380,00" → 1380
"R$ 50,00" → 50
"1.234,56" → 1234.56
"R$ 2.500,00" → 2500
"25" → 25
"" → 0
"null" → 0
```

---

## 🧪 TESTE 7: Performance (2 Injeções)

### Objetivo: Verificar impacto de performance

### Passos:
1. Arquivo v15 carregado
2. Escuta ativa
3. Observe console por 30 segundos

### ✅ Resultado Esperado:
- Logs a cada 10 leituras (não a cada 1s)
- CPU não deve sobrecarregar
- Memória estável

### ⚠️ Se CPU alta:
- Aumentar intervalo de log
- Desabilitar logs desnecessários

---

## 🧪 TESTE 8: Integração com Executor (Preparação)

### Objetivo: Simular leitura pelo Executor

### Passos:
1. Com escuta e monitoramento ativos
2. Simule código do Executor:

```javascript
// Como o Executor vai consumir os dados
chrome.storage.local.get(['escutaState'], (data) => {
  const broadcast = data.escutaState.broadcastState;
  
  if (!broadcast) {
    console.log('❌ BroadcastState não disponível');
    return;
  }
  
  console.log('=== DADOS PARA EXECUTOR ===');
  console.log('Status:', broadcast.liveState.status);
  console.log('Saldo:', broadcast.liveState.balance);
  console.log('Pode apostar?', broadcast.liveState.status === 'OPEN');
  console.log('Últimos números:', broadcast.liveState.lastResults);
  console.log('Seletor para apostar no 17:', broadcast.targets['17']);
  console.log('Seletor para apostar no RED:', broadcast.targets['red']);
  console.log('Config de click:', broadcast.executionConfig);
});
```

### ✅ Resultado Esperado:
```
=== DADOS PARA EXECUTOR ===
Status: OPEN
Saldo: 1380
Pode apostar? true
Últimos números: [14, 23, 8, 5, 17, ...]
Seletor para apostar no 17: [data-bet-spot-id='17']
Seletor para apostar no RED: [data-bet-spot-id='red']
Config de click: { interactionMethod: "PointerEvent", ... }
```

---

## 📊 Checklist Final

Após todos os testes, marque:

- [ ] Arquivo antigo funciona normalmente
- [ ] Dashboard atualiza com dados simulados
- [ ] Erro em monitoramento não quebra extensão
- [ ] BroadcastState tem estrutura correta
- [ ] Traffic Light muda de cor conforme status
- [ ] Limpeza de valores financeiros funciona
- [ ] Performance aceitável (CPU < 10%)
- [ ] Executor pode consumir dados via storage

---

## 🎯 Próximos Passos

1. ✅ Backend testado e funcionando
2. 🔧 Criar arquivo v15 com seletores reais do site
3. 🔧 Implementar Executor Beat
4. 🚀 Integração completa

---

## 🆘 Troubleshooting

### Dashboard não atualiza mesmo com dados:
```javascript
// Forçar atualização
chrome.storage.local.get(['escutaState'], (data) => {
  chrome.storage.local.set({ escutaState: data.escutaState });
});
```

### Ver estado completo:
```javascript
chrome.storage.local.get(['escutaState'], (data) => {
  console.log(JSON.stringify(data.escutaState, null, 2));
});
```

### Limpar estado:
```javascript
chrome.storage.local.remove('escutaState', () => {
  console.log('Estado limpo! Recarregue a extensão.');
});
```

---

**Status**: ✅ Backend pronto para testes!


