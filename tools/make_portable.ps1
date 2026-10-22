[CmdletBinding()]
param(
    [string]$SourceEnvironment = '',
    [string]$PythonHome = '',
    [string]$VCRedistDirectory = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $SourceEnvironment) { $SourceEnvironment = Join-Path $projectRoot 'venv' }
$sourcePython = Join-Path $SourceEnvironment 'Scripts/python.exe'
$sourcePackages = Join-Path $SourceEnvironment 'Lib/site-packages'
$runtimeRoot = Join-Path $projectRoot 'runtime'

if (-not (Test-Path -LiteralPath $sourcePython)) {
    throw 'Create the documented venv and install the dependencies first, or supply -SourceEnvironment.'
}
if (Test-Path -LiteralPath $runtimeRoot) {
    throw 'runtime already exists. Keep the working bundle; build a fresh bundle in a separate checkout to update it.'
}
if (-not $PythonHome) {
    $PythonHome = & $sourcePython -c 'import os, sys; print(os.path.realpath(sys.base_prefix))'
    if ($LASTEXITCODE -ne 0) { throw 'Could not locate the base Python runtime.' }
}
$PythonHome = (Resolve-Path -LiteralPath $PythonHome).ProviderPath
if (-not (Test-Path -LiteralPath (Join-Path $PythonHome 'python311.dll'))) {
    throw 'This bundle requires a Windows x64 CPython 3.11 runtime matching the installed dependencies.'
}
if (-not $VCRedistDirectory) {
    $redistCandidates = Get-ChildItem -Path 'C:/Program Files/Microsoft Visual Studio/*/*/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT', 'C:/Program Files (x86)/Microsoft Visual Studio/*/*/VC/Redist/MSVC/*/x64/Microsoft.VC*.CRT' -Directory -ErrorAction SilentlyContinue
    $VCRedistDirectory = ($redistCandidates | Sort-Object FullName -Descending | Select-Object -First 1).FullName
}
if (-not $VCRedistDirectory -or -not (Test-Path -LiteralPath (Join-Path $VCRedistDirectory 'msvcp140.dll'))) {
    throw 'Supply -VCRedistDirectory pointing to the x64 Microsoft.VC143.CRT app-local redistributable directory from Visual Studio / Build Tools.'
}

Write-Output ('Copying Python runtime from ' + $PythonHome)
New-Item -ItemType Directory -Path $runtimeRoot | Out-Null
Get-ChildItem -LiteralPath $PythonHome -Force | Copy-Item -Destination $runtimeRoot -Recurse -Force
$targetPackages = Join-Path $runtimeRoot 'Lib/site-packages'
New-Item -ItemType Directory -Path $targetPackages -Force | Out-Null
Write-Output 'Bundling installed dependencies (including CUDA PyTorch)...'
Get-ChildItem -LiteralPath $sourcePackages -Force | Copy-Item -Destination $targetPackages -Recurse -Force
Write-Output ('Bundling app-local Microsoft C++ runtime from ' + $VCRedistDirectory)
Get-ChildItem -LiteralPath $VCRedistDirectory -Filter '*.dll' -File | Copy-Item -Destination $runtimeRoot -Force

# Only relative paths, isolated from registry, PYTHONHOME, PYTHONPATH and user site.
# The parent entry exposes this checkout's modules when launched from any folder.
$relativePaths = @('.', 'Lib', 'DLLs', 'Lib/site-packages', '..', 'import site')
$pathConfig = Join-Path $runtimeRoot 'python311._pth'
[System.IO.File]::WriteAllLines($pathConfig, $relativePaths, [System.Text.UTF8Encoding]::new($false))
foreach ($virtualenvHook in @('_virtualenv.pth', '_virtualenv.py')) {
    $hookPath = Join-Path $targetPackages $virtualenvHook
    if (Test-Path -LiteralPath $hookPath) { Remove-Item -LiteralPath $hookPath -Force }
}

$portablePython = Join-Path $runtimeRoot 'python.exe'
& $portablePython -c 'import sys, pathlib, ctypes, torch, cv2, transformers, utils3d; root=pathlib.Path(sys.executable).resolve().parent.parent; assert sys.flags.isolated; assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in sys.path); libraries=[ctypes.WinDLL(n) for n in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")]; paths=[]; [(lambda b,h: (ctypes.windll.kernel32.GetModuleFileNameW(ctypes.c_void_p(h),b,len(b)),paths.append(b.value)))(ctypes.create_unicode_buffer(32768),lib._handle) for lib in libraries]; assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), paths; print("Portable Python:", sys.version); print("PyTorch:",torch.__version__); print("Python paths and required Microsoft C++ runtime DLLs are inside the portable folder.")'
if ($LASTEXITCODE -ne 0) { throw 'Portable runtime validation failed. Keep the original venv until this is resolved.' }
Write-Output 'Portable Python bundle created. Keep runtime, ffmpeg.exe, weights and vfms with the application files.'
