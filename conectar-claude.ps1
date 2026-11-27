param()
$ErrorActionPreference = 'Stop'
$claudeExe = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
if (-not (Test-Path -LiteralPath $claudeExe)) {
    $found = Get-Command claude.exe -ErrorAction SilentlyContinue
    if ($found) { $claudeExe = $found.Source }
    else {
        Write-Host 'Primero instalá Claude Code desde su sitio oficial.'
        Write-Host 'Abrí PowerShell y ejecutá: irm https://claude.ai/install.ps1 | iex'
        Write-Host 'Guía: https://github.com/guzadev/jarvis/blob/main/docs/CONECTAR-CLAUDE.md'
        Read-Host 'Presioná Enter para cerrar'
        exit 1
    }
}
$authFolder = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Jarvis\ClaudeLogin'
New-Item -ItemType Directory -Path $authFolder -Force | Out-Null
Set-Location -LiteralPath $authFolder
Write-Host 'CONECTAR CLAUDE CODE CON JARVIS'
Write-Host 'Iniciá sesión en la página oficial que se abre y autorizá Claude Code.'
Write-Host 'Si la terminal pide un código, pegalo acá. No lo publiques ni lo compartas.'
& $claudeExe auth login --claudeai
if ($LASTEXITCODE -ne 0) { throw 'El inicio de sesión no se completó.' }
$state = & $claudeExe auth status --json | ConvertFrom-Json
if ($state.loggedIn) { Write-Host 'Conectado. En Jarvis → Misiones elegí Claude Code y guardá.' }
else { Write-Host 'La conexión no se completó. Revisá el inicio de sesión oficial.' }
Read-Host 'Presioná Enter para cerrar'
