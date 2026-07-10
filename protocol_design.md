# A Dialogue-centric Protocol for Human-Agent Multi-Agent Systems



## Reference Existing Protocol

- [Agent Communication Protocol](https://agentcommunicationprotocol.dev/introduction/welcome)

- [Agent Network Protocol (ANP)](https://github.com/agent-network-protocol/AgentNetworkProtocol)

- [agents-json](https://agent-json.com/)

- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/getting-started/intro)

- [Agent to Agent (A2A)](https://github.com/a2aproject/A2A)





## 0. Classifying Concrete Protocols

- Counterparty
  - Hybrid：human-agent / agent-agent / orchestrator-agent

- Payload
  - Hybrid payload：message + control action + state/event + human signal + artifact/context

- Interaction State
  - stateful

- Discovery Mechanism
  - Centralized / Platform-mediated discovery

- Schema Flexibility
  - Multiple predefined schemas, with potential extension toward evolving schemas


---

## 1. Core Entities

<img src="figures/protocol_entity_overview.svg" alt="Protocal Entity Overview" width="100%">


###  1.1 Dialogue

A `Dialogue` is the top-level container of the protocol.
It defines the task, participants, state, and termination criteria.
For Example:

```json
{
  "dialogue_id": "dlg_001",
  "title": "Evaluate a university-facing AI education platform",
  "topic": "AI for education",
  "goal": "Assess whether the proposed platform is technically feasible and commercially viable.",
  "termination": {
    "condition": "A final recommendation with risks and next steps has been produced.",
    "max_turns": 12,
    "token_budget": 10000
  },
  "status": "running",
  "turn": 0
}
```


### 1.2 Role

A `Role` defines a dialogue-local identity.
For example:

```json
{
  "role_id": "technical_critic",
  "name": "Technical Critic",
  "kind": "agent",
  "persona": "Identify technical risks, missing assumptions, and implementation bottlenecks.",
  "response_mode": "required",
  "binding": {
    "agent_id": "agent.critic.v1"
  }
}
```

### 1.3 Participant

A `Participant` is the actual entity that fills a role.
Participants may include:

* local LLM agents;
* external agents;
* human users;
* tool-backed agents;
* observers;
* invited users.

The protocol distinguishes between the role and the participant.
For example:

```text
Role: Technical Critic
Participant: agent.critic.v1

Role: Founder
Participant: @founder

Role: Audience Commenter
Participant: @observer_1
```

This distinction allows the system to preserve role semantics even when the underlying participant changes.



### 1.4 Orchestrator

The orchestrator is responsible for both `dialogue control` and `dialogue oversight`. Oversight is applied before and after each participant action. 
It is `not a participant` and does not directly contribute content to the transcript.

Before selecting the next speaker, the orchestrator performs speaker readiness verification. It checks whether a candidate role is available, properly bound, capable of addressing the current dialogue need, sufficiently informed by the available context, and operationally feasible to invoke. If the candidate is not ready, the orchestrator may inject missing context, request human input, choose an alternative speaker, wait for a gate, or terminate provisionally.

After a participant contributes, the orchestrator performs output verification. It checks whether the contribution is relevant to the goal, consistent with the assigned role, complete, grounded, safe, and responsive to pending human input. Depending on the result, it may continue, request revision, route to a verifier, escalate to a human gate, or stop.

<img src="figures/orchestrator_oversight_loop.svg" alt="Orchestrator Oversight" width="100%">

For example:

```json
{
  "action": "select_speaker",
  "target_role_id": "technical_critic",
  "reason": "The proposal has not yet been challenged from an implementation perspective."
}
```

Pre-action Oversight
```text
├── Pre-action Oversight
│   ├── candidate speaker generation
│   ├── availability verification
│   ├── capability verification
│   ├── role-state verification
│   ├── context sufficiency verification
│   └── execution feasibility verification
```


Possible orchestration actions for dialogue control include:

```text
select_speaker / inject_context / request_human / resolve_gate / stop
```

Example:
```json
{
  "action": "select_speaker | inject_context | request_human | request_revision | request_verification | stop",
  "target_role_id": "...",
  "pre_action_verification": {
    "readiness": "ready | not_ready | uncertain",
    "availability": "available | unavailable | waiting | timeout",
    "capability_match": "high | medium | low",
    "role_state": "needed | already_satisfied | overused | blocked",
    "context_sufficiency": "sufficient | insufficient",
    "execution_feasibility": "feasible | infeasible | uncertain",
    "issues": [],
    "recommended_action": "select_speaker | inject_context | choose_alternative | request_human | stop"
  },
  "reason": "..."
}
```

```python
def decide_next_action(dialogue_state):
    needs = assess_dialogue_needs(dialogue_state)
    candidates = generate_candidate_speakers(needs, dialogue_state.roles)

    verified_candidates = []
    for candidate in candidates:
        readiness = verify_speaker_readiness(candidate, needs, dialogue_state)
        if readiness.ready:
            verified_candidates.append((candidate, readiness))

    if verified_candidates is not empty:
        speaker = select_best_candidate(verified_candidates)
        return select_speaker(speaker, readiness)

    recovery = decide_recovery_action(candidates, dialogue_state)
    return recovery
```

Select a valid speaker:
```json
{
  "action": "select_speaker",
  "target_role_id": "technical_critic",
  "pre_action_verification": {
    "readiness": "ready",
    "availability": "available",
    "capability_match": "high",
    "role_state": "needed",
    "context_sufficiency": "sufficient",
    "execution_feasibility": "feasible",
    "issues": [],
    "recommended_action": "select_speaker"
  },
  "reason": "The current proposal needs technical feasibility verification, and the technical critic is available and suited for this role."
}
```

An unvalid speaker:
```json
{
  "action": "inject_context",
  "target_role_id": "technical_critic",
  "pre_action_verification": {
    "readiness": "not_ready",
    "availability": "available",
    "capability_match": "high",
    "role_state": "needed",
    "context_sufficiency": "insufficient",
    "execution_feasibility": "feasible",
    "issues": [
      {
        "type": "missing_context",
        "description": "The technical critic needs the implementation constraints before producing a useful critique."
      }
    ],
    "recommended_action": "inject_context"
  },
  "reason": "The technical critic is suitable, but the required implementation context is missing."
}
```

Post-action Oversight
```text
├── Post-action Oversight
│   ├── output verification
│   ├── role consistency check
│   ├── human input addressed check
│   ├── factuality / grounding check
│   └── issue tracking
```

### 1.5 Message

A `Message` is a finalized semantic contribution to the dialogue transcript.
Example:

```json
{
  "message_id": "msg_001",
  "dialogue_id": "dlg_001",
  "turn_id": 3,
  "role_id": "technical_critic",
  "speaker_name": "Technical Critic",
  "speaker_kind": "agent",
  "content": "The main technical risk is that the system depends heavily on reliable orchestration decisions.",
  "created_at": "..."
}
```

### 1.6 Event

An `Event` is a protocol-level record of state transitions, control decisions, participation signals, and delivery updates.
Events may be used for:

* audit;
* replay;
* debugging;
* evaluation;
* recovery;
* frontend synchronization.

Example:
```json
{
  "event_id": "evt_001",
  "dialogue_id": "dlg_001",
  "type": "turn_assigned",
  "payload": {
    "target_role_id": "technical_critic",
    "reason": "The proposal needs technical critique."
  },
  "created_at": "..."
}
```

Events are broader than messages.
A message records a finalized contribution.
An event records that something happened in the dialogue process.

---

# 2. Dialogue Lifecycle

<img src="figures/dialogue_lifecycle_overview.svg" alt="Dialogue lifecycle overview" width="100%">


## 2.1 Dialogue Creation

A dialogue may be created in two ways.
First, the user may provide a natural-language query:
```json
{
  "type": "spawn_dialogue",
  "query": "Should we build a university-facing AI education product?",
  "max_turns": 12
}
```
Second, the user may provide a full topology:

```json
{
  "type": "spawn_dialogue",
  "topology": {
    "dialogue": {
      "title": "...",
      "goal": "...",
      "termination": {
        "condition": "...",
        "max_turns": 12
      }
    },
    "roles": [...],
    "flow": {...},
    "human_policy": {...}
  }
}
```

The output is a new dialogue session.



## 2.2 Topology Generation or Loading

If the user provides only a query, the system may generate a topology automatically.
The topology defines:

* dialogue title;
* topic;
* goal;
* termination condition;
* roles;
* advisory flow;
* human participation policy;
* orchestration mode.

Example:
```json
{
  "dialogue": {
    "title": "Evaluate AI Education Platform",
    "topic": "AI for education",
    "goal": "Produce a recommendation on product feasibility and market direction.",
    "termination": {
      "condition": "A final recommendation with risks and next steps is produced.",
      "max_turns": 12
    }
  },
  "roles": [
    {
      "id": "agent.product.v1",
      "name": "Product Strategist",
      "kind": "agent",
      "persona": "Analyze product-market fit and user needs.",
      "response_mode": "required"
    },
    {
      "id": "agent.technical.v1",
      "name": "Technical Critic",
      "kind": "agent",
      "persona": "Identify technical risks and implementation challenges.",
      "response_mode": "required"
    },
    {
      "id": "founder",
      "name": "Founder",
      "kind": "human",
      "binding": {
        "human_handle": "@founder"
      },
      "response_mode": "gate",
      "human_policy": {
        "wait_window_seconds": 60,
        "on_timeout": "finalize_provisional"
      }
    }
  ],
  "flow": {
    "entry": "agent.product.v1",
    "edges": []
  },
  "orchestrator": {
    "mode": "plan"
  }
}
```



## 2.3 Role Casting

The system binds dialogue roles to concrete participants.
Casting may follow this precedence:

```text
explicit binding
role id matches a pool agent id
capability overlap
persona-based fallback
```

Example:
```json
{
  "type": "roles_cast",
  "dialogue_id": "dlg_001",
  "roles": [
    {
      "role_id": "product_strategist",
      "participant_id": "agent.product.v1"
    },
    {
      "role_id": "technical_critic",
      "participant_id": "agent.technical.v1"
    },
    {
      "role_id": "founder",
      "participant_id": "@founder"
    }
  ]
}
```

The protocol should record the casting decision for auditability.



## 2.4 Turn Orchestration

At each turn, the orchestrator selects the next action.
Example input to orchestrator:
```json
{
  "dialogue_id": "dlg_001",
  "goal": "Produce a recommendation on product feasibility.",
  "termination": {
    "condition": "A final recommendation with risks and next steps is produced."
  },
  "roles": [...],
  "messages": [...],
  "pending_human_inputs": [],
  "open_gates": [],
  "last_speaker": "product_strategist",
  "turn": 4
}
```

Example output:

```json
{
  "action": "select_speaker",
  "target_role_id": "technical_critic",
  "reason": "The previous turn focused on product value, but technical feasibility has not yet been examined."
}
```

The orchestration action is then recorded as an event.



## 2.5 Participant Contribution

Once a role is selected, the corresponding participant contributes to the dialogue.

For an agent:
```json
{
  "type": "contribution_submitted",
  "dialogue_id": "dlg_001",
  "role_id": "technical_critic",
  "speaker_kind": "agent",
  "content": "The technical risk is that the orchestration layer may fail under ambiguous user interventions.",
  "metadata": {
    "model": "..."
  }
}
```

For a human:
```json
{
  "type": "contribution_submitted",
  "dialogue_id": "dlg_001",
  "role_id": "founder",
  "speaker_kind": "human",
  "content": "I approve the recommendation, but please make the risk section more concrete.",
  "metadata": {
    "mode": "gate",
    "decision": "approve"
  }
}
```

The finalized contribution becomes a `Message`.
The process of receiving and recording that contribution is also represented as an `Event`.



## 2.6 Human Intervention
Human intervention may occur in three ways.

<img src="figures/human_intervention_three_modes.svg" alt="Human Intervention" width="100%">

### Optional Enrichment
The human can add information, but the system does not wait.

```json
{
  "mode": "optional",
  "on_timeout": "continue"
}
```

This is useful when human feedback is helpful but not required.

### Approval Gate
The system waits for human approval.
```json
{
  "mode": "gate",
  "wait_window_seconds": 60,
  "on_timeout": "finalize_provisional"
}
```
This is useful when a human must approve, reject, or revise the output.

### Open Mic
An observer without a defined seat may interject.

```json
{
  "mode": "open_mic",
  "speaker": "@observer",
  "content": "Can someone explain how this differs from A2A?",
  "addressed": false
}
```

The protocol should mark the input as pending until an agent explicitly addresses it.
Once addressed:
```json
{
  "type": "human_input_addressed",
  "payload": {
    "input_id": "human_input_001",
    "addressed_by": "technical_critic"
  }
}
```



## 2.7 Termination

A dialogue can terminate under multiple conditions.
Possible terminal statuses include:

```text
done
provisional
stopped
budget
error
```

### Done
The dialogue successfully satisfies its goal.

```json
{
  "status": "done",
  "reason": "The final recommendation has been produced and no gate remains open."
}
```

### Provisional
The dialogue produces a provisional result, usually because a human gate timed out.

```json
{
  "status": "provisional",
  "reason": "The founder approval gate timed out."
}
```

### Stopped
The dialogue stops because the turn cap was reached.

```json
{
  "status": "stopped",
  "reason": "The maximum number of turns was reached."
}
```

### Budget
The dialogue stops because the token or compute budget was reached.

```json
{
  "status": "budget",
  "reason": "The token budget was exceeded."
}
```

### Error
The dialogue stops because of a runtime error.

```json
{
  "status": "error",
  "reason": "The selected participant could not be called."
}
```

---

# 3. Protocol Layers

The protocol can be organized into four layers.

<img src="figures/four_layer_protocol_stack.svg" alt="Four Layer Protocol" width="100%">



## 3.1 Dialogue State Layer
This layer manages the core state of the dialogue.

It includes:

```text
dialogue_id
goal
topic
termination condition
roles
status
turn
messages
open gates
pending human inputs
tokens or budget
```

This layer defines what the dialogue is and where it currently stands.



## 3.2 Participation Layer
This layer defines how agents and humans participate.

It includes:

```text
agent roles
human seats
reserved bindings
optional human input
approval gates
open mic
cross-user spawn
observer participation
```

This layer is one of the main differences between a dialogue-centric protocol and a pure agent-to-agent protocol.

The protocol does not assume that all participants are autonomous agents. Human users can be required, optional, supervisory, or spontaneous contributors.



## 3.3 Orchestration Layer
This layer controls the evolution of the dialogue.

It includes:

```text
select speaker
inject context
request human input
resolve gate
address open-mic input
check termination
stop dialogue
```

The orchestration layer makes the dialogue controllable rather than purely emergent.

This is especially important for complex multi-agent systems, where unconstrained agent discussion may become repetitive, unbalanced, or misaligned with the goal.



## 3.4 Delivery Layer
This layer handles how protocol records are delivered to clients.

It may include:

```text
HTTP API
SSE
WebSocket
polling
batch replay
frontend rendering
token-level streaming
```

This layer is implementation-specific.

The protocol should not depend on any particular delivery mechanism.

For example, SSE-based token streaming is a useful implementation choice, but it is not required by the semantic protocol.

