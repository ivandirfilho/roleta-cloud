<#
  rebuild_super_graph.ps1 — Reconstroi o super-grafo da infraestrutura Roleta.

  Uso:
    .\rebuild_super_graph.ps1            # re-funde os grafos existentes (rapido, sem LLM)
    .\rebuild_super_graph.ps1 -Update    # antes, roda 'graphify update' em cada projeto

  Pipeline: [update opcional] -> merge-graphs -> inject_backbone.py -> cluster-only
#>
param([switch]$Update)

$ErrorActionPreference = "Stop"
$exe  = "C:\Users\Windows\.local\bin\graphify.exe"
$base = "C:\Users\Windows\Desktop\Roleta Cloud\super_graph"
$out  = "$base\graphify-out\graph.json"

# Projetos-fonte (pasta raiz de cada um, que contem graphify-out\graph.json)
$projects = @(
  "C:\Users\Windows\Desktop\Roleta Cloud",
  "C:\Users\Windows\Desktop\Roleta Cloud\server_snapshot",
  "C:\Users\Windows\Desktop\android",
  "C:\Users\Windows\Desktop\Extrator beat novo\Roleta Cloud",
  "C:\Users\Windows\Desktop\Genesis azure",
  "C:\Users\Windows\Desktop\Testando Grafiphy"
)

if ($Update) {
  Write-Host "== Atualizando grafos-fonte (graphify update, sem LLM) =="
  foreach ($p in $projects) {
    if (Test-Path "$p\graphify-out\graph.json") {
      Write-Host "  update: $p"
      & $exe update "$p" 2>&1 | Out-Null
    }
  }
}

Write-Host "== 1/3 merge-graphs (local + servidor Debian primeiro) =="
$graphs = $projects | ForEach-Object { "$_\graphify-out\graph.json" } | Where-Object { Test-Path $_ }
& $exe merge-graphs @graphs --out $out

Write-Host "== 2/3 injetando camada backbone de infraestrutura =="
python "$base\inject_backbone.py"

Write-Host "== 3/3 cluster-only (comunidades + HTML + report) =="
& $exe cluster-only $base

Write-Host ""
Write-Host "OK -> $out"
Write-Host "Visualizacao: $base\graphify-out\graph.html"
Write-Host "Lembrete: o MCP graphify ja aponta para este graph.json (reinicie o Copilot CLI para recarregar)."
