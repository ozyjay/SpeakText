# Development

## Prerequisites

SpeakText targets Fedora 44 Workstation with GNOME Wayland. Required tools and
runtime libraries are checked with PowerShell 7 (`pwsh`):

```powershell
./scripts/bootstrap.ps1 -Check
```

The script never invokes `sudo`. If dependencies are absent, it prints the
corresponding Fedora package names and exits.

The installed `speaktext` command is a direct Python entry point, matching the
application process identity expected by XDG Desktop Portal. PowerShell remains
the language for build and maintenance scripts but is not part of the running
application's process tree.

## Build and run

Build the native CPU worker:

```powershell
make build
```

CMake fetches the pinned `whisper.cpp` 1.9.1 revision into the ignored build
tree and links it statically into `build/speaktext-worker`. GPU backends are
disabled and `-march=native` optimises the worker for the build machine.

Run directly from the repository:

```powershell
make run
```

`make run` always runs the development checkout and reports that fact before
launching. The top-bar indicator launches the installed application instead.
After `make install-user`, use the following command to test the same launcher
as the top-bar item:

```powershell
make run-installed
```

Quit SpeakText first: `make run-installed` refuses to continue while another
instance owns the application D-Bus name, avoiding a launch that would silently
forward to the development checkout. It prints the installed build identity
before opening the window.

The **Diagnostics → Build** row identifies the running copy as either the
development checkout or the installed Git revision. Reinstall before verifying
top-bar changes so that the extension, launcher, Python code, and worker stay
in sync.

First run downloads `ggml-base.en.bin`, checks its pinned SHA-256 digest, and
stores it in the XDG data directory. While SpeakText is running, add it as a
GNOME input source. No Global Shortcuts or Remote Desktop permission is
requested.

## Automated tests

Run all tests that avoid microphone and live IBus side effects:

```powershell
make test
```

The ordinary suite uses fakes for PipeWire, IBus gestures and insertion,
clipboard access, and worker inference. The native integration test is skipped
unless a model path is supplied:

```powershell
$env:SPEAKTEXT_TEST_MODEL = "/path/to/ggml-base.en.bin"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = "src"
python3 -m unittest tests.test_native_worker -v
```

This test loads the real model, sends one second of silent PCM through the
framed protocol, verifies a UTF-8 response, and requests graceful shutdown.

Useful additional checks are:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = "src"
python3 -m speaktext --help
pwsh -NoProfile -Command '$failed = $false; Get-ChildItem scripts/*.ps1 | ForEach-Object { $tokens = $null; $errors = $null; [Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref] $tokens, [ref] $errors) > $null; if ($errors.Count) { $failed = $true; Write-Error $errors } }; if ($failed) { exit 1 }'
python3 -c "import ast, pathlib; ast.parse(pathlib.Path('scripts/speaktext-launcher').read_text())"
node --check extension/extension.js
gnome-extensions pack --force --out-dir /tmp extension
cmake --build build --target speaktext-worker
```

IBus and microphone validation is intentionally manual; use
[acceptance-testing.md](acceptance-testing.md) in an attended GNOME session.

## Isolated installation smoke test

Do not install into the real home merely to test the scripts. Use temporary
locations:

```powershell
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
$null = New-Item -ItemType Directory -Path "$testRoot/home" -Force
$savedHome = $env:HOME
$savedDataHome = $env:XDG_DATA_HOME
$savedSkipEnable = $env:SPEAKTEXT_SKIP_EXTENSION_ENABLE
$savedSkipInputSource = $env:SPEAKTEXT_SKIP_INPUT_SOURCE
$env:HOME = "$testRoot/home"
$env:XDG_DATA_HOME = "$testRoot/data"
$env:SPEAKTEXT_SKIP_EXTENSION_ENABLE = "1"
$env:SPEAKTEXT_SKIP_INPUT_SOURCE = "1"
try {
    ./scripts/install-user.ps1
    ./scripts/uninstall-user.ps1
}
finally {
    $env:HOME = $savedHome
    $env:XDG_DATA_HOME = $savedDataHome
    $env:SPEAKTEXT_SKIP_EXTENSION_ENABLE = $savedSkipEnable
    $env:SPEAKTEXT_SKIP_INPUT_SOURCE = $savedSkipInputSource
    Remove-Item -LiteralPath $testRoot -Recurse -Force
}
```

Skipping extension enablement and input-source configuration is required for
this isolated check because it must not change the live GNOME session. Verify
the installed extension and input source interactively using
[acceptance-testing.md](acceptance-testing.md).

The uninstaller intentionally retains model, configuration, and state data.
The installer atomically replaces the persistent native worker, so reinstalling
while SpeakText is running does not fail with a `Text file busy` error. The
running process continues using its previous worker until SpeakText restarts.

## Change checklist

- Add or update tests for behaviour changes.
- Build the native worker after C++ or CMake changes.
- Run the acceptance checklist after IBus, gesture, audio, clipboard, or
  insertion changes.
- Check that new diagnostics cannot contain PCM or transcript content.
- Update architecture and privacy documentation when interfaces, permissions,
  paths, or persistence change.
