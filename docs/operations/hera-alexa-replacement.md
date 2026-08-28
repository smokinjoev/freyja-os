# Hera Alexa Replacement

Hera should behave like a household voice appliance while Freyja/Atlas remains
the authority. Hera captures local speech, transcribes it, sends a voice request
to Freyja, and speaks the returned `spoken` text.

## Target Loop

```text
wake word -> record utterance -> speech-to-text -> POST /shortcuts/message
          -> Freyja canonical routing -> spoken response -> text-to-speech
```

Hera must not make independent privileged decisions. Calendar writes, Home
Assistant changes, messages, and other mutations still go through the normal
approval gates.

Hera's home placement is Atlanta. Treat it as the household IoT/logging edge:
local sensors and voice activity become typed semantic events sent to Atlas, and
Atlas remains the durable log, audit, memory, schedule, and control authority.

## Minimum Useful Version

For Dragon Con, the useful version is a push-to-talk or wake-word voice loop
that supports:

- quick questions
- family calendar reads
- weather
- Home Assistant reads
- approval-safe calendar creation prompts
- short spoken responses

Camera perception remains separate. If no camera exists, keep
`freyja3-hera-semantic-publisher.timer` running and keep publishing semantic
no-camera status events.

## Hera Service Contract

Hera should call the same endpoint as HomePod Shortcuts:

```text
POST http://100.119.235.114:8300/shortcuts/message
```

Payload:

```json
{
  "prompt": "<transcribed speech>",
  "conversation_id": "hera-kitchen",
  "sender": "hera",
  "tools_required": true
}
```

Response:

```json
{
  "spoken": "<voice-safe response text>"
}
```

Hera speaks only `spoken`.

## Implementation Choices

Recommended first pass:

- Wake word: existing Hera wake service if active, otherwise push-to-talk
- Speech-to-text: local Whisper-compatible transcription
- Text-to-speech: Piper, system TTS, or the existing Hera avatar voice stack
- Transport: HTTP POST to Freyja 3 `/shortcuts/message`
- Logs: transcript length, status code, latency, no raw audio by default
- IoT/logging: Atlanta-local sensor observations only as typed semantic events;
  no raw continuous audio/video logs by default

## Smoke Tests

1. Health: Hera can reach Freyja 3 `/health`.
2. Text ingress: Hera can POST a typed test prompt to `/shortcuts/message`.
3. STT: Hera can transcribe a short local utterance.
4. TTS: Hera can speak a fixed phrase.
5. Full loop: say “Freyja, what time is it?” and hear a short answer.
6. Calendar read: ask “What is on the family calendar today?”
7. Calendar write: ask to add an event and verify Freyja asks for confirmation.
8. Safety: unclear speech produces a clarification instead of an action.

## Done Criteria

Hera is an Alexa replacement when a family member can speak naturally in the
room, receive a short response, and trigger Freyja workflows without bypassing
identity, privacy, or approval controls.
