// ============================================
// SCRIPT DE TESTE PARA O DASHBOARD
// ============================================
// 
// Como usar:
// 1. Carregue a extensão no Chrome
// 2. Vá em chrome://extensions/
// 3. Clique em "Service Worker" do Escuta Beat
// 4. Cole e execute as funções abaixo no console
//
// ============================================

// Função auxiliar para atualizar o estado
async function atualizarDashboard(dados) {
  return new Promise((resolve) => {
    chrome.storage.local.get(['escutaState'], (data) => {
      const state = data.escutaState || {};
      state.monitoringData = dados;
      
      chrome.storage.local.set({ escutaState: state }, () => {
        console.log('✅ Dashboard atualizado:', dados);
        resolve();
      });
    });
  });
}

// ============================================
// TESTES RÁPIDOS
// ============================================

// Teste 1: Status ABERTO (Verde)
function testeAberto() {
  atualizarDashboard({
    gameStatus: "FAÇAM SUAS APOSTAS",
    balance: 1380.00,
    currentBet: 50.00,
    activeChip: 2.5
  });
}

// Teste 2: Status FECHADO (Vermelho)
function testeFechado() {
  atualizarDashboard({
    gameStatus: "NÃO ACEITAMOS MAIS APOSTAS",
    balance: 1380.00,
    currentBet: 50.00,
    activeChip: 2.5
  });
}

// Teste 3: Status AGUARDANDO (Amarelo)
function testeAguardando() {
  atualizarDashboard({
    gameStatus: "PREPARANDO RODADA",
    balance: 1380.00,
    currentBet: 0,
    activeChip: 5.0
  });
}

// Teste 4: Simular vitória (saldo aumenta)
function testeVitoria() {
  atualizarDashboard({
    gameStatus: "FAÇAM SUAS APOSTAS",
    balance: 1500.00,
    currentBet: 0,
    activeChip: 2.5
  });
}

// Teste 5: Simular aposta em andamento
function testeAposta() {
  atualizarDashboard({
    gameStatus: "FECHADO",
    balance: 1280.00,
    currentBet: 100.00,
    activeChip: 10.0
  });
}

// Teste 6: Ocultar dashboard (remover monitoringData)
function testeOcultar() {
  chrome.storage.local.get(['escutaState'], (data) => {
    const state = data.escutaState || {};
    delete state.monitoringData;
    
    chrome.storage.local.set({ escutaState: state }, () => {
      console.log('✅ Dashboard ocultado');
    });
  });
}

// ============================================
// TESTE AUTOMÁTICO - CICLO COMPLETO
// ============================================
async function testeAutomatico() {
  console.log('🎬 Iniciando teste automático...');
  
  console.log('1️⃣ Status ABERTO');
  await testeAberto();
  await sleep(3000);
  
  console.log('2️⃣ Fazendo aposta...');
  await atualizarDashboard({
    gameStatus: "FAÇAM SUAS APOSTAS",
    balance: 1330.00,
    currentBet: 50.00,
    activeChip: 2.5
  });
  await sleep(3000);
  
  console.log('3️⃣ Status FECHADO');
  await testeFechado();
  await sleep(3000);
  
  console.log('4️⃣ AGUARDANDO resultado...');
  await testeAguardando();
  await sleep(3000);
  
  console.log('5️⃣ Vitória! 🎉');
  await atualizarDashboard({
    gameStatus: "FAÇAM SUAS APOSTAS",
    balance: 1450.00,
    currentBet: 0,
    activeChip: 2.5
  });
  
  console.log('✅ Teste automático concluído!');
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ============================================
// TESTE DE STRESS - MUDANÇAS RÁPIDAS
// ============================================
async function testeStress() {
  console.log('⚡ Iniciando teste de stress...');
  
  for (let i = 0; i < 20; i++) {
    const status = i % 2 === 0 ? "FAÇAM SUAS APOSTAS" : "FECHADO";
    const balance = 1000 + (i * 50);
    const currentBet = i % 2 === 0 ? 0 : 50;
    
    await atualizarDashboard({
      gameStatus: status,
      balance: balance,
      currentBet: currentBet,
      activeChip: 2.5
    });
    
    console.log(`Ciclo ${i + 1}/20 - Saldo: R$ ${balance}`);
    await sleep(500);
  }
  
  console.log('✅ Teste de stress concluído!');
}

// ============================================
// INSTRUÇÕES DE USO
// ============================================
console.log(`
╔════════════════════════════════════════════╗
║   🧪 TESTES DO DASHBOARD - ESCUTA BEAT    ║
╚════════════════════════════════════════════╝

📋 Funções disponíveis:

  testeAberto()      - Status ABERTO (verde)
  testeFechado()     - Status FECHADO (vermelho)
  testeAguardando()  - Status AGUARDANDO (amarelo)
  testeVitoria()     - Simula vitória (saldo aumenta)
  testeAposta()      - Simula aposta em andamento
  testeOcultar()     - Oculta o dashboard
  
  testeAutomatico()  - Roda ciclo completo (15s)
  testeStress()      - Teste de stress (20 ciclos)

💡 Exemplo de uso:
  
  testeAberto()      // Executa teste
  testeAutomatico()  // Ciclo completo

🎯 Após executar, abra o popup para ver as mudanças!
`);

