param(
  [int]$Port = 8000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "env.ps1")

python (Join-Path $PSScriptRoot "local_server.py") --port $Port
