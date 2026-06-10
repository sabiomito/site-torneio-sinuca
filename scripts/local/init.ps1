param(
  [switch]$SkipDocker
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
. (Join-Path $PSScriptRoot "env.ps1")

Push-Location $ProjectRoot
try {
  if (-not $SkipDocker) {
    try {
      docker compose up -d localstack
    } catch {
      Write-Host ""
      Write-Host "O Docker Desktop nao conseguiu iniciar o LocalStack." -ForegroundColor Red
      Write-Host "Se o erro mencionar overlay2 ou symbolic links:" -ForegroundColor Yellow
      Write-Host "1. Feche o Docker Desktop."
      Write-Host "2. Abra PowerShell como administrador e execute: wsl --shutdown"
      Write-Host "3. Execute: wsl --update"
      Write-Host "4. Reinicie o Windows e abra o Docker Desktop."
      Write-Host "5. Rode novamente: .\scripts\local\init.ps1"
      Write-Host ""
      Write-Host "Se persistir, use Docker Desktop > Troubleshoot > Clean / Purge data."
      Write-Host "Atencao: essa ultima opcao apaga containers, imagens e volumes locais do Docker."
      throw
    }
  }
  python (Join-Path $PSScriptRoot "init_local.py")
  Write-Host ""
  Write-Host "Ambiente local pronto."
  Write-Host "Use: .\scripts\local\dev.ps1"
} finally {
  Pop-Location
}
