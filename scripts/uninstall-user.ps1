#!/usr/bin/env pwsh
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "user-install-paths.ps1")
$installPaths = Get-SpeakTextUserInstallPaths
$dataHome = $installPaths.DataHome
$ibusComponentDir = Join-Path $dataHome "ibus/component"
$ibusServiceDropInDir = Join-Path $installPaths.UserHome ".config/systemd/user/org.freedesktop.IBus.session.GNOME.service.d"
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
    (Join-Path $dataHome "ibus/component/local.SpeakText.xml"),
    (Join-Path $ibusServiceDropInDir "10-speaktext-component-path.conf"),
    (Join-Path $dataHome "speaktext/python/speaktext"),
    (Join-Path $dataHome "gnome-shell/extensions/$extensionUuid")
)
foreach ($target in $targets) {
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

$ibus = Get-Command ibus -ErrorAction SilentlyContinue
if ($null -ne $ibus) {
    $savedIbusComponentPath = $env:IBUS_COMPONENT_PATH
    try {
        $componentPaths = @($ibusComponentDir, "/usr/share/ibus/component")
        if (-not [string]::IsNullOrWhiteSpace($savedIbusComponentPath)) {
            $componentPaths += $savedIbusComponentPath -split [IO.Path]::PathSeparator
        }
        $env:IBUS_COMPONENT_PATH = $componentPaths -join [IO.Path]::PathSeparator
        & $ibus.Source write-cache 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("Could not refresh the user IBus registry.")
        }
    }
    finally {
        if ($null -eq $savedIbusComponentPath) {
            Remove-Item Env:IBUS_COMPONENT_PATH -ErrorAction SilentlyContinue
        }
        else {
            $env:IBUS_COMPONENT_PATH = $savedIbusComponentPath
        }
    }
}

@(
    (Join-Path $installPaths.UserHome ".local/libexec/speaktext"),
    (Join-Path $dataHome "speaktext/python"),
    $ibusComponentDir,
    $ibusServiceDropInDir
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

$systemctl = Get-Command systemctl -ErrorAction SilentlyContinue
if ($null -ne $systemctl) {
    & $systemctl.Source --user daemon-reload 2>$null | Out-Null
}

Write-Output "Uninstalled SpeakText. Models, legacy settings, and diagnostics were retained."
