# Vulcan Local Coder Plan

## Current green baseline

Atlas Director exposes and verifies Vulcan through:

- `GET /endpoints`
- `GET /vulcan/health`
- `GET /vulcan-coder/health`
- `GET /vision/health`
- `POST /vision/extract`

Vulcan standard lanes:

- `8088`: Qwen3-30B-A3B general lane
- `8090`: Qwen3-Coder-30B-A3B-Instruct coder lane
- `8091`: Qwen2.5-VL-7B vision/document lane
- `1233`: LM Studio wake service
- `1234`: LM Studio wake-on-query proxy
- `1235`: LM Studio backend, local-only on Vulcan

The Atlas endpoint inventory repair is committed as `ffa35d3` on branch `feature/cloyd-upstream-features`.

## Problem statement

The current Windows setup can serve multiple local inference lanes, but it is not the right final foundation for a mission-critical coding agent. Windows Scheduled Tasks using an interactive user token are sensitive to login/session state. We repaired the startup triggers with explicit boot and `VULCAN\Freyja` logon triggers, but a dedicated coder should not depend on a desktop session.

## Path 1: Linux dual boot / dedicated inference host

Goal: make Vulcan, or a successor node, a service-native local inference host.

Validation gates:

1. Boot Linux and confirm hardware identity, RAM, GPU, and driver stack.
2. Confirm whether the AMD unified memory setup can expose enough usable GPU/shared memory for large models.
3. Build or install llama.cpp with Vulkan and, if viable, ROCm/HIP.
4. Run a model-loading matrix: 30B coder, Qwen3-Coder-Next Q4, then 120B-class GPT model only if memory allows.
5. Install the winning coder as a `systemd` service with restart policy, logs, and health checks.
6. Point Atlas `VULCAN_CODER_BASE_URL` at the Linux service.

Recommended target if Linux memory support is strong:

- Start with Qwen3-Coder-Next Q4_K_M.
- Move to a 120B GPT/coder-class model only after proving memory headroom and acceptable tokens/sec.

Why this is preferred:

- `systemd` is better than interactive Windows Scheduled Tasks for always-on inference.
- Logs, restart behavior, and network binding are cleaner.
- A single dedicated coder service is easier to reason about than several competing desktop-bound lanes.

## Path 2: Windows coder-exclusive mode

Goal: answer whether a larger local coder is smart enough before investing in Linux migration.

Control scripts on Vulcan:

- `C:\Freyja\inference\stop-vulcan-inference-lanes.ps1`
- `C:\Freyja\inference\start-vulcan-coder-exclusive-8090.ps1`
- `C:\Freyja\inference\start-vulcan-standard-lanes.ps1`

Wrappers:

- `C:\Freyja\inference\stop-vulcan-inference-lanes.cmd`
- `C:\Freyja\inference\start-vulcan-coder-exclusive-8090.cmd`
- `C:\Freyja\inference\start-vulcan-standard-lanes.cmd`

Current status:

- Standard lane restore works and was re-verified after an exclusive-mode stop/start test.
- Exclusive-mode successfully started the existing Qwen3-Coder-30B lane by itself on `8090`; the first validation wrapper hung on a PowerShell web health probe, so the script now treats the TCP listener as the readiness gate and leaves HTTP verification to the caller.
- The Qwen3-Coder-Next wrapper is staged at `C:\Freyja\inference\start-vulcan-coder-next-exclusive-8090.ps1`; it points at shard 1 and currently uses an `8192` context for safer first-load testing.
- Qwen3-Coder-Next Q4_K_M downloaded successfully with a resumable `curl.exe` Scheduled Task named `Freyja Download Qwen3 Coder Next Q4KM`; all four shards are present under `C:\Freyja\inference\models\qwen3-coder-next-q4km\Qwen3-Coder-Next-Q4_K_M`.
- Qwen3-Coder-Next has not been promoted. Initial Windows exclusive trials did not complete a healthy readiness plus chat-completion cycle. The standard Freyja lanes restored cleanly after each attempt, so the active safe local coder remains Qwen3-Coder-30B on `8090`.

Candidate model:

- `Qwen/Qwen3-Coder-Next-GGUF`, `Qwen3-Coder-Next-Q4_K_M`, 4 shards, about 48.4 GB total.
- This is an 80B-total / sparse-active coder model and is more practical on 64 GB RAM than a dense 70B Q4 model.

Test gate for Windows coder-exclusive mode:

1. Keep the standard Qwen3-Coder-30B lane as the active safe coder.
2. For further Qwen3-Coder-Next experiments, stop standard lanes with `C:\Freyja\inference\start-vulcan-coder-next-exclusive-8090.cmd`, which invokes PowerShell with execution-policy bypass.
3. Start only `8090` with Qwen3-Coder-Next shard 1 as the model path and `8192` context first.
4. Verify `GET http://100.87.242.99:8090/health`.
5. Verify `GET http://100.87.242.99:8090/v1/models`.
6. Run a small coding completion.
7. Run one real repo edit in a disposable branch/worktree.
8. Restore standard lanes.

Pass criteria:

- Loads without killing Windows or starving RAM.
- Produces materially better coding behavior than current Qwen3-Coder-30B.
- Survives at least one start/stop cycle.
- Atlas can point coder traffic at it cleanly.

Fail criteria:

- Cannot load with useful context.
- Too slow for interactive coding.
- Crashes under real repo prompts.
- Requires fragile manual desktop state.

## Current operational decision

Keep Vulcan on the standard multi-lane Windows stack for normal Freyja use. Qwen3-Coder-Next is downloaded but remains experimental because it has not passed the safe exclusive-mode readiness and chat test. Treat Windows coder-exclusive mode as a proving ground, not the final always-on architecture. Prioritize the Linux dual-boot/service-native path for the durable dedicated coder so the model runs under `systemd` instead of an interactive Windows session.

## Recommendation

Use Path 2 as a quick intelligence test, not as the permanent architecture. Use Path 1 for the durable local coder if the model quality justifies owning a big local lane.
