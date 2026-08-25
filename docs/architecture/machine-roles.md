# Machine Roles

## Atlas

Atlas is the always-on Freyja control plane. It owns Director, identity,
memory, policy, tool authorization, connector coordination, health, monitoring,
and persistent backend service placement.

## Vulcan

Vulcan is the inference layer. It should expose network-reachable local model
runtime endpoints over the private network. Atlas references logical profiles:
`MODEL_FAST`, `MODEL_REASON`, `MODEL_CODE`, and `MODEL_VISION`.

## Iris

Iris is the Apple bridge. It owns native iMessage, Apple Calendar, Contacts,
Shortcuts, and other macOS-only capabilities. Iris-originating messages that
need intelligence must enter Atlas Director and reach Vulcan.

## Hera

Hera is a household voice/avatar/interface node. Hera must use canonical
Freyja ingress and egress rather than embedding another assistant stack.

## Cloyd

Cloyd is Joe's personal-agent identity. The Raspberry Pi is an edge-automation
role and must not be conflated with the Cloyd persona.
