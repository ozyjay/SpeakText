#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [switch] $Check
)

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
$missing = [Collections.Generic.List[string]]::new()

function Test-Command {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $Package
    )

    if ($null -eq (Get-Command $Name -ErrorAction SilentlyContinue)) {
        $script:missing.Add($Package)
    }
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory)] [string] $Command,
        [Parameter(ValueFromRemainingArguments)] [string[]] $CommandArguments
    )

    & $Command @CommandArguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE."
    }
}

$python3 = Get-Command python3 -ErrorAction SilentlyContinue
Test-Command python3 python3
Test-Command pw-record pipewire-utils
Test-Command cmake cmake
Test-Command ninja ninja-build
Test-Command g++ gcc-c++
Test-Command git git

if ($null -eq $python3) {
    $missing.AddRange([string[]] @("python3-gobject", "gtk4", "libadwaita", "ibus"))
}
else {
    $gtkCheck =
        "import gi; gi.require_version('Gtk', '4.0'); " +
        "gi.require_version('Adw', '1'); gi.require_version('IBus', '1.0')"
    & $python3.Source -c $gtkCheck *> $null
    if ($LASTEXITCODE -ne 0) {
        $missing.AddRange([string[]] @("python3-gobject", "gtk4", "libadwaita", "ibus"))
    }
}

if ($missing.Count -gt 0) {
    $packageList = $missing -join " "
    [Console]::Error.WriteLine("Missing Fedora packages: $packageList")
    [Console]::Error.WriteLine("Install them explicitly, then run this script again.")
    [Console]::Error.WriteLine("Suggested command: sudo dnf install $packageList")
    exit 1
}

if ($Check) {
    Write-Output "All required Fedora dependencies are available."
    exit 0
}

$buildDir = Join-Path $projectDir "build"
Invoke-NativeCommand cmake -S $projectDir -B $buildDir -G Ninja -DCMAKE_BUILD_TYPE=Release
Invoke-NativeCommand cmake --build $buildDir --target speaktext-worker
Write-Output "Built $buildDir/speaktext-worker"
