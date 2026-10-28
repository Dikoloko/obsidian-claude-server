<#
Runs the Cloudflare tunnel and restarts it when it stops. Started at logon by the task
that install-tasks.ps1 registers. The tunnel settings are in
%USERPROFILE%\.cloudflared\config.yml (see cloudflared-config.example.yml).
#>
$ErrorActionPreference = 'Stop'

$cloudflared = (Get-Command cloudflared.exe).Source
$config = Join-Path $env:USERPROFILE '.cloudflared\config.yml'
$logs = Join-Path $env:USERPROFILE '.vault-mcp\tunnel'
New-Item -ItemType Directory -Force $logs | Out-Null

$delay = 10
while ($true) {
    $started = Get-Date
    Start-Process -FilePath $cloudflared -NoNewWindow -Wait `
        -ArgumentList @('tunnel', '--config', "`"$config`"", '--logfile', "`"$(Join-Path $logs 'cloudflared.log')`"", 'run')
    if (((Get-Date) - $started).TotalMinutes -gt 5) { $delay = 10 } else { $delay = [Math]::Min($delay * 2, 300) }
    Start-Sleep -Seconds $delay
}
