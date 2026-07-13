# Troubleshooting / FAQ

Common "why doesn't this work?" moments, each as *symptom → cause → fix*. If yours isn't here, the event log usually has the answer — `dcp show <id> --timeline` prints every control decision and
oversight verdict.

## The hello-world produces no messages / `turns: 0`

**Symptom.** A real-model run ends immediately: `status: stopped` (or `done`) with `turns: 0` and an empty transcript.

**Cause.** In `plan` mode the orchestrator's model is asked to pick the next speaker; if it isn't given the goal and the roster of roles, it has nothing to act on and stops. (This was a real bug — fixed by putting the goal, roles, and brief into the plan prompt.)

**Fix.** Make sure the instance has a `goal` (or the template does) and the roles are cast. 
On a current build the plan prompt already carries goal + roles + brief; if you wrote a **custom** `ControlPolicy`, ensure your `decide` reads `ctx.goal` / `ctx.roles` and returns a `select_speaker` for a role that has a participant.

## A provider shows "not configured"

**Symptom.** `dcp info` (or `server_info()`) lists a provider as *not configured*, or `server.run` raises that the provider has no key.

**Cause.** `configured` means a usable credential/endpoint is present:

- `openai` / `anthropic` → the API key env var (`OPENAI_API_KEY` / `ANTHROPIC_API_KEY`).
- `local` → `DCP_BASE_URL` (or `ModelBinding.base_url`) pointing at an OpenAI-compatible server.
- `transformers` → the extra installed (`pip install -e "./sdk[transformers]"`).
- `mock` → always configured.

**Fix.** Set the relevant variable, or switch `DCP_MODEL_PROVIDER` to one that is configured (e.g. `mock` for a key-free run). 
`dcp info` doubles as the config check.

## `.env` isn't taking effect

**Symptom.** You filled in `.env` but the run still can't find a key/model.

**Cause.** `load_dotenv()` reads `.env` from the **current working directory**. If your keys are in `sdk/.env` but you run from the repo root, they aren't found.

**Fix.** Run from the directory that holds your `.env`, or copy `sdk/.env` to a `.env` beside your script, or export the variables in your shell. (Never commit `.env` — it holds secrets.)

## The model returns a role's name, not its `role_id`

**Symptom.** `OrchestrationError: select_speaker for unknown role 'Proposer'` (the model returned the display name `Proposer` instead of the id `proposer`).

**Cause.** Plan-mode models occasionally return a role's name or a case variant.

**Fix.** Current builds tolerate this — `_resolve_role` matches exact id → case-insensitive id → name. If you're on an older build, upgrade, or give roles ids and names that don't invite the confusion. A *truly* unknown role still raises (that's a real bug, not a slip).

## OpenAI "trailing characters" / invalid-JSON crash

**Symptom.** `ProviderError: openai structured call failed … Invalid JSON: trailing characters`.

**Cause.** Some models emit a valid JSON object followed by extra prose; the strict parser rejects the whole string.

**Fix.** Current builds salvage the leading JSON object and retry a bounded number of times, so a single bad emission doesn't abort the dialogue. If you see it persist, the model may be returning non-JSON entirely — check the model id and that structured output is supported.

## `status: done` but `turn: 0` — is that wrong?

Not necessarily. `done` means the termination condition was satisfied with no open gate. 
If your policy or model decides the goal is already met before anyone speaks, a 0-turn `done` is legitimate.
For the hello-world specifically, though, a 0-turn result usually means the "no messages" issue above — check that the goal and roles reached the orchestrator.

## How do I switch between mock / local / remote providers?

- **Mock** (key-free): pass `MockProvider(...)` as `orchestrator_provider` / in `agent_providers`,
  or set `DCP_MODEL_PROVIDER=mock`.
- **Local open-weights**: `DCP_MODEL_PROVIDER=local` + `DCP_BASE_URL=http://localhost:11434/v1` (a
  server), or `DCP_MODEL_PROVIDER=transformers` + `DCP_MODEL=Qwen/Qwen3-4B` (in-process).
- **Remote component agent**: resolve + `connect` the component and drop it into `agent_providers`.

Per-agent, set `Participant.model_binding=ModelBinding(provider=…, model=…)`. Precedence: `agent_providers` > `model_binding` > env default. See
[05 · Participant](05-participant.md#provider-taxonomy).

## Can one dialogue mix providers (Claude + GPT + local)?

Yes. Resolution is per-agent, so a Claude proposer and a GPT critic and a local summarizer coexist in one run. Mixing `openai` + `anthropic` just means **both** keys must be in the environment.

## How do I see what happened — the event log / replay?

- Code: `restore(store, instance_id)` (or `reg.get_instance(id)`) returns the fully replayed `DialogueInstance` — inspect `.messages` and `.events`.
- CLI: `dcp show <instance_id> --db <url>` prints the transcript; add `--timeline` to interleave the control decisions and oversight verdicts.
- Over HTTP: `GET /instances/{id}` (full replay) or `GET /instances/{id}/events` (SSE: replay then tail). See [06 · Hosting & Delivery](06-hosting-delivery.md).

## A custom orchestrator/oversight isn't being used

**Symptom.** You passed `control_policy=` / `oversight=` but behavior is unchanged.

**Cause / fix.** A custom policy passed to `Server.run(...)` / `Orchestrator(...)` **wins** over the template's mode. Make sure you passed it to the *run* (not just constructed it), and that your object matches the protocol (`async decide(ctx)` for control; `pre`/`post` for oversight). See [04 · Orchestrator](04-orchestrator.md).

---

[All docs](README.md)
