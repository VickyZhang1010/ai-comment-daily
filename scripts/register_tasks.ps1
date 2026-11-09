# Register scheduled tasks for ai-comment-daily (Windows 11)
# Run:  powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1
# Remove: powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Uninstall

param([switch]$Uninstall)

$ErrorActionPreference = "Stop"
$Root = "D:\WorkBuddy\2026-11-09-21-03-07\ai-comment-daily"
$Py = Join-Path $Root ".venv\Scripts\pythonw.exe"

if ($Uninstall) {
    Get-ScheduledTask | Where-Object { $_.TaskName -like "AICmt-*" } | ForEach-Object {
        Unregister-ScheduledTask -TaskName $_.TaskName -Confirm:$false
        Write-Host "removed: $($_.TaskName)"
    }
    exit 0
}

if (-not (Test-Path $Py)) { throw "pythonw.exe not found: $Py" }

function Install-AppTask {
    param([string]$Name, [string]$ArgLine, $Trigger, [string]$Desc)
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
    $Action = New-ScheduledTaskAction -Execute $Py -Argument $ArgLine -WorkingDirectory $Root
    $Set = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger `
        -Settings $Set -Description $Desc | Out-Null
    Write-Host "installed: $Name"
}

# 08:30 collect + build + deploy (machine on)
Install-AppTask -Name "AICmt-DailyBuild" -ArgLine "run.py morning-build" `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "08:30") `
    -Desc "Collect official-media essays and build the daily edition"

# 09:00 push digest (machine on)
Install-AppTask -Name "AICmt-DailyPush" -ArgLine "run.py morning-push" `
    -Trigger (New-ScheduledTaskTrigger -Daily -At "09:00") `
    -Desc "Push the daily digest to WeCom at 09:00"

# On logon: catch up if today is not pushed yet (idempotent)
Install-AppTask -Name "AICmt-Catchup" -ArgLine "run.py catchup" `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn) `
    -Desc "Idempotent catch-up on logon when the daily push was missed"

Write-Host ""
Get-ScheduledTask | Where-Object { $_.TaskName -like "AICmt-*" } |
    Format-Table TaskName, State -AutoSize
