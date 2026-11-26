param([switch]$Disable)
$ErrorActionPreference = "Stop"
$name = "EGX Personal Trading Assistant"
if ($Disable) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
    return
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$launcher = Join-Path $PSScriptRoot "launch.cmd"
$action = New-ScheduledTaskAction -Execute $env:ComSpec -Argument ('/d /s /c ""' + $launcher + '" task"')
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "EGX will start after you sign in to Windows."
