#requires -Version 5.1
<#  sprint-status.ps1 — painel de 1 tela: BOARD × PRs × CI.  Uso: pwsh -File scripts/sprint-status.ps1  #>
$ErrorActionPreference = 'SilentlyContinue'
$root = (git rev-parse --show-toplevel 2>$null); if($root){ Set-Location $root.Trim() }

Write-Host '=== BOARD (sprints/BOARD.md) ===' -ForegroundColor Cyan
if(Test-Path sprints/BOARD.md){
  Select-String -Path sprints/BOARD.md -Pattern '^\|\s*SPR-' | ForEach-Object { $_.Line }
} else { Write-Host 'sem sprints/BOARD.md' }

Write-Host "`n=== PRs abertos (gh) ===" -ForegroundColor Cyan
$json = gh pr list --state open --json number,title,headRefName,statusCheckRollup 2>$null
if($LASTEXITCODE -eq 0 -and $json){
  ($json | ConvertFrom-Json) | ForEach-Object {
    $ci = (($_.statusCheckRollup | ForEach-Object { $_.conclusion } | Where-Object { $_ }) -join ',')
    if(-not $ci){ $ci = 'pending' }
    "  #{0,-4} {1,-50} [{2}] CI={3}" -f $_.number, ($_.title.Substring(0,[Math]::Min(50,$_.title.Length))), $_.headRefName, $ci
  }
} else { Write-Host '  gh indisponível ou sem PRs abertos' }

Write-Host "`nMerge-ready = PR com CI verde (success). Flag-ready = sprint MERGED esperando ligar a flag na docker-compose.yml." -ForegroundColor DarkGray
