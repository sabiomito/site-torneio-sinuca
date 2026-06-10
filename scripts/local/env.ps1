$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = "sa-east-1"
$env:AWS_REGION = "sa-east-1"

if (-not $env:TABLE_NAME) { $env:TABLE_NAME = "torneio-sinuca-local" }
if (-not $env:MEDIA_BUCKET) { $env:MEDIA_BUCKET = "torneio-sinuca-local-media" }
if (-not $env:ADMIN_PASSWORD) { $env:ADMIN_PASSWORD = "1234" }
if (-not $env:SECRET_KEY) { $env:SECRET_KEY = "local-dev-secret" }
if (-not $env:SESSION_SECONDS) { $env:SESSION_SECONDS = "43200" }

$env:DYNAMODB_ENDPOINT_URL = "http://localhost:4566"
$env:S3_ENDPOINT_URL = "http://localhost:4566"
$env:DATABASE_RESET_VERSION = ""
$env:LOCAL_DEV = "1"

$backendPath = Join-Path $ProjectRoot "backend"
if ($env:PYTHONPATH) {
  $env:PYTHONPATH = "$backendPath;$ProjectRoot;$env:PYTHONPATH"
} else {
  $env:PYTHONPATH = "$backendPath;$ProjectRoot"
}
