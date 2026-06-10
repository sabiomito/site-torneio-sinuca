param(
  [string]$BaseUrl = "http://localhost:8000",
  [switch]$Headed,
  [switch]$Full,
  [switch]$TelaoOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "env.ps1")

$env:APP_BASE_URL = $BaseUrl
$env:SELENIUM_HEADLESS = $(if ($Headed) { "0" } else { "1" })

if ($TelaoOnly) {
  python -m pytest tests/e2e -m telao_cycle -s
} elseif ($Full) {
  python -m pytest tests/e2e -m full -s
} else {
  python -m pytest tests/e2e -m "not full and not telao_cycle"
}
