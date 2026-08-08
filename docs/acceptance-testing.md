# Fedora 44 acceptance testing

Run these checks in a GNOME Wayland session after building SpeakText. Portal
tests deliberately require visible user approval and should not be automated
in an unattended session.

1. Install with `make install-user`, then log out and back in so IBus loads the
   user-local SpeakText component. Confirm a microphone icon appears in the
   GNOME top bar and its menu can open the settings window.
2. Start SpeakText from the top-bar menu; confirm startup identifies whether it
   is checking the local model, downloading it with byte progress, or loading
   speech recognition. The checking and loading stages show an active progress
   bar; the first model load can take up to 90 seconds.
3. While SpeakText is running, add **SpeakText** as an input source in GNOME
   Settings and select it. Confirm no Global Shortcuts or Remote Desktop prompt
   and no orange remote-access indicator appears.
4. Confirm the top-bar icon and status text follow Ready, Recording,
   Transcribing, Inserting, and Error states without routine desktop
   notifications.
5. In GNOME Text Editor, Firefox, VS Code, and Ptyxis, place the cursor in an
   editable area, rapidly tap either Shift key twice, speak for five to ten
   seconds, double-tap Shift again, and confirm insertion at the current cursor.
6. Start a recording, choose **Cancel recording** from the top-bar menu, and
   confirm immediate return to Ready with no transcription, insertion, or
   clipboard change. Repeat with the button in the SpeakText window, then start
   another recording and tap Shift once. Confirm cancellation occurs only after
   the short double-tap window expires.
7. Dictate punctuation, a newline, and Unicode words such as “café”; confirm the
   committed text is correct.
8. Change focus while recording; confirm the recording is cancelled. Finish a
   new recording, then change focus during transcription; confirm insertion
   follows the newly focused IBus context as documented.
9. Switch away from the SpeakText input source, double-tap Shift, and confirm
   recording does not start. Finish a recording in an editable context, then
   deactivate the SpeakText input source before transcription finishes;
   confirm the transcript is copied and a notification explains the fallback.
   Confirm **Copy last transcript** works from the top-bar menu without
   displaying it.
10. Disconnect or mute the microphone, dictate silence, rapidly repeat the
   gesture, and quit during recording and transcription. Confirm recovery with
   no crash or stale recording.
11. Leave a recording active for two minutes; confirm automatic stop and
    transcription.
12. Restart SpeakText and dictate again; confirm IBus insertion remains
    available without a Remote Desktop prompt.
13. Search `$XDG_CONFIG_HOME`, `$XDG_STATE_HOME`, and `/tmp` for distinctive
    dictated words. Confirm that neither transcripts nor PCM data were written.

For a warm model on the target CPU, recording should begin within 300 ms and a
ten-second sample should be inserted within five seconds of release.
