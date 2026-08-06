#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

$dataHome = '@DATA_HOME@'
$libexecHome = '@LIBEXEC_HOME@'
$pythonPath = Join-Path $dataHome "speaktext/python"
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $pythonPath
}
else {
    $env:PYTHONPATH = "$pythonPath$([IO.Path]::PathSeparator)$env:PYTHONPATH"
}
$env:SPEAKTEXT_WORKER = Join-Path $libexecHome "speaktext/speaktext-worker"
$env:PYTHONDONTWRITEBYTECODE = "1"

& /usr/bin/python3 -m speaktext @args
exit $LASTEXITCODE
