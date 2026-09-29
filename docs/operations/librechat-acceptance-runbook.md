# LibreChat Agent Acceptance Runbook

Use this after signing in to LibreChat at `http://100.119.235.114:3080/`.
Record only pass/fail, agent, time, and trace ID. Do not record private chat
content, passwords, tokens, or personal data.

## Preconditions

1. From Vulcan or another VPN-connected machine, run:

   ```sh
   python3 scripts/freyja-live-readiness.py
   ```

2. Confirm the named agent selector shows Freyja, Cloyd, Benedict, Agent 47,
   and JennaCide.
3. Use a new conversation for every agent. Do not use a generic model chat.

## No-write check for every agent

For each agent, send:

> State your name and role in one sentence. Do not use tools and do not save
> anything to memory.

Pass only when the response is written prose, identifies the selected agent,
and does not expose an internal tool trace.

Then request one safe Core action appropriate to that agent, for example:

| Agent | Safe request |
| --- | --- |
| Freyja | `Use your tools to report whether Core is healthy. Do not change anything.` |
| Cloyd | `Use your tools to report whether OpenCode is available. Do not start or change a session.` |
| Benedict | `Use a read-only tool to report the current local date. Do not save memory.` |
| Agent 47 | `Use a read-only tool to inspect whether OpenCode is available. Do not start a coding task.` |
| JennaCide | `Use a read-only tool to report whether Core is healthy. Do not save memory.` |

Pass only when the displayed tool activity is attributed to the selected agent,
the written answer follows, and no consequential action is taken.

## Agent 47 bounded OpenCode handoff

In a new Agent 47 conversation, send:

> Check whether OpenCode is available and report its status. Do not start a
> session, run shell commands, edit files, or create a task.

Pass only when Agent 47 returns a written, read-only status. A later coding
handoff must be explicitly approved and should use an isolated worktree.

## Memory-boundary evidence

The no-write checks above establish the agent selection and tool path. They do
not prove durable-memory isolation on their own.

To prove isolation requires a deliberate controlled-memory marker. Because
that writes durable data, get the operator's explicit approval first. Use a
non-sensitive random marker, verify it is recalled only by the same agent, and
then remove it through the approved memory-management path. Do not use a real
name, address, credential, or household fact as the marker.

## Record the outcome

Update `docs/operations/freyja-live-acceptance.md` after the run. A production
baseline is not eligible until all five no-write/tool checks, the Agent 47
status check, and the separately approved memory-boundary check are recorded.
