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

## Shift gesture does not activate

- Confirm **SpeakText** appears under GNOME Settings → Keyboard → Input
  Sources. If it is absent after `make install-user`, log out and back in so
  IBus reloads the installed component descriptor.
- Reopen SpeakText and use **Retry setup**.
- Start SpeakText before opening GNOME Settings, add **SpeakText** under
  Keyboard → Input Sources, and select it.
- Focus an editable text control. The engine deliberately receives no gesture
  outside an active IBus text context.
- Tap Shift twice within about 350 ms. Double-tap again to finish, or tap once
  while recording to cancel.

## Text is copied instead of inserted

Select **SpeakText** in GNOME's input-source menu and keep an editable field
focused until transcription finishes. Clipboard fallback is expected if that
IBus context disappears after recording starts.

## Text appears in the wrong application

This is expected if focus changes during transcription. Wayland does not allow
SpeakText to inspect or restore the original target. Keep the intended cursor
focused until insertion completes.

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
