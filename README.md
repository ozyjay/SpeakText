# SpeakText

SpeakText is private, local speech-to-text dictation for Fedora 44 Workstation
on GNOME Wayland. Hold the configured global shortcut, speak, then release it;
SpeakText transcribes with a local Whisper model and inserts the result at the
currently focused cursor. A GNOME top-bar indicator shows whether SpeakText is
ready, recording, transcribing, inserting, or needs attention.

No audio or transcript is written to disk, sent over the network, included in
diagnostic logs, or retained after successful insertion. The only runtime
network request is the first model download.

## Platform and behaviour

- Fedora 44 Workstation, GNOME 50, and Wayland only.
- English dictation up to two minutes using `ggml-base.en.bin`.
- `CTRL+ALT+space` is requested as the default push-to-talk shortcut. GNOME's
  portal dialog owns the final binding.
- A settings switch provides press-once/start, press-again/stop fallback if a
  compositor fails to report shortcut release.
- Keyboard input opens an XDG Remote Desktop session on demand, with
  keyboard-only access, just before insertion and closes it immediately
  afterwards. No screen or pointer access is requested.
- If keyboard access is unavailable, SpeakText copies the transcript and shows
  a notification. A partial insertion is never retried automatically.
- The application window and top-bar menu can cancel an active recording,
  immediately discarding its in-memory audio without transcription.
- The top-bar menu can also open the settings window, copy recoverable text,
  and quit SpeakText. It never receives audio or transcript text.
- Wayland does not expose the original focused application. Text goes to the
  cursor focused when transcription finishes.

## Build

The build and maintenance scripts and Make targets use PowerShell 7 (`pwsh`).
The installed entry point runs directly under Python so desktop portals can
identify the application process. The current Fedora 44 Workstation image
normally contains most other dependencies. Check without changing the system:

```powershell
./scripts/bootstrap.ps1 -Check
```

If anything is missing, the script prints a suggested `dnf` command but never
runs `sudo`. Once dependencies are available, build the CPU-only native worker:

```powershell
./scripts/bootstrap.ps1
```

This fetches the pinned `whisper.cpp` 1.9.1 source during the first build. Run
the development copy with:

```powershell
make run
```

The first run downloads and verifies the approximately 142 MiB English model.
GNOME then asks you to approve the global shortcut. The first completed
dictation asks for keyboard-only remote control when its text is ready to
insert. Denying keyboard control leaves clipboard fallback available.

## User-local installation

Install beneath `~/.local` without root access:

```powershell
make install-user
```

The installer also adds and enables the `speaktext@local` GNOME Shell
extension. When run from a Snap-packaged terminal or editor, it avoids that
Snap's private data directory and installs into the host user's
`~/.local/share`. Launches from a Snap terminal are delegated to host D-Bus
activation so desktop portals receive the `local.SpeakText` application ID. If
GNOME has not seen a newly installed extension yet, log out and back in, then
run:

```powershell
gnome-extensions enable speaktext@local
```

Use the microphone icon in the top bar to open the settings window, copy a
recoverable transcript, or quit. You can also launch **SpeakText** from the
GNOME application grid or run `~/.local/bin/speaktext`. Closing the window
keeps dictation running.

To remove executables and desktop metadata while retaining the downloaded
model and settings:

```powershell
make uninstall-user
```

Retained data can be removed manually from:

- `$env:XDG_DATA_HOME/speaktext` (default: `~/.local/share/speaktext`)
- `$env:XDG_CONFIG_HOME/speaktext` (default: `~/.config/speaktext`)
- `$env:XDG_STATE_HOME/speaktext` (default: `~/.local/state/speaktext`)

## Testing

Run the dependency-free Python suite:

```powershell
make test
```

The tests use fake audio, portal, clipboard, and worker implementations, so
they do not request desktop permissions or access the microphone. After the
native worker and model are available, run the manual acceptance checklist in
[`docs/acceptance-testing.md`](docs/acceptance-testing.md).

## Architecture

- `AudioCapture` streams raw 16 kHz mono signed-16 PCM from `pw-record` into
  memory.
- `TranscriptionWorker` owns a persistent C++ process with the model loaded
  once and communicates through a length-prefixed pipe protocol.
- `GlobalShortcutPortal` owns the persistent shortcut session;
  `KeyboardPortal` isolates each short-lived insertion session.
- `TextInjector` preflights the entire transcript through `libxkbcommon` before
  sending keysyms.
- `DictationCoordinator` exclusively owns the application state machine.
- A small GNOME Shell extension renders the top-bar indicator and talks to the
  application over a content-free local D-Bus control interface.

Diagnostic logs are stored under `$XDG_STATE_HOME/speaktext` and contain state,
timing, and error metadata only.

## Documentation

See the [documentation index](docs/README.md) for detailed architecture,
development, privacy, troubleshooting, and acceptance-testing guidance.
