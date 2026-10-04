<#
Run the database migrations: the geodata chain, the app chain, then the
vectors chain. What `make migrate` (scripts/migrate.sh) does, from PowerShell.

Usage: scripts\windows\migrate.ps1 [-Message <text>]
  no message   upgrade the three chains to head
  -Message     first autogenerate an app-chain revision with that message

Reads DATABASE_URL from the root .env (CI injects it instead).
#>
param([string]$Message)
. "$PSScriptRoot\lib.ps1"
Update-Path
Set-PythonEnvironment
Use-PgBin
Import-DotEnv

if (-not $env:DATABASE_URL) { Fail 'DATABASE_URL is not set. Run scripts\windows\setup-db.ps1, which writes it into the root .env.' }
if (-not (Test-Command uv)) { Fail 'uv is not installed. See https://docs.astral.sh/uv/' }
$apiDir = Join-Path $RepoRoot 'apps\api'

# psql does not understand SQLAlchemy's driver suffix.
$psqlUrl = if ($env:SYNC_DATABASE_URL) { $env:SYNC_DATABASE_URL } else { $env:DATABASE_URL }
$psqlUrl = $psqlUrl -replace '\+asyncpg', '' -replace '\+psycopg', ''

# The three schemas must exist before Alembic runs: each chain keeps its version
# table in its own schema. A schema that exists is left alone.
if (Test-Command psql) {
    Write-Log 'Ensuring the app, geodata and vectors schemas exist...'
    foreach ($schema in 'app', 'geodata', 'vectors') {
        $exists = (Invoke-Capture 'psql' @($psqlUrl, '-X', '-tA', '-c', "SELECT 1 FROM pg_namespace WHERE nspname = '$schema'")).Output
        if ($exists -ne '1') {
            Invoke-Native 'psql' @($psqlUrl, '-X', '-q', '-v', 'ON_ERROR_STOP=1', '-c', "CREATE SCHEMA $schema")
        }
    }
} else {
    Write-Warn 'psql not found; assuming the app, geodata and vectors schemas already exist'
}

if ($Message) {
    Write-Log "Creating a new app migration: $Message"
    Invoke-Native 'uv' @('run', 'alembic', 'revision', '--autogenerate', '-m', $Message) -WorkingDirectory $apiDir
}

Write-Log 'Running the geodata chain...'
Invoke-Native 'uv' @('run', 'alembic', '-c', 'alembic_geodata/alembic.ini', 'upgrade', 'head') -WorkingDirectory $apiDir
Write-Log 'Running the app chain...'
Invoke-Native 'uv' @('run', 'alembic', 'upgrade', 'head') -WorkingDirectory $apiDir
Write-Log 'Running the vectors chain...'
Invoke-Native 'uv' @('run', 'alembic', '-c', 'alembic_vectors/alembic.ini', 'upgrade', 'head') -WorkingDirectory $apiDir
Write-Ok 'Migrations completed'
exit 0
