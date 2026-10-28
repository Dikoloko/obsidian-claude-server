<#
Registers the logon tasks for the current user: one per vault server, and one for the
tunnel. No administrator rights needed. Run again to update; -Remove takes them away.

  .\install-tasks.ps1 -Names a            # one vault
  .\install-tasks.ps1 -Names a,b          # both vaults
  .\install-tasks.ps1 -Names a,b -Remove
#>
param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[a-z0-9-]+$')][string[]]$Names,
    [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$user = "$env:USERDOMAIN\$env:USERNAME"

function Register-LogonTask([string]$taskName, [string]$script, [string]$arguments) {
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" $arguments"
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $taskName -TaskPath '\vault-mcp\' -Action $action `
        -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
    Write-Host "Taak klaar: $taskName"
}

$tasks = @($Names | ForEach-Object { "vault $_" }) + 'tunnel'
if ($Remove) {
    foreach ($task in $tasks) {
        Unregister-ScheduledTask -TaskName $task -TaskPath '\vault-mcp\' -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Taak weg: $task"
    }
    return
}

foreach ($name in $Names) {
    Register-LogonTask "vault $name" (Join-Path $PSScriptRoot 'start-vault.ps1') "-Name $name"
}
Register-LogonTask 'tunnel' (Join-Path $PSScriptRoot 'start-tunnel.ps1') ''
