function Get-SpeakTextUserInstallPaths {
    [CmdletBinding()]
    param()

    $userHome = $env:HOME
    if ([string]::IsNullOrWhiteSpace($userHome)) {
        throw "HOME is not set."
    }

    $dataHome = if ([string]::IsNullOrWhiteSpace($env:XDG_DATA_HOME)) {
        Join-Path $userHome ".local/share"
    }
    else {
        $env:XDG_DATA_HOME
    }

    $snapDataHomes = @()
    if (-not [string]::IsNullOrWhiteSpace($env:SNAP_USER_DATA)) {
        $snapDataHomes += Join-Path $env:SNAP_USER_DATA ".local/share"
    }
    if (-not [string]::IsNullOrWhiteSpace($env:SNAP_USER_COMMON)) {
        $snapDataHomes += Join-Path $env:SNAP_USER_COMMON ".local/share"
    }

    $realHome = if ([string]::IsNullOrWhiteSpace($env:SNAP_REAL_HOME)) {
        $userHome
    }
    else {
        $env:SNAP_REAL_HOME
    }
    $snapRoot = (Join-Path $realHome "snap") + [IO.Path]::DirectorySeparatorChar
    $snapShapedDataHome =
        $dataHome.StartsWith($snapRoot, [StringComparison]::Ordinal) -and
        $dataHome.EndsWith("/.local/share", [StringComparison]::Ordinal)
    $snapPrivateDataHome =
        $snapShapedDataHome -or $snapDataHomes -ccontains $dataHome

    if ($snapPrivateDataHome) {
        $userHome = $realHome
        $dataHome = Join-Path $userHome ".local/share"
        [Console]::Error.WriteLine(
            "Ignoring Snap-private XDG_DATA_HOME; using $dataHome."
        )
    }

    [PSCustomObject]@{
        UserHome = $userHome
        DataHome = $dataHome
        SnapPrivateDataHome = $snapPrivateDataHome
    }
}
