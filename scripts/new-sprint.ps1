#requires -Version 5.1
<#
  new-sprint.ps1 — Diretor: PUBLICA um brief ja escrito num branch spr/<Id>,
  para o Executor (sessao nova/worktree) ou /delegate (nuvem) pegarem direto.
  Uso: pwsh -File scripts/new-sprint.ps1 -Id SPR-X1 [-DryRun]
  Pre-requisito: escreva sprints/<Id>.md primeiro (o Diretor preenche o brief).
  Nao toca o working tree do Diretor (usa worktree temporario). Nao mescla.
#>
param([Parameter(Mandatory)][string]$Id, [switch]$DryRun)
$ErrorActionPreference = 'Continue'
$root = (git rev-parse --show-toplevel).Trim(); Set-Location $root
if($Id -notmatch '^SPR-[A-Za-z0-9._-]+$'){ Write-Error "Id invalido (ex.: SPR-X1)"; exit 1 }
$brief = "sprints/$Id.md"
if(-not (Test-Path $brief)){ Write-Error "Escreva $brief primeiro (o Diretor preenche o brief a partir de sprints/_BRIEF_TEMPLATE.md)."; exit 1 }
$branch = "spr/$Id"
git fetch -q origin main
if($DryRun){ Write-Host "[DryRun] publicaria $brief no branch $branch (a partir de origin/main)"; exit 0 }

$tmp = Join-Path $env:TEMP ("rc-$Id-" + (Get-Random))
git worktree add -q -b $branch $tmp origin/main
if($LASTEXITCODE -ne 0){ Write-Error "worktree add falhou (branch $branch ja existe? use outro Id ou 'git push origin --delete $branch')"; exit 1 }
try {
  Copy-Item $brief (Join-Path $tmp $brief) -Force
  git -C $tmp add -- $brief
  $msg = "$Id`: brief (Diretor)`n`nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
  git -C $tmp commit -q -m $msg
  git -C $tmp push -q -u origin $branch
  if($LASTEXITCODE -ne 0){ Write-Warning "push falhou (branch ja existe?) — verifique"; }
  else {
    Write-Host "==> Brief publicado no branch $branch" -ForegroundColor Green
    Write-Host "   Executar em sessao NOVA (local):"
    Write-Host "     git worktree add ..\rc-$Id $branch; cd ..\rc-$Id; copilot --agent sprint-executor `"Execute $brief`""
    Write-Host "   OU delegar p/ a nuvem: /delegate (no branch $branch)."
  }
} finally {
  git worktree remove --force $tmp 2>$null
}
