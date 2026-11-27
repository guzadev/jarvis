param([switch]$Remove)
$ErrorActionPreference = 'Stop'
$startupFolder = [Environment]::GetFolderPath('Startup')
$shortcutPath = Join-Path $startupFolder 'Jarvis - activacion por voz.lnk'
if ($Remove) {
    if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath }
    Write-Host 'Inicio automatico de Jarvis desactivado.'
    exit
}
$launcherPath = Join-Path $PSScriptRoot 'jarvis.ps1'
if (-not (Test-Path -LiteralPath $launcherPath)) { throw 'No encuentro jarvis.ps1.' }
$shortcutShell = New-Object -ComObject WScript.Shell
$shortcut = $shortcutShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$shortcut.Arguments = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $launcherPath + '" -Background'
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.Description = 'Inicia Jarvis al entrar a Windows; escucha local de la palabra Jarvis.'
$shortcut.WindowStyle = 7
$shortcut.Save()
Write-Host 'Jarvis iniciara en segundo plano al entrar a tu sesion de Windows.'
