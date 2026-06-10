param(
  [switch]$Yes
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
. (Join-Path $PSScriptRoot "env.ps1")

if (-not $Yes) {
  $answer = Read-Host "Isto apaga somente o DynamoDB/S3 locais. Digite LOCAL para continuar"
  if ($answer -ne "LOCAL") {
    Write-Host "Reset cancelado."
    exit 1
  }
}

Push-Location $ProjectRoot
try {
  try {
    docker compose up -d localstack
  } catch {
    Write-Host ""
    Write-Host "Falha ao iniciar o LocalStack. Execute primeiro .\scripts\local\init.ps1 e siga o diagnostico exibido." -ForegroundColor Red
    throw
  }
  python (Join-Path $PSScriptRoot "reset_local.py")
  Write-Host ""
  Write-Host "Banco e midias locais reiniciados."
} finally {
  Pop-Location
}
