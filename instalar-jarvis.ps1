param(
    [string]$Storage, [switch]$Offline, [switch]$SinModelosDeVoz,
    [switch]$Chatterbox, [switch]$VozPropia, [switch]$VozQwen, [string]$ReferenciaAudio, [string]$TextoReferencia, [string]$ReferenciaMp3, [switch]$AccesoDirecto
)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
if (($VozPropia -and $Chatterbox) -or ($VozQwen -and ($VozPropia -or $Chatterbox))) {throw 'Elegi un solo motor de voz por instalacion.'}
if ($VozPropia -and (-not $ReferenciaMp3 -or -not (Test-Path -LiteralPath $ReferenciaMp3 -PathType Leaf))) {throw 'Para preparar el perfil local indica -ReferenciaMp3 con la referencia elegida.'}
if ($VozQwen) {
    if (-not $ReferenciaAudio -or -not $TextoReferencia) {throw 'Indica -ReferenciaAudio con tu WAV y -TextoReferencia con un archivo TXT UTF-8.'}
    $ReferenciaAudio=(Resolve-Path -LiteralPath $ReferenciaAudio).Path
    $TextoReferencia=(Resolve-Path -LiteralPath $TextoReferencia).Path
}
Set-Location -LiteralPath $PSScriptRoot
function Run([string]$Program,[string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Fallo $Program (codigo $LASTEXITCODE)." }
}
$python=$null
foreach ($candidate in @('py','python')) {
    if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) {continue}
    $options=@()
    if ($candidate -eq 'py') {$options=@('-3.13')}
    $found=& $candidate @options -c 'import sys;print(sys.executable if sys.version_info[:2]==(3,13) and sys.maxsize>2**32 else str())' 2>$null
    if ($LASTEXITCODE -eq 0 -and $found) {$python=$found;break}
}
if (-not $python) {throw 'Instala Python 3.13 de 64 bits desde https://www.python.org/downloads/windows/ y volve a abrir el instalador.'}
$settingsPath=Join-Path $PSScriptRoot '.jarvis-app.json'
$existing=if(Test-Path -LiteralPath $settingsPath){Get-Content -Raw -Encoding UTF8 -LiteralPath $settingsPath | ConvertFrom-Json}
if (-not $Storage) {
    if ($existing.storage_dir) {$Storage=$existing.storage_dir}
    else {
        $drive=[IO.DriveInfo]::GetDrives() | Where-Object {$_.IsReady -and $_.DriveType -eq 'Fixed'} | Sort-Object AvailableFreeSpace -Descending | Select-Object -First 1
        $default=Join-Path $env:LOCALAPPDATA 'Jarvis-Aurelio'
        if ($drive -and $drive.Name -ne [IO.Path]::GetPathRoot($default)) {$default=Join-Path $drive.Name 'Jarvis-Aurelio'}
        $Storage=$default
    }
}
$Storage=[IO.Path]::GetFullPath($Storage)
New-Item -ItemType Directory -Path $Storage -Force | Out-Null
$volume=Get-PSDrive -Name ([IO.Path]::GetPathRoot($Storage).TrimEnd('\').TrimEnd(':')) -ErrorAction SilentlyContinue
if ($volume -and $null -ne $volume.Free) {Write-Host ("Almacenamiento: {0} ({1:N1} GB libres)" -f $Storage,($volume.Free / 1GB))}
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'jarvis-workspace') -Force | Out-Null
$env:TEMP=Join-Path $Storage 'tmp'
$env:TMP=$env:TEMP
$env:PIP_CACHE_DIR=Join-Path $Storage 'cache\pip'
$env:HF_HOME=Join-Path $Storage 'cache\huggingface'
New-Item -ItemType Directory -Path $env:TEMP,$env:PIP_CACHE_DIR,$env:HF_HOME -Force | Out-Null
$servicePython=Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$agentPython=Join-Path $Storage '.agent-venv\Scripts\python.exe'
if (-not (Test-Path $servicePython)) {Run $python @('-m','venv',(Join-Path $PSScriptRoot '.venv'))}
Run $servicePython @('-m','pip','install','-r','requirements.txt')
if (-not (Test-Path $agentPython)) {Run $python @('-m','venv',(Join-Path $Storage '.agent-venv'))}
Run $agentPython @('-m','pip','install','-r','requirements-agent.txt')
Run $agentPython @('-c','from openjarvis.agents.orchestrator import OrchestratorAgent; import sympy, matplotlib, faster_whisper, sherpa_onnx')
$env:JARVIS_INSTALL_STORAGE=$Storage
$env:JARVIS_INSTALL_LOCAL=if($Offline){'1'}else{'0'}
$init=@'
import os, secrets, json
from pathlib import Path
import app_runtime
base=Path.cwd()
new=not app_runtime.CONFIG_PATH.exists()
options=dict(storage_dir=os.environ['JARVIS_INSTALL_STORAGE'])
if new:options.update(tts_engine='piper',voice='local')
if os.environ['JARVIS_INSTALL_LOCAL']=='1':options['provider']='local'
app_runtime.save_settings(options)
if not (base/'.env').exists():(base/'.env').write_text('OPENAI_API_KEY=\nJARVIS_LANGUAGE=es\n',encoding='utf-8')
pairing=base/'.jarvis-web.json'
if not pairing.exists():pairing.write_text(json.dumps(dict(origin='https://jarvis-aurelio.vercel.app',token=secrets.token_urlsafe(40))),encoding='utf-8')
'@
$init | & $servicePython -
if ($LASTEXITCODE -ne 0) {throw 'Fallo la configuracion local.'}
if (-not $SinModelosDeVoz) {Run $servicePython @('preparar-activacion.py')}
if (-not $SinModelosDeVoz -and -not $VozPropia -and -not $VozQwen) {Run $agentPython @('preparar-modelos.py','--voice-only')}
if ($VozPropia -or $VozQwen) {
    "import app_runtime; app_runtime.save_settings({'voice':'owned'})" | & $servicePython -
    if ($LASTEXITCODE -ne 0) {throw 'Fallo la seleccion del perfil local.'}
    if (-not $SinModelosDeVoz) {Run $agentPython @('preparar-modelos.py','--transcription-only')}
    if ($VozQwen) {Run $servicePython @('preparar-voz-qwen.py','--storage',$Storage,'--reference',$ReferenciaAudio,'--transcript',$TextoReferencia)}
    else {Run $servicePython @('preparar-voz-propia.py','--storage',$Storage,'--reference',$ReferenciaMp3)}
}
if ($Offline) {
    if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString() -ne 'X64') {throw 'El paquete Ollama automatico requiere Windows x64.'}
    $ollama=Join-Path $Storage 'tools\ollama'
    if (-not (Test-Path (Join-Path $ollama 'ollama.exe'))) {
        $archive=Join-Path $env:TEMP 'ollama-v0.40.16.zip'
        Invoke-WebRequest -UseBasicParsing 'https://github.com/ollama/ollama/releases/download/v0.40.16/ollama-windows-amd64.zip' -OutFile $archive
        if ((Get-FileHash $archive -Algorithm SHA256).Hash -ne '50fcf5ad54277f2fa5d173ebfc93bcb017adbc0c9ef2314daabc96ca9e6aa64e') {throw 'Fallo la verificacion SHA-256 de Ollama.'}
        Expand-Archive -LiteralPath $archive -DestinationPath $ollama -Force
        Remove-Item -LiteralPath $archive
    }
    Run $agentPython @('preparar-modelos.py','--llm-only')
}
if ($Chatterbox) {
    if (-not $ReferenciaMp3 -or -not (Test-Path -LiteralPath $ReferenciaMp3 -PathType Leaf) -or [IO.Path]::GetExtension($ReferenciaMp3) -ne '.mp3') {throw 'Para Chatterbox indica -ReferenciaMp3 con tu muestra MP3.'}
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {throw 'La instalacion opcional de Chatterbox requiere Git para Windows.'}
    $voiceEnv=Join-Path $Storage '.voice-venv'
    $voicePython=Join-Path $voiceEnv 'Scripts\python.exe'
    if (-not (Test-Path $voicePython)) {Run $python @('-m','venv',$voiceEnv)}
    Run $voicePython @('-m','pip','install','torch==2.6.0','torchaudio==2.6.0','--index-url','https://download.pytorch.org/whl/cu124')
    Run $voicePython @('-m','pip','install','https://github.com/resemble-ai/chatterbox/archive/ab55923c27757c90cfcc407baa57dc25a7d25217.zip','fastapi','uvicorn')
    Run $voicePython @('-c','from chatterbox.mtl_tts import ChatterboxMultilingualTTS')
    $refFolder=Join-Path $Storage 'models\voice-reference'
    New-Item -ItemType Directory -Path $refFolder -Force | Out-Null
    $dest=Join-Path $refFolder 'jarvis-latino.mp3'
    if ([IO.Path]::GetFullPath($ReferenciaMp3) -ne [IO.Path]::GetFullPath($dest)) {Copy-Item -LiteralPath $ReferenciaMp3 -Destination $dest -Force}
    "import app_runtime; app_runtime.save_settings({'tts_engine':'jarvis_local','voice':'local'})" | & $servicePython -
    if ($LASTEXITCODE -ne 0) {throw 'Fallo la seleccion de voz.'}
}
if ($AccesoDirecto) {
    $desktop=[Environment]::GetFolderPath('Desktop')
    $shortcut=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'Jarvis Aurelio.lnk'))
    $shortcut.TargetPath=Join-Path $PSScriptRoot 'INICIAR_JARVIS.cmd'
    $shortcut.WorkingDirectory=$PSScriptRoot
    $shortcut.Save()
}
Write-Host 'Instalacion terminada. Abri INICIAR_JARVIS.cmd o ABRIR_JARVIS_ONLINE.cmd.'
