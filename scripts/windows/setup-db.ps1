<#
Create the local PostgreSQL role, databases, schemas and extensions for
TABSIRA, and write the connection URLs into the root .env: what
scripts/setup-db.sh does, for a Windows PostgreSQL (install-postgres.ps1).

  role        tabsira          login role; the password is generated once and
                               kept in .env, never printed. CREATEDB on
                               development and test hosts only.
  databases   tabsira          the application database
              tabsira_test     the API test suite; not in production
              tabsira_template development and test only: an empty copy of the
                               setup, marked as a template, closed to connections
  schemas     app, geodata, vectors   owned by the role, in every database
  search_path app, geodata, vectors, public   set on the role
  extensions  postgis pg_trgm unaccent pgcrypto btree_gin btree_gist
              pg_stat_statements vector timescaledb   in every database,
              WITH SCHEMA public, the way the API migrations expect them

.env keys written (the file is created from .env.example when missing, is
gitignored, and is readable by you only):
  DATABASE_URL, SYNC_DATABASE_URL, TEST_DATABASE_URL

Superuser steps connect as postgres over 127.0.0.1 with the password that
install-postgres.ps1 put in pgpass.conf (PGPASSFILE names another file).
Idempotent. Only the objects named tabsira, tabsira_test, tabsira_template and
the role tabsira are touched.

Environment: PG_PORT (default 5432), ENVIRONMENT (development, test or
production; from the environment, else from .env, else development).

Usage: scripts\windows\setup-db.ps1
#>
. "$PSScriptRoot\lib.ps1"
Use-PgBin

$PgHost = '127.0.0.1'
$DbUser = 'tabsira'
$DbName = 'tabsira'
$TestDbName = 'tabsira_test'
$TemplateDbName = 'tabsira_template'
$Schemas = @('app', 'geodata', 'vectors')
$Extensions = @('postgis', 'pg_trgm', 'unaccent', 'pgcrypto', 'btree_gin', 'btree_gist', 'pg_stat_statements', 'vector', 'timescaledb')

$environment = if ($env:ENVIRONMENT) { $env:ENVIRONMENT } else { Get-EnvValue $EnvFile 'ENVIRONMENT' }
if (-not $environment) { $environment = 'development' }
$environment = $environment.ToLower()
switch ($environment) {
    { $_ -in 'development', 'test' } {
        $databases = @($DbName, $TestDbName, $TemplateDbName)
        $connectable = @($DbName, $TestDbName)
        $roleFlags = 'CREATEDB'
    }
    'production' {
        $databases = @($DbName)
        $connectable = @($DbName)
        $roleFlags = 'NOCREATEDB'
    }
    default { Fail "ENVIRONMENT must be development, test or production (got '$environment')" }
}

if (-not (Test-Command psql)) { Fail 'psql is not installed. Run: scripts\windows\provision-dev.ps1' }
if (-not (Test-PsqlAdmin)) {
    Fail "cannot reach PostgreSQL as postgres on ${PgHost}:$PgPort. Is the service running, and is the superuser password in $PgPassFile (one line: ${PgHost}:${PgPort}:*:postgres:<password>)?"
}

# timescaledb and pg_stat_statements only work when the server preloads them.
$preload = Invoke-Psql -Tuples -Sql 'SHOW shared_preload_libraries'
foreach ($lib in 'timescaledb', 'pg_stat_statements') {
    if ((",$($preload -replace '[ ''"]', '')," ) -notlike "*,$lib,*") {
        Fail "$lib is not in shared_preload_libraries ('$preload'). Run: scripts\windows\install-postgres.ps1"
    }
}

# --- Password: the one in .env, else a new one -------------------------------
if (-not (Test-Path -LiteralPath $EnvFile)) {
    $example = Join-Path $RepoRoot '.env.example'
    if (Test-Path -LiteralPath $example) {
        Copy-Item -LiteralPath $example -Destination $EnvFile
        Write-Log 'Created .env from .env.example'
    } else {
        Write-Utf8File -Path $EnvFile -Content ''
        Write-Log 'Created an empty .env'
    }
}
Protect-File $EnvFile

$dbPassword = ''
$url = Get-EnvValue $EnvFile 'DATABASE_URL'
if ($url -match '^[^:]+://[^:@/]+:([^@]*)@') { $dbPassword = $Matches[1] }
# Keep an existing password only when it is long and URL-safe; a placeholder, a
# short one or anything that is not a URL with a password is replaced.
if ($dbPassword -notmatch '^[A-Za-z0-9]{24,}$') {
    $dbPassword = New-RandomHex 24
    Write-Log "Generated a new password for role $DbUser"
}

# --- Role ------------------------------------------------------------------
Write-Log "Ensuring role $DbUser"
[void](Invoke-Psql -InputSql @"
DO `$`$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$DbUser') THEN
    CREATE ROLE $DbUser LOGIN;
  END IF;
END
`$`$;
"@)
# The password goes in through stdin: never on a command line.
[void](Invoke-Psql -InputSql "ALTER ROLE $DbUser WITH LOGIN PASSWORD '$dbPassword';")
[void](Invoke-Psql -Sql "ALTER ROLE $DbUser SET search_path = app, geodata, vectors, public;")
# CREATEDB lets pytest-xdist copy a template database per worker; it is a
# development convenience that a production role must not have.
[void](Invoke-Psql -Sql "ALTER ROLE $DbUser $roleFlags;")
Write-Log "Role ${DbUser}: $roleFlags ($environment)"

# --- Databases -------------------------------------------------------------
foreach ($db in $databases) {
    if ((Invoke-Psql -Tuples -Sql "SELECT 1 FROM pg_database WHERE datname = '$db'") -ne '1') {
        Write-Log "Creating database $db"
        [void](Invoke-Psql -Sql "CREATE DATABASE $db OWNER $DbUser ENCODING 'UTF8' TEMPLATE template0;")
    } else {
        Write-Ok "Database $db exists"
        [void](Invoke-Psql -Sql "ALTER DATABASE $db OWNER TO $DbUser;")
    }

    # The template is closed to connections between runs; open it to work on it.
    if ($db -eq $TemplateDbName) {
        [void](Invoke-Psql -Sql "ALTER DATABASE $db WITH ALLOW_CONNECTIONS true;")
    }

    foreach ($schema in $Schemas) {
        [void](Invoke-Psql -Database $db -Sql "CREATE SCHEMA IF NOT EXISTS $schema AUTHORIZATION $DbUser;")
        [void](Invoke-Psql -Database $db -Sql "ALTER SCHEMA $schema OWNER TO $DbUser;")
    }

    # Extensions are created here with superuser rights; a migration only ever
    # finds them already present and never silently skips a missing one.
    foreach ($ext in $Extensions) {
        [void](Invoke-Psql -Database $db -Sql "CREATE EXTENSION IF NOT EXISTS $ext SCHEMA public;")
        $installed = Invoke-Psql -Database $db -Tuples -Sql "SELECT extversion FROM pg_extension WHERE extname = '$ext'"
        $available = Invoke-Psql -Database $db -Tuples -Sql "SELECT default_version FROM pg_available_extensions WHERE name = '$ext'"
        if ($installed -ne $available) {
            Write-Log "${db}: updating $ext $installed -> $available"
            try { [void](Invoke-Psql -Database $db -Sql "ALTER EXTENSION $ext UPDATE;") }
            catch { Write-Warn "${db}: $ext could not be updated from $installed to ${available}: $_" }
        }
    }
    if ($db -eq $TemplateDbName) {
        [void](Invoke-Psql -Sql "ALTER DATABASE $db WITH IS_TEMPLATE true ALLOW_CONNECTIONS false;")
        # The TimescaleDB scheduler may still hold a session opened before the
        # switch, and a template with any session cannot be copied.
        [void](Invoke-Psql -Tuples -Sql "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid()")
    }
    Write-Ok "${db}: schemas $($Schemas -join ' ') and extensions ready"
}

# --- .env ------------------------------------------------------------------
Set-EnvValue $EnvFile 'DATABASE_URL' "postgresql+asyncpg://${DbUser}:${dbPassword}@${PgHost}:${PgPort}/$DbName"
Set-EnvValue $EnvFile 'SYNC_DATABASE_URL' "postgresql+psycopg://${DbUser}:${dbPassword}@${PgHost}:${PgPort}/$DbName"
if ($environment -ne 'production') {
    Set-EnvValue $EnvFile 'TEST_DATABASE_URL' "postgresql+asyncpg://${DbUser}:${dbPassword}@${PgHost}:${PgPort}/$TestDbName"
}
Write-Ok 'Connection URLs are in .env'

# --- Verify as the application role, the way the app connects --------------
foreach ($db in $connectable) {
    try {
        $path = Invoke-Psql -User $DbUser -Database $db -Password $dbPassword -Tuples -Sql 'SHOW search_path'
    } catch {
        Fail "role $DbUser cannot connect to $db over ${PgHost}:${PgPort}: $("$_" -replace [regex]::Escape($dbPassword), '***')"
    }
    if ($path -ne 'app, geodata, vectors, public') { Fail "search_path of $DbUser on $db is '$path'" }
}
foreach ($db in $connectable) {
    Write-Log "$db extensions: $(Invoke-Psql -Database $db -Tuples -Sql "SELECT string_agg(extname || ' ' || extversion, ', ' ORDER BY extname) FROM pg_extension WHERE extname <> 'plpgsql'")"
}
Write-Ok "Database setup complete: $($databases -join ' '), role $DbUser, search_path app, geodata, vectors, public"
exit 0
