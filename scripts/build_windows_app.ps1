param(
    [switch]$Installer,
    [switch]$InstallerOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = if ($env:PYTHON) {
    $env:PYTHON
} elseif (Test-Path -LiteralPath (Join-Path $Root ".venv\Scripts\python.exe") -PathType Leaf) {
    Join-Path $Root ".venv\Scripts\python.exe"
} else {
    (Get-Command python -ErrorAction Stop).Source
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python environment not found: $Python"
}

if (-not $InstallerOnly) {
    & $Python (Join-Path $Root "scripts\build_desktop_app.py") --platform windows
    if ($LASTEXITCODE -ne 0) {
        throw "Windows desktop build failed with exit code $LASTEXITCODE"
    }
}

$App = Join-Path $Root "build\windows\LectureAuto.dist"
if (-not (Test-Path -LiteralPath (Join-Path $App "LectureAuto.exe") -PathType Leaf)) {
    throw "Built application not found: $App"
}

if ($Installer -or $InstallerOnly) {
    $Candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $Compiler = $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
    if (-not $Compiler) {
        $Command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($Command) { $Compiler = $Command.Source }
    }
    if (-not $Compiler) {
        throw "Inno Setup 6 was not found. Install it or run without -Installer."
    }
    Push-Location $Root
    try {
        & $Compiler "deployment\windows.iss"
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
    Write-Output "Built installer: $(Join-Path $Root 'dist-installer\LectureAuto-Setup.exe')"
}
else {
    Write-Output "Built application: $App"
}
