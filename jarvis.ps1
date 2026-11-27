param([switch]$Stop, [switch]$Online, [switch]$Background)
$ErrorActionPreference = 'Stop'
$jarvisRoot = $PSScriptRoot
$pythonPath = Join-Path $jarvisRoot '.venv\Scripts\python.exe'
$serverPath = Join-Path $jarvisRoot 'server.py'
$pidPath = Join-Path $jarvisRoot '.jarvis.pid'
$localUrl = 'http://127.0.0.1:8788'

if ($Stop) {
    if (Test-Path -LiteralPath $pidPath) {
        $jarvisProcessId = [int]([IO.File]::ReadAllText($pidPath).Trim())
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$jarvisProcessId"
        if ($process -and $process.ExecutablePath -eq $pythonPath -and $process.CommandLine.Contains($serverPath)) {
            Stop-Process -Id $jarvisProcessId
            Write-Host 'Servidor de Jarvis detenido.'
        } elseif ($process) {
            throw 'El PID pertenece a otro programa; no se detuvo.'
        } else {
            Write-Host 'El servidor ya estaba detenido.'
        }
        Remove-Item -LiteralPath $pidPath
    } else {
        Write-Host 'No hay un servidor iniciado por este lanzador.'
    }
    exit
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Falta el entorno Python .venv. Ejecuta INSTALAR_JARVIS.cmd.'
}
$config = $null
try { $config = Invoke-RestMethod "$localUrl/api/config" -TimeoutSec 2 } catch {}
if (-not $config) {
    if (Get-NetTCPConnection -LocalPort 8788 -State Listen -ErrorAction SilentlyContinue) {
        throw 'El puerto 8788 esta ocupado por otro programa.'
    }
    $logDir = Join-Path $jarvisRoot '.logs'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
    $serverProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-u', ('"' + $serverPath + '"')) -WorkingDirectory $jarvisRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'server.out.log') -RedirectStandardError (Join-Path $logDir 'server.err.log') -PassThru
    [IO.File]::WriteAllText($pidPath, [string]$serverProcess.Id)
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $config = Invoke-RestMethod "$localUrl/api/config" -TimeoutSec 1; break } catch {}
        if ($serverProcess.HasExited) { throw 'El servidor no pudo iniciar. Revisa .logs\server.err.log.' }
    }
    if (-not $config) { throw 'El servidor tarda en responder. Revisa .logs\server.err.log.' }
}
Write-Host "Jarvis disponible en $localUrl"
if ($Background) { exit }
try {
    $agentConfig = Invoke-RestMethod "$localUrl/api/agent/status" -TimeoutSec 3
    Write-Host "Motor: $($agentConfig.model). Voz: $($agentConfig.voice_mode). Activacion en Conexion."
} catch {Write-Host 'Configura el motor y la voz en Misiones.'}
if ($Online) {
    $webConfigPath = Join-Path $jarvisRoot '.jarvis-web.json'
    if (-not (Test-Path -LiteralPath $webConfigPath)) { throw 'Todavia no se configuro la publicacion online.' }
    $webConfig = Get-Content -LiteralPath $webConfigPath -Raw | ConvertFrom-Json
    $onlineUrl = $webConfig.origin + '/#jarvis-pair=' + [uri]::EscapeDataString($webConfig.token)
    Write-Host "Abriendo la interfaz online: $($webConfig.origin)"
    Start-Process -FilePath $onlineUrl
} else {
    $browser = @(
        (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe')
        (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe')
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
    ) | Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
    if ($browser) {Start-Process -FilePath $browser -ArgumentList "--app=$localUrl"}
    else {Start-Process -FilePath $localUrl}
}
