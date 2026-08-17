# scripts/agent-kickoff.ps1 — orientação de sessão em ~10s (READ-ONLY)
# TODO agente roda isto ANTES da primeira ação (ritual de abertura dos invioláveis).
# Não altera nada: só coleta o estado que o agente PRECISA saber para não agir cego.

$ErrorActionPreference = "SilentlyContinue"

Write-Host "===== KICKOFF · $(Get-Date -Format 'yyyy-MM-dd HH:mm') ====="

Write-Host "`n== 1. main-red (prioridade máxima se houver) =="
gh issue list --label main-red --state open --json number,title --jq '.[] | "#\(.number) \(.title)"'
if (-not $?) { Write-Host "(gh indisponível — cheque manualmente)" }

Write-Host "`n== 2. PRs abertos (lock check anti-silo) =="
gh pr list --state open --json number,title,headRefName --jq '.[] | "#\(.number) [\(.headRefName)] \(.title)"'

Write-Host "`n== 3. Últimos merges na main =="
git log origin/main --oneline -5

Write-Host "`n== 4. Produção (ler por endpoint, NUNCA ssh) =="
foreach ($u in "https://roleta.xma-ia.com/health", "https://roleta.xma-ia.com/") {
    try {
        $r = Invoke-WebRequest -Uri $u -TimeoutSec 6 -UseBasicParsing
        Write-Host "$u -> $($r.StatusCode)"
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        Write-Host "$u -> $(if ($code) { $code } else { 'sem resposta' })"
    }
}
try {
    $azure = Invoke-WebRequest -Uri "https://20-226-77-194.sslip.io/healthz" -TimeoutSec 3 -UseBasicParsing
    Write-Host "Azure standby https://20-226-77-194.sslip.io/healthz -> $($azure.StatusCode)"
} catch {
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host "Azure standby https://20-226-77-194.sslip.io/healthz -> $(if ($code) { $code } else { 'sem resposta' })"
}
Write-Host "(health 404/ws 502 = incidente conhecido? cheque issues abertas antes de re-diagnosticar)"

Write-Host "`n== 5. Grafo local (graphify) — auto-refresh (build ~5s; sempre fresco) =="
if (Get-Command graphify -ErrorAction SilentlyContinue) {
    $gt = Measure-Command { graphify update . 2>&1 | Out-Null }
    Write-Host "grafo atualizado em $([math]::Round($gt.TotalSeconds))s -> graphify-out/graph.json (NUNCA commitar)"
} else {
    Write-Host "graphify ausente nesta maquina — siga sem grafo (grep/view) e registre no log da sessao"
}

Write-Host "`n== 6. Board (tail) =="
if (Test-Path "sprints\BOARD.md") { Get-Content "sprints\BOARD.md" -Tail 12 }

Write-Host "`n===== FIM DO KICKOFF — agora aja. Mapa completo: AGENTS.md ====="
