# Spyrath Studio v1 Beta Release

Milestone 13 freezes the core architecture and establishes the commercial beta boundary.

## Beta capabilities

- Authenticated accounts and tenant-isolated projects
- Durable project/checkpoint/runtime state
- Chatterbox narration, 30-second audio preparation, SadTalker presenter production, FFmpeg H.264/AAC export
- Resume/retry after interruption
- Durable beta usage ledger and plan limits
- Health/readiness endpoints and container deployment
- Presenter/voice/final-video preview and download

## Beta plan

The built-in `beta` plan allows 10 projects and 50 production starts per UTC calendar month. These are safety/cost guardrails, not final public pricing. Payment processing is intentionally adapter-ready but not coupled to a payment vendor in v1 beta.

## Required release gate

Do not label a deployment production-ready until a real GPU environment passes one complete smoke path using the deployed dependencies: Chatterbox voice generation -> audio chunk -> patched SadTalker presenter generation -> FFmpeg final export. Unit tests validate orchestration and adapters but do not substitute for that GPU/model integration test.

## Production checklist

1. Deploy with Python 3.11, persistent `/data`, FFmpeg/ffprobe, NVIDIA runtime, SadTalker checkout/checkpoints, and Chatterbox dependencies.
2. Set `SPYRATH_AUTH_ENABLED=1` and a strong `SPYRATH_BOOTSTRAP_API_KEY`; never commit the key.
3. Set `SPYRATH_REQUIRE_GPU=1` and verify `/api/ready` before accepting production jobs.
4. Run `python -m pytest` and the real GPU smoke test.
5. Back up project media, `studio.db`, `usage.db`, project state, and runtime job ledger.
6. Start with a small invite-only beta and use usage/error data to drive post-v1 work.

## Post-beta, not M13

Public pricing, payment-provider integration, self-service subscription changes, distributed GPU queues, cancellation, subtitles/templates, and direct YouTube publishing are intentionally deferred until beta feedback justifies them.
