# HomePod Shortcuts To Freyja

Use this path for Apple HomePod voice entry without exposing the Director on the
LAN. HomePod invokes a Siri Shortcut on the family member's iPhone, the Shortcut
sends an iMessage to Freyja, and the existing native iMessage connector forwards
authorized messages to the Director.

## Shortcut

Create this shortcut in Apple Shortcuts on the iPhone that owns the HomePod Siri
request. iCloud Shortcuts will propagate it to the rest of the Apple account.

Name:

```text
Tell Freyja
```

Siri phrases:

```text
Hey Siri, Tell Freyja
Hey Siri, Tell Freyja <message>
```

Actions:

1. `Ask for Input`
   - Prompt: `What should I tell Freyja?`
   - Input Type: `Text`
   - Allow Multiple Lines: off
2. `Send Message`
   - Message: `Provided Input`
   - Recipients: the Freyja iMessage contact
   - Show When Run: off

Expected behavior:

- Saying `Hey Siri, Tell Freyja` prompts for the message.
- Saying `Hey Siri, Tell Freyja what can you see in Home Assistant?` sends the
  spoken request directly.
- Freyja replies in Messages after the native iMessage connector routes the
  request through `/route`.

## Freyja-Side Requirements

- The native iMessage connector LaunchAgent must be loaded and running.
- `IMESSAGE_ENABLED` must be true in the runtime `.env`.
- `IMESSAGE_ALLOWED_SENDERS` must include the iMessage identity that the
  HomePod/iPhone will send from.
- `FREYJA_DIRECTOR_URL` and `FREYJA_CONNECTOR_TOKEN` must be configured in the
  runtime `.env`.

Validate the local side with:

```bash
scripts/verify-homepod-shortcut-path.sh
```

## Notes

- Do not point HomePod Shortcuts directly at `http://127.0.0.1:8000/route`;
  that address is only local to the device running the Shortcut.
- Do not expose the Director on the LAN just for HomePod. Use the iMessage
  connector as the Apple-native authenticated path.
- Home Assistant safety policy is unchanged: voice entry can ask about Home
  Assistant, but it does not grant new control authority.
