# setup-windows-scheduler.ps1
# Enregistre 3 tâches Windows qui réveillent le PC et exécutent les jobs ChannelOS.
# Remplace le cron WSL2 (fuseau correct, réveil depuis veille, relance après PC éteint).
#
# Prérequis : exécuter depuis PowerShell en administrateur.
# Usage     : powershell -ExecutionPolicy Bypass -File setup-windows-scheduler.ps1
#
# Heures CEST (UTC+2, heure locale Windows — DST géré automatiquement) :
#   13:00 — collect  (≡ 11:00 UTC)
#   14:00 — produce  (≡ 12:00 UTC)
#   18:00 — produce  (≡ 16:00 UTC)

$WSL      = "C:\Windows\System32\wsl.exe"
$User     = "mfayech"
$Scripts  = "/home/mfayech/Github/channelos.ia/scripts"
$Folder   = "ChannelOS"

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

function Register-ChannelOSTask {
    param($Name, $Script, $Hour, $Minute)

    $action  = New-ScheduledTaskAction `
        -Execute $WSL `
        -Argument "-u $User bash $Scripts/$Script"

    $trigger = New-ScheduledTaskTrigger -Daily -At ("{0:D2}:{1:D2}" -f $Hour, $Minute)

    Register-ScheduledTask `
        -TaskPath "\$Folder\" `
        -TaskName  $Name `
        -Action    $action `
        -Trigger   $trigger `
        -Settings  $settings `
        -RunLevel  Highest `
        -Force | Out-Null

    Write-Host "OK  \$Folder\$Name  →  $Script  @ $($trigger.StartBoundary)"
}

Register-ChannelOSTask "collect"    "wts-collect.sh"  13 0
Register-ChannelOSTask "produce-14" "wts-produce.sh"  14 0
Register-ChannelOSTask "produce-18" "wts-produce.sh"  18 0

Write-Host ""
Write-Host "3 tâches enregistrées. Vérifier dans Task Scheduler : \ChannelOS\"
Write-Host "Option 'Wake the computer' = activée via -WakeToRun."
Write-Host ""
Write-Host "Prochaine étape : désactiver le cron WSL2 (éviter les doubles runs) :"
Write-Host '  wsl -u mfayech crontab -r'
