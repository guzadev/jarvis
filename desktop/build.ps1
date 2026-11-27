param([string]$Output, [string]$Storage, [string]$Compiler)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$repo=Split-Path -Parent $PSScriptRoot
if (-not $Storage) {
    $settings=Get-Content -LiteralPath (Join-Path $repo '.jarvis-app.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $Storage=$settings.storage_dir
}
$Storage=[IO.Path]::GetFullPath($Storage)
if (-not $Output) {$Output=Join-Path $Storage ('build\desktop-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))}
$Output=[IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath $Output) {throw 'ElegÃ­ una carpeta de salida nueva. El proceso conserva las compilaciones anteriores.'}
if (-not $Compiler) {
    $candidate=Join-Path $Storage 'tools\inno-setup\ISCC.exe'
    if (Test-Path -LiteralPath $candidate) {$Compiler=$candidate}
    else {$Compiler=(Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source}
}
if (-not $Compiler -or -not (Test-Path -LiteralPath $Compiler)) {throw 'Para compilar instalÃ¡ Inno Setup y pasÃ¡ su ISCC.exe en -Compiler. El destinatario no lo necesita.'}
$python=Join-Path $repo '.venv\Scripts\python.exe'
$pythonHome=& $python -c 'import sys; print(sys.base_prefix)'
if ($LASTEXITCODE -ne 0) {throw 'No se pudo identificar el Python de la compilaciÃ³n.'}
New-Item -ItemType Directory -Path $Output -Force | Out-Null
$env:TEMP=Join-Path $Storage 'tmp'; $env:TMP=$env:TEMP
$env:npm_config_cache=Join-Path $Storage 'cache\npm'
$env:ELECTRON_CACHE=Join-Path $Storage 'cache\electron'
$env:ELECTRON_BUILDER_CACHE=Join-Path $Storage 'cache\electron-builder'
$tools=Join-Path $Output 'desktop-source'
New-Item -ItemType Directory -Path $tools,(Join-Path $tools 'test') -Force | Out-Null
foreach($name in @('package.json','package-lock.json','main.cjs','runtime.cjs','policy.cjs','preload.cjs','onboarding.html','onboarding.js','icon.png','icon.ico')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $tools $name)
}
foreach($name in @('policy.test.cjs','runtime.test.cjs')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('test\'+$name)) -Destination (Join-Path $tools ('test\'+$name))
}
Set-Location -LiteralPath $tools
function Run([string]$Program,[string[]]$Arguments) { & $Program @Arguments; if ($LASTEXITCODE -ne 0) {throw "La compilaciÃ³n se detuvo: $Program"} }
Run 'npm' @('ci','--no-audit','--no-fund')
Run 'node' @('--test','test/policy.test.cjs','test/runtime.test.cjs')
Run $python @((Join-Path $PSScriptRoot 'test\test_desktop_bridge.py'))
$electron=Join-Path $Output 'electron'
Run 'node' @('node_modules/electron-builder/cli.js','--win','--x64','--dir','--publish','never',('--config.directories.output='+$electron))
$payload=Join-Path $Output 'payload'
Run $python @((Join-Path $PSScriptRoot 'stage-offline.py'),'--source',$repo,'--storage',$Storage,'--python-home',$pythonHome,'--electron-dir',(Join-Path $electron 'win-unpacked'),'--output',$payload)
$installer=Join-Path $Output 'installer'
Run $Compiler @(('--define=Payload='+$payload),('--define=OutputFolder='+$installer),('--define=Version='+((Get-Content -LiteralPath (Join-Path $PSScriptRoot 'package.json') -Raw | ConvertFrom-Json).version)),(Join-Path $PSScriptRoot 'installer.iss'))
Write-Host ('Instalador completo: '+$installer)
