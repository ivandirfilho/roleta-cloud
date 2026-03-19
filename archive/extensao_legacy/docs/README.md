# 👂 Escuta Beat - Extensão Chrome

Extensão para monitoramento de resultados de roleta em tempo real com dashboard de operações.

## 📁 Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `manifest.json` | Configuração da extensão Chrome |
| `popup.html` | Interface visual do popup + Dashboard |
| `popup.js` | Lógica de monitoramento e UI |
| `background.js` | Service Worker - Loop de leitura |
| `icons/` | Ícones da extensão (16, 48, 128px) |
| `DASHBOARD_README.md` | Documentação completa do Dashboard |
| `test_dashboard.js` | Scripts de teste para o Dashboard |

## 🚀 Instalação

1. Abra `chrome://extensions/`
2. Ative "Modo do desenvolvedor"
3. Clique "Carregar sem compactação"
4. Selecione esta pasta

## 📖 Uso

### 1. Monitoramento de Resultados
1. Carregue arquivo JSON do Extrator Beat
2. Clique "▶️ INICIAR ESCUTA"
3. Monitore os resultados em tempo real

### 2. Dashboard de Operações (Novo!)
- **Traffic Light**: Indicador visual de status (Aberto/Fechado)
- **Área Financeira**: Saldo e aposta atual
- **Ficha Ativa**: Valor da ficha selecionada

O Dashboard aparece automaticamente quando há dados de monitoramento.

## 🧪 Testando o Dashboard

1. Carregue a extensão
2. Vá em `chrome://extensions/`
3. Clique em "Service Worker" do Escuta Beat
4. Copie e cole o conteúdo de `test_dashboard.js` no console
5. Execute: `testeAutomatico()`
6. Abra o popup para ver o dashboard funcionando

## 📚 Documentação

- **Dashboard completo**: Veja `DASHBOARD_README.md`
- **Testes**: Veja `test_dashboard.js`

## 🔄 Versões

**v2.3** (Atual) - Backend com Monitoramento
- ✅ Dashboard de Operações com Traffic Light
- ✅ Área financeira (saldo, aposta, ficha)
- ✅ Formatação de moeda BRL
- ✅ **Backend refatorado com monitoramento em tempo real**
- ✅ **BroadcastState para integração com Executor**
- ✅ **Suporte a arquivo extrator_completo.json v15**
- ✅ **Arquitetura zero-conflict (retrocompatível)**
- ✅ Loop de leitura a cada 1 segundo
- ✅ Service Worker com keep-alive

**v2.2**
- Dashboard de Operações com Traffic Light
- Área financeira (saldo, aposta, ficha)
- Formatação de moeda BRL

**v2.1**
- Leitura a cada 1 segundo
- Debug detalhado

**v1.0.0**
- Monitor de resultados em tempo real








