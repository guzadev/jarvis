param([Parameter(Mandatory=$true)][string]$ReleaseDirectory,[Parameter(Mandatory=$true)][Int64]$InstalledBytes)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$version=(Get-Content -LiteralPath (Join-Path $root 'desktop/package.json') -Raw | ConvertFrom-Json).version
$directory=[IO.Path]::GetFullPath($ReleaseDirectory)
$files=@(Get-ChildItem -LiteralPath $directory -File | Where-Object {$_.Name -match '^Jarvis-Windows-Instalador(-\d+\.bin|\.exe)$'} | Sort-Object Name)
if ($files.Count -lt 2 -or -not ($files.Name -contains 'Jarvis-Windows-Instalador.exe')) {throw 'Faltan archivos del instalador completo.'}
$items=@(foreach($file in $files){
    if ($file.Length -ge 2147483648) {throw 'Un archivo supera el límite de GitHub Releases.'}
    [ordered]@{name=$file.Name;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant();bytes=$file.Length}
})
$manifest=Join-Path $directory 'windows-release.json'
[IO.File]::WriteAllText($manifest,([ordered]@{version=$version;installed_bytes=$InstalledBytes;files=$items} | ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
$compiler=Join-Path $env:SystemRoot 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {throw 'Falta el compilador .NET Framework de Windows.'}
& $compiler /nologo /target:winexe /platform:x64 /codepage:65001 /optimize+ ('/out:'+(Join-Path $directory 'Jarvis-Windows.exe')) ('/win32icon:'+(Join-Path $root 'desktop/icon.ico')) ('/resource:'+$manifest+',release-manifest.json') /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Net.Http.dll /reference:System.Web.Extensions.dll (Join-Path $root 'desktop/download/Downloader.cs')
if ($LASTEXITCODE -ne 0) {throw 'Falló la compilación del asistente de descarga.'}
Write-Output 'Jarvis-Windows.exe compilado con manifiesto SHA-256 embebido.'
