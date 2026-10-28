<#
Runs one vault server and restarts it when it stops. Started at logon by the task that
install-tasks.ps1 registers; can also be run by hand to test.

Settings live outside the repo and outside the vault, in
%USERPROFILE%\.vault-mcp\<Name>\server.json. Not under AppData: an app installed as a
Windows package (the Claude desktop app is one) has its AppData writes redirected to a
private copy, so a file written from there would never reach this script.

  {
    "vault_path": "C:\\Obsidian\\Mijn Vault",
    "port": 8421,
    "hostname": "a.jouwdomein.com",
    "cf_access_team_domain": "<team>.cloudflareaccess.com",
    "cf_access_aud": "<AUD tag of the Access application>"
  }

The server runs in Cloudflare Access mode only: without both Access settings this script
refuses to start it. Every server gets its own state folder, so a login for one vault
never works on the other.
#>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9-]+$')][string]$Name
)

$ErrorActionPreference = 'Stop'

# Any error this script does not handle lands in its log instead of vanishing with the
# hidden window.
trap {
    $fallback = Join-Path $env:USERPROFILE ".vault-mcp\$Name\start-vault-error.log"
    [IO.File]::AppendAllText($fallback, ('{0:yyyy-MM-dd HH:mm:ss} {1}{2}{3}{2}' -f (Get-Date), $_, [Environment]::NewLine, $_.ScriptStackTrace))
    exit 1
}

$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$exe = Join-Path $repo '.venv\Scripts\vault-mcp.exe'
$state = Join-Path $env:USERPROFILE ".vault-mcp\$Name"
$logs = Join-Path $state 'logs'
$configPath = Join-Path $state 'server.json'
New-Item -ItemType Directory -Force $logs | Out-Null

function Write-Log([string]$message) {
    $line = '{0:yyyy-MM-dd HH:mm:ss} {1}' -f (Get-Date), $message
    Add-Content -Encoding utf8 -Path (Join-Path $logs 'start-vault.log') -Value $line
}

try {
    $config = Get-Content -Raw -Encoding utf8 $configPath | ConvertFrom-Json
    foreach ($key in 'vault_path', 'port', 'hostname', 'cf_access_team_domain', 'cf_access_aud') {
        if (-not $config.$key) { throw "server.json mist '$key'" }
    }
    if (-not (Test-Path -LiteralPath $config.vault_path -PathType Container)) {
        throw "vault niet gevonden: $($config.vault_path)"
    }
    if (-not (Test-Path -LiteralPath $exe)) { throw "server niet geinstalleerd: $exe" }
} catch {
    Write-Log "niet gestart: $($_.Exception.Message)"
    exit 1
}

# Clear everything this fork must not run with, then set what it needs.
foreach ($var in 'VAULT_MCP_TOKEN', 'VAULT_OAUTH_PASSWORD', 'VAULT_OAUTH_CLIENT_SECRET',
                 'VAULT_UPLOAD_URL_SECRET', 'VAULT_DOWNLOAD_URL_SECRET', 'VAULT_SEMANTIC_SEARCH',
                 'VAULT_MCP_HEARTBEAT_URL', 'VAULT_EXTRA_BINARY_MEDIA_TYPES_JSON') {
    Remove-Item -ErrorAction SilentlyContinue "Env:$var"
}
$env:VAULT_PATH = $config.vault_path
$env:VAULT_MCP_HOST = '127.0.0.1'
$env:VAULT_MCP_PORT = [string]$config.port
$env:VAULT_MCP_PUBLIC_URL = "https://$($config.hostname)"
$env:VAULT_MCP_ALLOWED_HOSTS = $config.hostname
$env:VAULT_MCP_FORWARDED_ALLOW_IPS = '127.0.0.1'
$env:VAULT_MCP_CF_ACCESS_TEAM_DOMAIN = $config.cf_access_team_domain
$env:VAULT_MCP_CF_ACCESS_AUD = $config.cf_access_aud
$env:OAUTH_CLIENTS_PATH = Join-Path $state 'oauth\oauth_clients.json'
$env:VAULT_AUDIT_LOG_PATH = Join-Path $state 'audit.jsonl'
$env:PYTHONUTF8 = '1'

# Never run with the vault as working folder.
Set-Location $repo

# Ending the task stops this script, not the server it started. A server of ours still
# holding the port is stopped first, so the new one can bind it.
function Stop-StrayServer {
    $listeners = Get-NetTCPConnection -LocalPort $config.port -State Listen -ErrorAction SilentlyContinue
    foreach ($owner in @($listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$owner"
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)" -ErrorAction SilentlyContinue
        if ("$($process.CommandLine) $($parent.CommandLine)" -match 'vault-mcp') {
            Write-Log "achtergebleven server op poort $($config.port) gestopt (pid $owner)"
            if ($parent -and $parent.CommandLine -match 'vault-mcp') { Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
        }
    }
}

$out = Join-Path $logs 'server.out.log'
$err = Join-Path $logs 'server.err.log'
$delay = 10
while ($true) {
    Stop-StrayServer
    Start-Sleep -Seconds 1
    foreach ($log in $out, $err) {
        if (Test-Path $log) { Move-Item -Force $log "$log.prev" -ErrorAction SilentlyContinue }
    }
    Write-Log "start op poort $($config.port) voor $($config.hostname)"
    $started = Get-Date
    $process = Start-Process -FilePath $exe -NoNewWindow -PassThru -Wait `
        -RedirectStandardOutput $out -RedirectStandardError $err
    Write-Log "gestopt met code $($process.ExitCode)"
    # A server that ran a while gets a quick restart; one that keeps failing backs off.
    if (((Get-Date) - $started).TotalMinutes -gt 5) { $delay = 10 } else { $delay = [Math]::Min($delay * 2, 300) }
    Start-Sleep -Seconds $delay
}
