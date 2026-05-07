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
@'
from app.models import TeachingRequest
from app.pipeline import generate_teaching_assets

req = TeachingRequest(
    request_id="local-test",
    course_requirement="Explain binary search to a high school student.",
    student_persona="10th grader, knows basic arrays but not recursion.",
)
assets = generate_teaching_assets(req)
print("Video:", assets["video"])
print("Subtitle:", assets["subtitle"])
print("Supplementary:", assets["supplementary"])
print("Voice provider:", assets["voice_provider"])
'@ | & $python -
