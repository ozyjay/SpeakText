#!/usr/bin/env pwsh
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "user-install-paths.ps1")
$installPaths = Get-SpeakTextUserInstallPaths
$launcher = Join-Path $installPaths.UserHome ".local/bin/speaktext"

if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
    throw "SpeakText is not installed at $launcher. Run 'make install-user' first."
}

$gdbus = Get-Command gdbus -ErrorAction SilentlyContinue
if ($null -eq $gdbus) {
    throw "gdbus is required to verify that SpeakText is not already running."
}
$owner = & $gdbus.Source call --session --dest org.freedesktop.DBus `
    --object-path /org/freedesktop/DBus `
    --method org.freedesktop.DBus.NameHasOwner local.SpeakText
if ($LASTEXITCODE -ne 0) {
    throw "Could not query the session D-Bus for an existing SpeakText instance."
}
if ($owner -match "\btrue\b") {
    throw "SpeakText is already running. Quit it from the top-bar menu before using 'make run-installed'."
}

$buildLabel = & $launcher --build-id
if ($LASTEXITCODE -ne 0) {
    throw "Could not identify the installed SpeakText build."
}
Write-Host "Running $buildLabel from $launcher"
& $launcher
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
