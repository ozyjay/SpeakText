#!/usr/bin/env pwsh
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectDir = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "user-install-paths.ps1")
$installPaths = Get-SpeakTextUserInstallPaths
$dataHome = $installPaths.DataHome
$binDir = Join-Path $installPaths.UserHome ".local/bin"
$libexecHome = Join-Path $installPaths.UserHome ".local/libexec"
$libexecDir = Join-Path $libexecHome "speaktext"
$pythonDir = Join-Path $dataHome "speaktext/python"
$applicationsDir = Join-Path $dataHome "applications"
$iconsDir = Join-Path $dataHome "icons/hicolor/scalable/apps"
$dbusServicesDir = Join-Path $dataHome "dbus-1/services"
$extensionUuid = "speaktext@local"
$extensionDir = Join-Path $dataHome "gnome-shell/extensions/$extensionUuid"
$workerSource = Join-Path $projectDir "build/speaktext-worker"
$executableMode =
    [IO.UnixFileMode]::UserRead -bor [IO.UnixFileMode]::UserWrite -bor
    [IO.UnixFileMode]::UserExecute -bor [IO.UnixFileMode]::GroupRead -bor
    [IO.UnixFileMode]::GroupExecute -bor [IO.UnixFileMode]::OtherRead -bor
    [IO.UnixFileMode]::OtherExecute
$readableMode =
    [IO.UnixFileMode]::UserRead -bor [IO.UnixFileMode]::UserWrite -bor
    [IO.UnixFileMode]::GroupRead -bor [IO.UnixFileMode]::OtherRead

function Install-ExecutableAtomically {
    param(
        [Parameter(Mandatory)] [string] $Source,
        [Parameter(Mandatory)] [string] $Destination
    )

    $destinationDir = Split-Path -Parent $Destination
    $temporaryName = ".speaktext-worker.$PID.$([guid]::NewGuid()).tmp"
    $temporaryPath = Join-Path $destinationDir $temporaryName
    try {
        Copy-Item -LiteralPath $Source -Destination $temporaryPath
        [IO.File]::SetUnixFileMode($temporaryPath, $executableMode)
        [IO.File]::Move($temporaryPath, $Destination, $true)
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
}

if (-not (Test-Path -LiteralPath $workerSource -PathType Leaf)) {
    [Console]::Error.WriteLine(
        "Native worker is missing; run scripts/bootstrap.ps1 first."
    )
    exit 1
}

$skipExtensionEnable = $env:SPEAKTEXT_SKIP_EXTENSION_ENABLE -eq "1"
$gnomeExtensions = Get-Command gnome-extensions -ErrorAction SilentlyContinue
if (-not $skipExtensionEnable -and $null -ne $gnomeExtensions) {
    & $gnomeExtensions.Source disable $extensionUuid 2>$null | Out-Null
}

@(
    $binDir,
    $libexecDir,
    $pythonDir,
    $applicationsDir,
    $iconsDir,
    $dbusServicesDir,
    $extensionDir
) | ForEach-Object {
    $null = New-Item -ItemType Directory -Path $_ -Force
}

$launcherPath = Join-Path $binDir "speaktext"
$launcher = Get-Content (Join-Path $PSScriptRoot "speaktext-launcher") -Raw
$launcher = $launcher.Replace(
    '"@DATA_HOME@"', (ConvertTo-Json -InputObject $dataHome -Compress)
)
$launcher = $launcher.Replace(
    '"@LIBEXEC_HOME@"', (ConvertTo-Json -InputObject $libexecHome -Compress)
)
Set-Content -LiteralPath $launcherPath -Value $launcher -NoNewline -Encoding utf8
$workerDestination = Join-Path $libexecDir "speaktext-worker"
Install-ExecutableAtomically $workerSource $workerDestination

$pythonPackageDir = Join-Path $pythonDir "speaktext"
$null = New-Item -ItemType Directory -Path $pythonPackageDir -Force
Get-ChildItem (Join-Path $projectDir "src/speaktext") -Filter "*.py" -File |
    Copy-Item -Destination $pythonPackageDir -Force
$buildRevision = "unknown revision"
$git = Get-Command git -ErrorAction SilentlyContinue
if ($null -ne $git) {
    $revision = & $git.Source -C $projectDir rev-parse --short HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $revision -match "^[0-9a-f]+$") {
        $buildRevision = $revision
    }
}
$installedBuildInfo = @"
"""Identity embedded when SpeakText is installed for a user."""

BUILD_LABEL = "Installed build: $buildRevision"
"@
Set-Content -LiteralPath (Join-Path $pythonPackageDir "build_info.py") `
    -Value $installedBuildInfo -NoNewline -Encoding utf8
Copy-Item -LiteralPath (Join-Path $projectDir "data/local.SpeakText.svg") `
    -Destination (Join-Path $iconsDir "local.SpeakText.svg") -Force

$desktopEntry = (Get-Content (Join-Path $projectDir "data/local.SpeakText.desktop.in") -Raw).
    Replace("@EXEC@", $launcherPath)
$desktopPath = Join-Path $applicationsDir "local.SpeakText.desktop"
Set-Content -LiteralPath $desktopPath -Value $desktopEntry -NoNewline -Encoding utf8
$dbusService = (Get-Content (Join-Path $projectDir "data/local.SpeakText.service.in") -Raw).
    Replace("@EXEC@", $launcherPath)
$dbusServicePath = Join-Path $dbusServicesDir "local.SpeakText.service"
Set-Content -LiteralPath $dbusServicePath -Value $dbusService -NoNewline -Encoding utf8
Copy-Item -LiteralPath (Join-Path $projectDir "extension/extension.js") `
    -Destination (Join-Path $extensionDir "extension.js") -Force
Copy-Item -LiteralPath (Join-Path $projectDir "extension/metadata.json") `
    -Destination (Join-Path $extensionDir "metadata.json") -Force

[IO.File]::SetUnixFileMode($launcherPath, $executableMode)
[IO.File]::SetUnixFileMode($workerDestination, $executableMode)
@(
    $desktopPath,
    $dbusServicePath,
    (Join-Path $iconsDir "local.SpeakText.svg"),
    (Join-Path $extensionDir "extension.js"),
    (Join-Path $extensionDir "metadata.json")
) | ForEach-Object { [IO.File]::SetUnixFileMode($_, $readableMode) }
Get-ChildItem $pythonPackageDir -Filter "*.py" -File |
    ForEach-Object { [IO.File]::SetUnixFileMode($_.FullName, $readableMode) }

$updateDesktopDatabase = Get-Command update-desktop-database -ErrorAction SilentlyContinue
if ($null -ne $updateDesktopDatabase) {
    & $updateDesktopDatabase.Source $applicationsDir 2>$null | Out-Null
}

$extensionStatus = "installed but not enabled"
if ($skipExtensionEnable) {
    $extensionStatus = "extension enable skipped"
}
elseif ($null -ne $gnomeExtensions) {
    & $gnomeExtensions.Source enable $extensionUuid 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $extensionStatus = "top-bar extension enabled"
    }
    else {
        [Console]::Error.WriteLine(
            "GNOME has not loaded the new extension yet. Log out and back in, then run:"
        )
        [Console]::Error.WriteLine("  gnome-extensions enable $extensionUuid")
    }
}
else {
    [Console]::Error.WriteLine(
        "GNOME has not loaded the new extension yet. Log out and back in, then run:"
    )
    [Console]::Error.WriteLine("  gnome-extensions enable $extensionUuid")
}

Write-Output "Installed SpeakText for the current user ($extensionStatus). Run: $launcherPath"
Write-Output "Start SpeakText, then add it in GNOME Settings > Keyboard > Input Sources."
