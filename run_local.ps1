$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundledPython = "C:\Users\yu891\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path $bundledPython) {
  $python = $bundledPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
  $python = "py"
} else {
  $python = "python"
}

$env:PYTHONPATH = $root
Set-Location $root
& $python -m app.simple_server
