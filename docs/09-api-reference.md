# API Reference

The curated public surface of `dcp`. Everything here is importable from the top-level package (`from dcp import Server`) unless noted. Submodules (`dcp.schema`, `dcp.orchestration`, …) hold the full detail. 
Signatures are simplified; the Pydantic models in `dcp.schema` are the authoritative contract (SPEC §4).

```python
import dcp
dcp.__version__        # "0.2.0.dev0"  — package version (PEP 440)
dcp.PROTOCOL_VERSION   # "0.2.0"       — wire protocol version
```

## Facade — `Server`

The one-object entry point: store + registry + providers, with a run/resume method.

```python
Server(*, database_url=None, config=None, authenticator=None, generator=None)

server.register_template(template)
server.register_participant(participant)
server.instantiate(template_ref, *, owner, visibility=None, instance_id=None,
                   goal=None, termination=None, brief=None) -> DialogueInstance
server.server_info() -> ServerInfo
await server.run(
    instance_id, *, cast,                 # cast: dict[role_id -> participant_id]
    agent_providers=None,                 # dict[participant_id -> ModelProvider]
    orchestrator_provider=None,           # ModelProvider (else built from env)
    oversight=None,                       # OversightPolicy
    human_gateway=None,                   # HumanGateway
    control_policy=None,                  # ControlPolicy (else Plan/Flow by mode)
) -> DialogueInstance
```

`instantiate`'s `goal` / `termination` / `brief` are the per-run overrides (see [03](03-dialogue-template.md#3--the-instance--per-run-inputs)). 
`run` restores the instance first and **resumes** if it is non-terminal.

## Registry & Hosting  (`dcp.registry`)

```python
Registry(store, *, authenticator=None, dcp_version="0.2.0", generator=None, capabilities=None)

# templates (immutable per (id, version))
register_template(template) ; get_template(id, version) ; list_templates()
await generate_template(query, *, constraints=None) -> DialogueTemplate   # needs a generator

# participants
register_participant(p) ; get_participant(id) ; list_participants(*, discoverable_only=False)

# hosting
instantiate(template_ref, *, owner, visibility=None, instance_id=None,
            goal=None, termination=None, brief=None) -> DialogueInstance
grant_access(instance_id, *, grantor, participant_id, tier) -> None
join(instance_id, *, participant_id) -> DialogueInstance          # returns full replay
leave(instance_id, *, participant_id) -> None
get_instance(instance_id) -> DialogueInstance
list_instances(*, caller=None) -> list[DialogueInstance]          # visibility-filtered
restore(instance_id) -> DialogueInstance

# introspection & auth
server_info(env=None) -> ServerInfo
authenticate(token) -> str
```

### Authentication
```python
Authenticator                     # Protocol: authenticate(token: str | None) -> str
SimpleTokenAuthenticator(tokens: dict[str, str])      # token -> participant_id; else AuthError
AnonymousAuthenticator(participant_id="@local")       # dev mode: any/None token -> the id
```

## HTTP + SSE endpoints  (`dcp.delivery`)

`build_app(registry)` exposes the Registry as a Starlette REST + SSE app. 
Semantics and error codes: [06 · Hosting & Delivery](06-hosting-delivery.md#delivery-http--sse).

| Method & path | Operation |
|---------------|-----------|
| `GET /` | server info + capabilities + providers |
| `POST /templates` · `GET /templates` | register · list |
| `GET /templates/{id}/versions/{version}` | fetch one version |
| `POST /templates/generate` | draft from a query (501 if not enabled) |
| `POST /participants` · `GET /participants` · `GET /participants/{id}` | register · list · fetch |
| `POST /instances` | instantiate `{template_id, version, owner, visibility?, goal?, termination_policy?, brief?}` |
| `GET /instances` · `GET /instances/{id}` | list (`?caller=`) · full replay (+ `resumable`) |
| `POST /instances/{id}/join` · `.../leave` | join `{participant_id}` · leave |
| `GET /instances/{id}/events` | **SSE**: replay history then tail (`?tail=false` = finite) |

Errors → HTTP: `409` (immutability), `403` (access), `404` (unknown), `422` (bad body), `501` (capability off).

```python
build_app(registry) -> starlette.Starlette     # REST + SSE app
HttpSseDelivery(registry)                       # .asgi() -> app ; .run(host, port)
Delivery                                        # Protocol (transport-agnostic seam)
```

## Orchestration  (`dcp.orchestration`)

```python
Orchestrator(*, store, template, instance_id, cast, participants, provider,
             agent_providers=None, oversight=None, human_gateway=None,
             control_policy=None, max_recovery_attempts=3, max_revisions=2)
await orchestrator.run() -> DialogueInstance          # runs or resumes to a terminal status
orchestrator.submit_open_mic(input_id, content, from_participant)   # if template.allow_open_mic
orchestrator.address_open_mic(input_id, addressed_by)
```

### Control policies (the "brain") — see [04 · Orchestrator](04-orchestrator.md)
```python
ControlPolicy         # Protocol: async decide(ctx: DialogueContext) -> OrchestratorAction
PlanPolicy()          # emergent: ask the model for the next action (default in plan mode)
FlowPolicy()          # guided: follow the template's flow graph (default in flow mode)

DialogueContext       # read-only, log-derived view passed to a policy:
                      #   instance_id, goal (effective), topic, brief, termination_condition,
                      #   max_turns, roles, orchestration_mode, flow, status, turn, last_speaker,
                      #   roster, messages, open_gates, pending_inputs, budget, provider
                      # helpers: transcript(), brief_text(), role(id), filled_role_ids(),
                      #          over_turn_cap()
OrchestratorAction(action, target_role_id=None, status=DONE, reason="")   # select_speaker|stop|suspend
```

### Oversight policies
```python
OversightPolicy       # Protocol: async pre(role, transcript) / post(role, message, transcript)
DefaultOversight()    # deterministic all-pass (key-free happy path)
LlmOversight(provider)                 # asks the model for the structured records
ScriptedOversight(*, pre=[...], post=[...])   # FIFO of records — for tests

RubricOversight(*, relevance=None, role_consistency=None, completeness=None,
                grounding=None, safety=None, verdict_fn=None)   # one check per dimension
Check                 # Protocol: async (*, role, message, transcript) -> Assessment | CheckOutcome
CheckOutcome(assessment: Assessment, issue: str | None = None)
```

### Human gateway & termination
```python
HumanGateway          # Protocol: async request(*, role, policy, blocking) -> HumanReply
HumanReply(content: str | None = None, decision: str | None = None)   # content None == timeout
ScriptedHumanGateway({role_id: HumanReply})           # test gateway

resolve_termination(*, errored=False, over_budget=False, over_turns=False,
                    gate_timeout=False, done=False) -> TerminationStatus | None
# priority: error > budget > stopped > provisional > done
```

## Model providers  (`dcp.provider`) — see [05 · Participant](05-participant.md)

```python
ModelProvider         # Protocol: async text(instructions, content) -> str
                      #           async structured(instructions, content, schema) -> BaseModel
MockProvider(*, texts=[...], structured_queue=[...], structured_by_type={...})   # no network/key
OpenAIProvider(model, *, api_key=None, base_url=None)      # dcp.provider.openai_provider
AnthropicProvider(model, *, api_key=None)                  # dcp.provider.anthropic_provider
LocalProvider(model, *, base_url, api_key=None)            # provider="local" + DCP_BASE_URL
TransformersProvider(model="Qwen/Qwen3-4B", *, enable_thinking=False, max_new_tokens=512)
                                                           # provider="transformers"; dcp[transformers]

build_provider(binding: ModelBinding, *, api_key=None) -> ModelProvider   # per-binding factory (D8)
                                                  # unknown name -> a `dcp.providers` plugin (agent)
orchestrator_binding(config: Config) -> ModelBinding                      # env default binding
available_providers(env=None) -> list[ProviderInfo]      # built-ins + installed provider plugins
```

## Replay viewer

```python
render_timeline(store, instance_id) -> str     # transcript interleaved with control + oversight
# also: `dcp show <id> --timeline`
```

## Evaluation  (`dcp.evaluation`) — see [08 · Evaluation](08-evaluation.md)

```python
Scenario(name, template, cast, participants, *, agent_providers={}, human_gateway=None,
         orchestrator_provider=None, control_policy=None, oversight=None, scorer=None)
Candidate(name, *, control_policy=None, oversight=None)
Metric(name, fn, higher_is_better=None) ; DEFAULT_METRICS
await run_matrix(scenarios, candidates, metrics=DEFAULT_METRICS) -> list[RunResult]
aggregate(results) -> {candidate: {metric: mean}}     # + success_rate
render_report(results) -> str                          # comparison table
```

## State  (`dcp.state`)

```python
Store                 # Protocol — the persistence edge
SqlStore(url="sqlite:///:memory:")             # SQLAlchemy 2.x; SQLite dev / Postgres prod
restore(store, instance_id) -> DialogueInstance                # full replay (D3)
replay(header, records) -> DialogueInstance                    # pure reducer
InstanceHeader(...)   # the immutable base of an instance (not derived from the log)
```

## Participation  (`dcp.participation`)

```python
cast_roles(template, participants: list[Participant], instance_id, tiers=None) -> RolesCast
ParticipantRegistry(store)                     # register / get / list
tier_allows(held, required) -> bool ; can_speak(tier) ; can_observe(tier) ; assert_castable(tier)
```

## Authoring  (`dcp.authoring`)

```python
TemplateGenerator(provider)
await generator.generate(query, *, constraints=None) -> DialogueTemplate   # a draft (unregistered)
```

## Presets  (`dcp.presets`) — see [03 · Templates & Instances](03-dialogue-template.md#presets)

```python
list_presets() -> list[str]                 # names
get_preset(name) -> DialogueTemplate        # a fresh template (RegistryError if unknown)
# direct factories: design_review() debate() brainstorm() red_team_review() research_companion()
```

## Plugins  (`dcp.plugins`) — see [07 · Extending & Sharing](07-extending-sharing.md)

```python
GROUP_CONTROL_POLICIES = "dcp.control_policies"
GROUP_OVERSIGHT_POLICIES = "dcp.oversight_policies"
GROUP_TEMPLATES = "dcp.templates"
GROUP_PROVIDERS = "dcp.providers"                   # a packaged agent (ModelProvider), by name

list_plugins(group=None) -> list[PluginInfo]      # (group, name, value); nothing imported
available_plugins() -> dict[str, list[str]]        # group -> names (feeds server_info.plugins)
load_plugin(group, name) -> object                 # import the target on demand
load_control_policy(name) / load_oversight_policy(name)
load_model_provider(name) -> object                # a ModelProvider class/factory/instance
load_template(name) -> DialogueTemplate            # resolves an instance or a 0-arg factory
```

Components (portable, local/remote) live in `dcp.component` — see
[components-reference.md](components-reference.md).

## Config & errors

```python
Config(model_provider="openai", model=None, database_url="sqlite:///./dcp.db")
Config.from_env(env=None) -> Config
Config.api_key_for(provider, env=None) -> str | None
load_dotenv(path=".env", *, override=False)

DCPError              # base; subclasses: SchemaError, AccessError, AuthError, RegistryError,
                      # OrchestrationError, ProviderError, TerminationError, PluginError
```

## Schema  (`dcp.schema`)

The authoritative models (SPEC §4). Key types:

- **Entities:** `DialogueTemplate`, `DialogueInstance`, `Role`, `Participant`, `Message`, `Event`
- **Values:** `TemplateRef`, `ModelBinding`, `TerminationPolicy`, `Flow`, `Edge`, `HumanPolicy`,
  `Budget`, `RosterEntry`, `AccessGrant`, `Gate`, `PendingInput`, `Capabilities`, `ProviderInfo`,
  `ServerInfo`
- **Records:** `PreActionVerification`, `PostActionVerification`, `TerminationRecord`, `RolesCast`,
  `Issue`
- **Enums:** `InstanceStatus`, `TerminationStatus`, `RoleKind`, `ResponseRequirement`, `AccessTier`,
  `Visibility`, `OrchestrationMode`, `OnTimeout`, `EventType`, and the verification enums
  (`Readiness`, `Availability`, `CapabilityMatch`, `RoleState`, `ContextSufficiency`,
  `ExecutionFeasibility`, `RecommendedAction`, `Verdict`, `Assessment`, `PostOutcome`)
- **Helper:** `is_resumable(status) -> bool` ; `TERMINAL_STATUSES`

`DialogueInstance` carries the per-run `goal` / `brief` / `termination_policy` overrides (§4.2). 
Every model rejects unknown top-level fields (`extra="forbid"`); `Message` and `Event` are frozen.
Regenerate JSON Schemas with `python scripts/gen_schema.py` (generated, never hand-edited).

---

**Stuck?** [10 · Troubleshooting / FAQ](10-troubleshooting.md). · [All docs](README.md)
