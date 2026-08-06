# Development

## Prerequisites

SpeakText targets Fedora 44 Workstation with GNOME Wayland. Required tools and
runtime libraries are checked with:

```bash
./scripts/bootstrap.sh --check
```

The script never invokes `sudo`. If dependencies are absent, it prints the
corresponding Fedora package names and exits.

## Build and run

Build the native CPU worker:

```bash
make build
```

CMake fetches the pinned `whisper.cpp` 1.9.1 revision into the ignored build
tree and links it statically into `build/speaktext-worker`. GPU backends are
disabled and `-march=native` optimises the worker for the build machine.

Run directly from the repository:

```bash
make run
```

First run downloads `ggml-base.en.bin`, checks its pinned SHA-256 digest, and
stores it in the XDG data directory. GNOME then presents the shortcut and
keyboard-only permission dialogs.

## Automated tests

Run all tests that avoid microphone and portal side effects:

```bash
make test
```

The ordinary suite uses fakes for PipeWire, portals, keyboard injection,
clipboard access, and worker inference. The native integration test is skipped
unless a model path is supplied:

```bash
SPEAKTEXT_TEST_MODEL=/path/to/ggml-base.en.bin \
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  python3 -m unittest tests.test_native_worker -v
```

This test loads the real model, sends one second of silent PCM through the
framed protocol, verifies a UTF-8 response, and requests graceful shutdown.

Useful additional checks are:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m speaktext --help
bash -n scripts/*.sh
node --check extension/extension.js
gnome-extensions pack --force --out-dir /tmp extension
cmake --build build --target speaktext-worker
```

Portal and microphone validation is intentionally manual; use
[acceptance-testing.md](acceptance-testing.md) in an attended GNOME session.

## Isolated installation smoke test

Do not install into the real home merely to test the scripts. Use temporary
locations:

```bash
test_root=$(mktemp -d)
mkdir -p "$test_root/home"
HOME="$test_root/home" XDG_DATA_HOME="$test_root/data" \
  SPEAKTEXT_SKIP_EXTENSION_ENABLE=1 \
  ./scripts/install-user.sh
HOME="$test_root/home" XDG_DATA_HOME="$test_root/data" \
  SPEAKTEXT_SKIP_EXTENSION_ENABLE=1 \
  ./scripts/uninstall-user.sh
```

Skipping extension enablement is required for this isolated check because the
test installation is not visible to the live GNOME Shell. Verify the installed
extension interactively in the target session using
[acceptance-testing.md](acceptance-testing.md).

When the installer inherits a Snap-private `XDG_DATA_HOME`, such as from a
Snap-packaged editor terminal, it uses the host user's `~/.local/share`
instead. Other explicit `XDG_DATA_HOME` values are preserved.

The uninstaller intentionally retains model, configuration, and state data.

## Change checklist

- Add or update tests for behaviour changes.
- Build the native worker after C++ or CMake changes.
- Run the acceptance checklist after portal, shortcut, audio, clipboard, or
  insertion changes.
- Check that new diagnostics cannot contain PCM or transcript content.
- Update architecture and privacy documentation when interfaces, permissions,
  paths, or persistence change.
