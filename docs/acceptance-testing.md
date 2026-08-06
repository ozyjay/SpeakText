# Fedora 44 acceptance testing

Run these checks in a GNOME Wayland session after building SpeakText. Portal
tests deliberately require visible user approval and should not be automated
in an unattended session.

1. Start `make run`; confirm model download progress and its checksum check.
2. Approve the `CTRL+ALT+space` global shortcut and keyboard-only remote-control
   request. Confirm that no screen or pointer sharing is requested.
3. In GNOME Text Editor, Firefox, VS Code, and Ptyxis, place the cursor in an
   editable area, hold the shortcut, speak for five to ten seconds, release it,
   and confirm insertion at the current cursor.
4. Dictate punctuation and Unicode words such as “café”; confirm correct text
   and that newline handling produces an Enter key event.
5. Change focus immediately after release; confirm insertion follows the newly
   focused cursor as documented.
6. Revoke remote-control permission and dictate again; confirm the transcript
   is copied and a notification explains the fallback.
7. Disconnect or mute the microphone, dictate silence, rapidly repeat the
   shortcut, and quit during recording and transcription. Confirm recovery with
   no crash or stale recording.
8. Hold the shortcut for two minutes; confirm automatic stop and transcription.
9. Restart SpeakText; confirm the restored permission does not require screen
   capture and the single-use restore token is refreshed.
10. Search `$XDG_CONFIG_HOME`, `$XDG_STATE_HOME`, and `/tmp` for distinctive
    dictated words. Confirm that neither transcripts nor PCM data were written.

For a warm model on the target CPU, recording should begin within 300 ms and a
ten-second sample should be inserted within five seconds of release.

