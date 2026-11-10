param([string]$PythonPath, [string]$ShortcutName = 'Zoom Copilot v2.1 Preview')
$ErrorActionPreference = 'Stop'
$taskRepo = $PSScriptRoot
if (-not $PythonPath) {
    $taskCandidates = @(
        (Join-Path $taskRepo 'venv\Scripts\pythonw.exe'),
        (Join-Path $taskRepo '.venv\Scripts\pythonw.exe')
    )
    $taskCandidates += @(Get-Command pythonw.exe, pyw.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    $PythonPath = $taskCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
}
$taskLauncher = Join-Path $taskRepo 'Zoom Copilot.exe'
if (-not (Test-Path -LiteralPath $taskLauncher) -and
    (-not $PythonPath -or -not (Test-Path -LiteralPath $PythonPath -PathType Leaf))) {
    throw 'A windowless Python interpreter was not found. Run setup.bat first.'
}
$taskDesktop = [Environment]::GetFolderPath('Desktop')
$taskShortcutPath = Join-Path $taskDesktop ($ShortcutName + '.lnk')
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $taskShell.CreateShortcut($taskShortcutPath)
if (Test-Path -LiteralPath $taskLauncher) {
    $taskShortcut.TargetPath = $taskLauncher
    $taskShortcut.Arguments = ''
    if ($PythonPath) {
        $taskShortcut.Arguments = '--python "' + (Resolve-Path -LiteralPath $PythonPath).Path + '"'
    }
} else {
    $taskShortcut.TargetPath = (Resolve-Path -LiteralPath $PythonPath).Path
    $taskShortcut.Arguments = '"' + (Join-Path $taskRepo 'launch.pyw') + '"'
}
$taskShortcut.IconLocation = (Join-Path $taskRepo 'assets\app.ico') + ',0'
$taskShortcut.WorkingDirectory = $taskRepo
$taskShortcut.Description = 'Zoom Copilot'
$taskShortcut.Save()
Write-Output $taskShortcutPath
