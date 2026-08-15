# Troubleshooting

## Dependency check fails

Run:

```powershell
./scripts/bootstrap.ps1 -Check
```

Install only the packages it reports, then rerun the check. The script prints a
suggested `dnf` command but never elevates privileges itself.

## Native build cannot fetch whisper.cpp

The first `make build` needs access to GitHub. Confirm DNS and HTTPS access, then
remove only the incomplete FetchContent directory under `build/_deps` if CMake
cannot recover. Do not remove the repository or model directories.

## Model download or checksum fails

- Confirm HTTPS access to Hugging Face.
- Check free space under `$XDG_DATA_HOME` or `~/.local/share`.
- Use **Retry setup** after connectivity is restored.
- Never bypass checksum validation. A `.part` download is removed after failure.

## Microphone capture fails

- Confirm `pw-record` is available with `Get-Command pw-record`.
- Check GNOME Settings → Privacy & Security → Microphone.
- Confirm the intended default input source in GNOME Settings → Sound.
- Run `pw-record --rate 16000 --channels 1 --format s16 --raw -` only during an
  attended diagnostic session; it emits binary audio to the terminal and must
  be stopped with `Ctrl+C`.

## Dictation gesture does not activate

- Confirm **SpeakText** appears in GNOME's top-bar input-source menu and select
  it. If it is absent after `make install-user`, log out and back in so IBus
  reloads the installed component descriptor.
- Startup normally activates the engine automatically. **Retry setup** is only
  needed after a setup error; use **Reactivate** when the application is ready
  but its input source is no longer selected.
- While SpeakText is running, use `ibus engine` to confirm the active engine is
  `speaktext`. If it is not, open the SpeakText window and choose
  **Reactivate** beside **Input source**, then run `ibus engine` again to
  confirm it now reports `speaktext`. Do not use `ibus list-engine` for this
  check; it omits engines registered by running applications. On some Wayland
  configurations, `ibus engine speaktext` changes the engine but exits with 1
  while attempting an unrelated legacy X11 keyboard-layout update; use the
  subsequent `ibus engine` output as the authoritative result.
- Check `gsettings get org.gnome.desktop.input-sources sources` for
  `('ibus', 'speaktext')`. If it is missing, rerun `make install-user` or use
  the manual `gsettings set` example in the README while retaining every
  existing keyboard-layout entry.
- Focus an editable text control. The engine deliberately receives no gesture
  outside an active IBus text context.
- Confirm the application window shows the intended Shift or Control gesture
  key. Tap that key twice within about 350 ms. Double-tap again to stop and
  review, then double-tap once more to commit; tap once while recording or
  reviewing to discard.

## Dictation gesture does not activate in VS Code

SpeakText supports native Wayland applications, not Electron applications
running through XWayland. Use a Fedora-installed VS Code package that supports
native Wayland.

Quit every VS Code process before testing a different package or backend.
Check the main process with `pgrep -a -f '/usr/share/code/code'`; it must not
show `--ozone-platform=x11`.

## Text is copied instead of inserted

Select **SpeakText** in GNOME's input-source menu and keep an editable field
focused until you confirm the preview. Clipboard fallback is expected only if
the IBus context becomes unavailable during a confirmed commit.

## Text appears in the wrong application

An uncommitted preview is deliberately discarded if its IBus context changes.
Wayland does not allow SpeakText to inspect or restore the original target.
Keep the intended cursor focused until you commit the preview.

## Insertion is incomplete

Use **Copy last transcript** and manually replace the partial text. SpeakText
does not automatically replay a partial insertion because that could duplicate
content.

## Application closes but dictation keeps running

Closing the window hides it by design. Launch SpeakText again to reopen the
single existing instance, then choose **Quit SpeakText** from the top-bar menu
to stop the worker and IBus service.

## Top-bar icon is missing

Check whether GNOME knows and has enabled the extension:

```powershell
gnome-extensions info speaktext@local
gnome-extensions enable speaktext@local
```

GNOME Shell may not discover an extension installed during the current
session. Log out and back in, then enable it again. On Wayland, do not try to
restart GNOME Shell with `Alt+F2` and `r`.

If the icon shows a disconnected state, choose **Start SpeakText** from its
menu. Confirm that `$XDG_DATA_HOME/dbus-1/services/local.SpeakText.service`
exists when D-Bus activation does not start the application.

## Diagnostics

Logs are stored at `$XDG_STATE_HOME/speaktext/speaktext.log`, falling back to
`~/.local/state/speaktext/speaktext.log`. They rotate automatically and must not
contain audio or transcript content.
