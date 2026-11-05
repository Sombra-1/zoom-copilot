$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $taskCompiler)) {
    $taskCompiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
if (-not (Test-Path -LiteralPath $taskCompiler)) {
    throw 'The Windows .NET Framework compiler was not found.'
}
$taskSource = Join-Path $PSScriptRoot 'WindowsLauncher.cs'
$taskIcon = Join-Path $taskRoot 'assets\app.ico'
$taskOutput = Join-Path $taskRoot 'Zoom Copilot.exe'
& $taskCompiler /nologo /target:winexe /optimize+ "/win32icon:$taskIcon" "/out:$taskOutput" /reference:System.Windows.Forms.dll $taskSource
if ($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }
Write-Output $taskOutput
