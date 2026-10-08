param([string]$ConfigPath = "")
# SysDash v12 · Windows-agent-installer (LICHTE versie).
# Zet alleen de kernmetingen neer (CPU/RAM/schijf/netwerk/accu/uptime) via Taakplanner.
# Geen temperaturen/updates-telling/hardware-info/actie-laag — zie windows/README.md waarom.
# Draai dit script vanuit deze map (windows/) met: powershell -ExecutionPolicy Bypass -File install-windows.ps1

$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Say($msg)  { Write-Host "`n» $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function WarnMsg($msg) { Write-Host "  [!] $msg" -ForegroundColor Yellow }
function DieMsg($msg)  { Write-Host "  [X] $msg" -ForegroundColor Red; exit 1 }

Write-Host "════════════════════════════════════════════════"
Write-Host " SysDash v12 · Windows-agent-installer (licht)"
Write-Host " map: $Dir"
Write-Host "════════════════════════════════════════════════"

Say "1. Python + psutil"
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { DieMsg "Python niet gevonden. Installeer via https://python.org/downloads (vink 'Add to PATH' aan) en draai dit script opnieuw." }
Ok "python gevonden: $($py.Source)"
python -m pip install --quiet "psutil>=6.1,<8"
if ($LASTEXITCODE -ne 0) { DieMsg "psutil installeren mislukt" }
Ok "psutil geïnstalleerd"

Say "2. Secrets (.env)"
$envPath = Join-Path $Dir ".env"
if ($ConfigPath) { Copy-Item -LiteralPath $ConfigPath -Destination $envPath -Force }
if (-not (Test-Path $envPath)) { DieMsg "Maak op de hub een machineconfig met create-agent.py en geef die op met -ConfigPath. Geen service-key op Windows gebruiken." }
# Restrict secrets to this user; inherited broad access is removed.
$acl = New-Object System.Security.AccessControl.FileSecurity
$acl.SetAccessRuleProtection($true, $false)
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule($identity,"FullControl","Allow")))
$acl.AddAccessRule((New-Object System.Security.AccessControl.FileSystemAccessRule("SYSTEM","FullControl","Allow")))
Set-Acl -LiteralPath $envPath -AclObject $acl
Ok "Machineconfig aanwezig en privé"

Say "3. Test-meting (--dry-run, pusht nog niks)"
python (Join-Path $Dir "agent_windows.py") --dry-run
if ($LASTEXITCODE -ne 0) { DieMsg "test-meting mislukt — check python/psutil hierboven" }
Ok "meting werkt"
python (Join-Path $Dir "agent_windows.py") --once
if ($LASTEXITCODE -ne 0) { DieMsg "Eerste push mislukt; taak is niet geïnstalleerd." }
Ok "Eerste meting ontvangen"

Say "4. Taakplanner-taak registreren (start bij inloggen, herstart zelf bij een crash)"
$taskName = "SysDash-Agent"
$pythonwCommand = Get-Command pythonw -ErrorAction SilentlyContinue
$pythonw = if ($pythonwCommand) { $pythonwCommand.Source } else { $py.Source }  # fallback: gewone python.exe (kort schermpje bij opstarten)
$action  = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$Dir\agent_windows.py`"" -WorkingDirectory $Dir
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -DontStopOnIdleEnd -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -Force -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "SysDash Windows-agent (licht) — pusht metingen naar Supabase" | Out-Null
Start-ScheduledTask -TaskName $taskName
Start-Sleep -Seconds 2
$state = (Get-ScheduledTask -TaskName $taskName).State
if ($state -ne "Running") { DieMsg "Taak niet actief; controleer Taakplanner." }
Ok "taak geregistreerd en actief"

Write-Host ""
Write-Host "════════════════════════════════════════════════"
Write-Host " KLAAR — deze pc meet nu mee. Zie 'm op het dashboard verschijnen"
Write-Host " (kan een paar minuten duren voor de eerste meting binnen is)."
Write-Host " Taak beheren: Taakplanner (taskschd.msc) → 'SysDash-Agent'."
Write-Host "════════════════════════════════════════════════"
