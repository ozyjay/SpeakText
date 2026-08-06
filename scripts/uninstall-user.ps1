#!/usr/bin/env pwsh
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "user-install-paths.ps1")
$installPaths = Get-SpeakTextUserInstallPaths
$dataHome = $installPaths.DataHome
$extensionUuid = "speaktext@local"
$skipExtensionEnable = $env:SPEAKTEXT_SKIP_EXTENSION_ENABLE -eq "1"
$gnomeExtensions = Get-Command gnome-extensions -ErrorAction SilentlyContinue
if (-not $skipExtensionEnable -and $null -ne $gnomeExtensions) {
    & $gnomeExtensions.Source disable $extensionUuid 2>$null | Out-Null
}

$targets = @(
    (Join-Path $installPaths.UserHome ".local/bin/speaktext"),
    (Join-Path $installPaths.UserHome ".local/libexec/speaktext/speaktext-worker"),
    (Join-Path $dataHome "applications/local.SpeakText.desktop"),
    (Join-Path $dataHome "icons/hicolor/scalable/apps/local.SpeakText.svg"),
    (Join-Path $dataHome "dbus-1/services/local.SpeakText.service"),
    (Join-Path $dataHome "speaktext/python/speaktext"),
    (Join-Path $dataHome "gnome-shell/extensions/$extensionUuid")
)
foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

@(
    (Join-Path $installPaths.UserHome ".local/libexec/speaktext"),
    (Join-Path $dataHome "speaktext/python")
) | ForEach-Object {
    if (Test-Path -LiteralPath $_) {
        try {
            [IO.Directory]::Delete($_, $false)
        }
        catch [IO.IOException] {
            # Retain non-empty directories.
        }
    }
}

Write-Output "Uninstalled SpeakText. Models, settings, and diagnostics were retained."
