# SpeakText

SpeakText is private, local speech-to-text dictation for Fedora 44 Workstation
on GNOME Wayland. Select its IBus input source and rapidly tap either Shift key
twice to start recording; double-tap again to transcribe and insert. A GNOME
top-bar indicator shows whether SpeakText is
ready, recording, transcribing, inserting, or needs attention.

No audio or transcript is written to disk, sent over the network, included in
diagnostic logs, or retained after successful insertion. The only runtime
network request is the first model download.

## Platform and behaviour

- Fedora 44 Workstation, GNOME 50, and Wayland only.
- Electron applications must use their native Wayland backend; applications
  running through XWayland are not supported.
- English dictation up to two minutes using `ggml-base.en.bin`.
- Rapidly double-tap either Shift key to start recording, then double-tap again
  to finish and transcribe.
- Tap either Shift key once while recording to cancel after the short
  double-tap window, discarding the recording immediately.
- The gesture is available only while SpeakText is the selected IBus input
  source in an editable context, so it cannot start recording elsewhere.
- Completed transcripts are committed through the local IBus input method;
  SpeakText does not request Remote Desktop, screen, pointer, or synthetic
  keyboard access.
- If the SpeakText input method is inactive, SpeakText copies the transcript
  and shows a notification.
- The application window and top-bar menu can cancel an active recording,
  immediately discarding its in-memory audio without transcription.
- The application window includes an optional **Test dictation** control for a
  short microphone check. Its recognised text is shown only in the window; it
  is never inserted into another application.
- The top-bar menu can also open the settings window, copy recoverable text,
  and quit SpeakText. It never receives audio or transcript text.
- Wayland does not expose the original focused application. Text goes to the
  cursor focused when transcription finishes.

## Build

The build and maintenance scripts and Make targets use PowerShell 7 (`pwsh`).
The installed entry point runs directly under Python. The current Fedora 44
Workstation image normally contains most other dependencies. Check without
changing the system:

```powershell
./scripts/bootstrap.ps1 -Check
```

If anything is missing, the script prints a suggested `dnf` command but never
runs `sudo`. Once dependencies are available, build the CPU-only native worker:

```powershell
./scripts/bootstrap.ps1
```

This fetches the pinned `whisper.cpp` 1.9.1 source during the first build. Run
the development checkout with:

```powershell
make run
```

This is intentionally separate from the application launched by the top-bar
indicator. After installation, test that exact build with:

```powershell
make run-installed
```

Quit any existing SpeakText instance first. The command verifies this, then
prints the installed build identity before it launches the application.

The first run downloads and verifies the approximately 142 MiB English model.
The user installer adds **SpeakText** to GNOME's existing input sources without
removing any keyboard layouts. Select it from GNOME's input-source menu to
enable the Shift gesture and native text insertion.

SpeakText registers its IBus engine while the application is running, so it is
not shown by `ibus list-engine`. After starting SpeakText, select it from
GNOME's input-source menu or activate it directly:

```bash
ibus engine speaktext
```

To check the currently active engine, run `ibus engine`; it should print
`speaktext` before testing the Shift gesture.

The VS Code Snap currently appends `--ozone-platform=x11` in its launcher, so
command-line Wayland flags cannot override it. Use a Fedora-installed VS Code
package that can run on native Wayland, and quit every existing VS Code process
before changing its launch flags or backend. Microsoft documents its Fedora
repository and automatic DNF updates in the
[VS Code Linux setup guide](https://code.visualstudio.com/docs/setup/linux).

## User-local installation

Install beneath `~/.local` without root access:

```powershell
make install-user
```

The installer also adds and enables the `speaktext@local` GNOME Shell
extension and adds **SpeakText** to GNOME's input sources. When run
from a Snap-packaged terminal or editor, the installer avoids that
Snap's private data directory and installs into the host user's
`~/.local/share`. Launches from a Snap terminal are delegated to host D-Bus
activation. If
GNOME has not seen a newly installed extension yet, log out and back in, then
run:

```powershell
gnome-extensions enable speaktext@local
```

If automatic input-source setup fails, first inspect the current list:

```bash
gsettings get org.gnome.desktop.input-sources sources
```

Then retain those entries and append `('ibus', 'speaktext')`. For example, an
Australian English configuration is:

```bash
gsettings set org.gnome.desktop.input-sources sources \
  "[('xkb', 'au'), ('ibus', 'speaktext')]"
```

Use the microphone icon in the top bar to open the settings window, copy a
recoverable transcript, or quit. You can also launch **SpeakText** from the
GNOME application grid or run `~/.local/bin/speaktext`. Closing the window
keeps dictation running. The window's **Diagnostics → Build** row identifies
whether the running application is the development checkout or an installed
build revision. Use **Test dictation** to check a short spoken sample without
inserting it at the current cursor; clear the visible result when finished.

To remove executables and desktop metadata while retaining the downloaded
model and settings:

```powershell
make uninstall-user
```

Retained data can be removed manually from:

- `$env:XDG_DATA_HOME/speaktext` (default: `~/.local/share/speaktext`)
- `$env:XDG_CONFIG_HOME/speaktext` (default: `~/.config/speaktext`; legacy
  shortcut settings from earlier versions only)
- `$env:XDG_STATE_HOME/speaktext` (default: `~/.local/state/speaktext`)

## Testing

Run the dependency-free Python suite:

```powershell
make test
```

The tests use fake audio, IBus, clipboard, and worker implementations, so
they do not request desktop permissions or access the microphone. After the
native worker and model are available, run the manual acceptance checklist in
[`docs/acceptance-testing.md`](docs/acceptance-testing.md).

## Architecture

- `AudioCapture` streams raw 16 kHz mono signed-16 PCM from `pw-record` into
  memory.
- `TranscriptionWorker` owns a persistent C++ process with the model loaded
  once and communicates through a length-prefixed pipe protocol.
- The IBus engine recognises the Shift gestures only in an active text context
  and otherwise passes all keyboard events through unchanged.
- `IBusTextInjector` commits the completed transcript to that text context.
- `DictationCoordinator` exclusively owns the application state machine.
- A small GNOME Shell extension renders the top-bar indicator and talks to the
  application over a content-free local D-Bus control interface.

Diagnostic logs are stored under `$XDG_STATE_HOME/speaktext` and contain state,
timing, and error metadata only.

## Documentation

See the [documentation index](docs/README.md) for detailed architecture,
development, privacy, troubleshooting, and acceptance-testing guidance.
