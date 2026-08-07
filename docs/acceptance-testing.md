# Fedora 44 acceptance testing

Run these checks in a GNOME Wayland session after building SpeakText. Portal
tests deliberately require visible user approval and should not be automated
in an unattended session.

1. Install with `make install-user`, then log out and back in if requested.
   Confirm a microphone icon appears in the GNOME top bar and its menu can open
   the settings window.
2. Start SpeakText from the top-bar menu; confirm model download progress and
   its checksum check.
3. Approve the `CTRL+ALT+space` dictation and `CTRL+ALT+x` cancellation global
   shortcuts. Complete the first dictation, then approve the keyboard-only
   remote-control request when insertion begins. Confirm that no screen or
   pointer sharing is requested.
4. Confirm the top-bar icon and status text follow Ready, Recording,
   Transcribing, Inserting, and Error states without routine desktop
   notifications.
5. In GNOME Text Editor, Firefox, VS Code, and Ptyxis, place the cursor in an
   editable area, hold the shortcut, speak for five to ten seconds, release it,
   and confirm insertion at the current cursor. Confirm GNOME's orange
   remote-access indicator appears only around insertion and clears after its
   minimum display period rather than remaining for the application lifetime.
6. Start a recording, choose **Cancel recording** from the top-bar menu, and
   confirm immediate return to Ready with no transcription, insertion, or
   clipboard change. Repeat with the button in the SpeakText window, then with
   the cancellation shortcut while still holding push-to-talk.
7. Dictate punctuation and Unicode words such as “café”; confirm correct text
   and that newline handling produces an Enter key event.
8. Change focus immediately after release; confirm insertion follows the newly
   focused cursor as documented.
9. Revoke remote-control permission and dictate again; confirm the transcript
   is copied and a notification explains the fallback. Confirm **Copy last
   transcript** works from the top-bar menu without displaying the text there.
10. Disconnect or mute the microphone, dictate silence, rapidly repeat the
   shortcut, and quit during recording and transcription. Confirm recovery with
   no crash or stale recording.
11. Hold the shortcut for two minutes; confirm automatic stop and transcription.
12. Restart SpeakText and dictate again; confirm the on-demand session restores
    permission without screen capture, refreshes the single-use token, and
    closes after insertion.
13. Search `$XDG_CONFIG_HOME`, `$XDG_STATE_HOME`, and `/tmp` for distinctive
    dictated words. Confirm that neither transcripts nor PCM data were written.

For a warm model on the target CPU, recording should begin within 300 ms and a
ten-second sample should be inserted within five seconds of release.
