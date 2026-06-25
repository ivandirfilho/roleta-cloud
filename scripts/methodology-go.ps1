#requires -Version 5.1
<#
  methodology-go.ps1 — bootstrap IDEMPOTENTE da metodologia de sprints (Roleta Cloud).
  Uso:  pwsh -File scripts/methodology-go.ps1 [-DryRun]
  Seguro de re-rodar. NÃO mexe em produção. Entrega o scaffold por PR.
  Referência: evolução_24_junho.md §6, §8.
#>
param([switch]$DryRun)
$ErrorActionPreference = 'Continue'
function Step($m){ Write-Host "==> $m" -ForegroundColor Cyan }
$root = (git rev-parse --show-toplevel 2>$null)
if(-not $root){ Write-Error 'Não é um repositório git.'; exit 1 }
Set-Location $root.Trim()

# 1) scaffold nativo presente?
Step 'Verificando scaffold .github/ + .githooks/'
$need = @(
  '.github/copilot-instructions.md','.github/agents/sprint-director.md','.github/agents/sprint-executor.md',
  '.github/skills/sprint-executor/SKILL.md','.github/skills/methodology-go/SKILL.md','.github/skills/sprint-status/SKILL.md',
  '.githooks/pre-push','.githooks/pre-commit'
)
$miss = $need | Where-Object { -not (Test-Path $_) }
if($miss){ Write-Warning ("Faltando: " + ($miss -join ', ')) } else { Write-Host '   scaffold OK' }

# 2) git hooks versionados
Step 'git config core.hooksPath .githooks'
if(-not $DryRun){ git config core.hooksPath .githooks }

# 3) .gitignore graphify-out/graph.*
Step '.gitignore graphify-out/graph.{json,html}'
$gi = if(Test-Path .gitignore){ Get-Content .gitignore -Raw } else { '' }
foreach($l in 'graphify-out/graph.json','graphify-out/graph.html'){
  if($gi -notmatch [regex]::Escape($l)){ if(-not $DryRun){ Add-Content .gitignore $l }; Write-Host "   add: $l" }
}

# 4) GitHub: branch protection + auto-merge (best-effort; falha não é fatal)
Step 'GitHub settings (best-effort)'
$repo = (gh repo view --json nameWithOwner -q .nameWithOwner 2>$null)
if($repo){
  if(-not $DryRun){
    $body = @{
      required_status_checks = @{ strict = $true; contexts = @('ci-ok') }
      enforce_admins = $false
      required_pull_request_reviews = @{ required_approving_review_count = 0 }
      restrictions = $null
    } | ConvertTo-Json -Depth 6
    $body | gh api -X PUT "repos/$repo/branches/main/protection" --input - 2>$null
    if($LASTEXITCODE -eq 0){ Write-Host '   branch protection OK' } else { Write-Warning '   branch protection falhou (precisa admin) — manual' }
    gh api -X PATCH "repos/$repo" -F allow_auto_merge=true 2>$null | Out-Null
    Write-Host '   allow_auto_merge solicitado'
  }
} else { Write-Warning '   gh indisponível — pule GitHub settings' }

# 5) untrack grafo pesado (idempotente) + branch + commit + PR
Step 'untrack graphify-out/graph.* (se tracked)'
if(-not $DryRun){
  git ls-files --error-unmatch graphify-out/graph.json 2>$null | Out-Null
  if($LASTEXITCODE -eq 0){ git rm --cached -q graphify-out/graph.json graphify-out/graph.html 2>$null; Write-Host '   untracked graph.json/html' }
}
Step 'branch spr/methodology-bootstrap + commit + PR'
if(-not $DryRun){
  $br = 'spr/methodology-bootstrap'
  git show-ref --verify --quiet "refs/heads/$br"
  if($LASTEXITCODE -eq 0){ git switch $br | Out-Null } else { git switch -c $br | Out-Null }
  git add .github .githooks scripts sprints .gitignore .gitattributes 2>$null
  Get-ChildItem -File -Filter '*_24_junho.md' | ForEach-Object { git add -- $_.Name }
  git add fluxo_mental_24.md 2>$null
  $msg = "SPR-M: bootstrap da metodologia de sprints (nativo Copilot CLI)`n`nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
  git commit -m $msg
  if($LASTEXITCODE -ne 0){ Write-Warning 'commit falhou (nada novo ou hook bloqueou) — verifique'; }
  git push -u origin $br
  if($LASTEXITCODE -ne 0){ Write-Warning 'push falhou (conflito/permite?) — abortando'; return }
  gh pr create --fill --base main --head $br
  if($LASTEXITCODE -ne 0){ Write-Warning 'PR nao criado (talvez ja exista)'; }
}
Write-Host '==> GO finalizado (cheque avisos acima).' -ForegroundColor Green
