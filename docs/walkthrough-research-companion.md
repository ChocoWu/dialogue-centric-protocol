# Walkthrough: building a Student Research Companion

This is a complete, small **multi-agent system** built on DCP — a companion that helps a student turn a research question into a grounded, advisor-approved direction. 
It's the "how do I build my own MAS on this?" example, and it exercises the whole platform: a **preset template**, a **custom orchestrator**, **oversight that acts**, and a **human approval gate**.

Runnable: [`examples/research_companion_mock.py`](examples/research_companion_mock.py) (key-free) and [`examples/research_companion.py`](examples/research_companion.py) (real model).

## The cast

The [`research_companion`](03-dialogue-template.md) preset seats:

| Role | Kind | Job |
|------|------|-----|
| Literature Scout | agent | find & summarize related work, **with citations** |
| Methodologist | agent | critique rigor, design, threats to validity |
| Writing Coach | agent | sharpen the framing and argument |
| Advisor | human (gate) | approve or redirect the direction |
| Student | human (optional) | pose the question, react to guidance |

## 1. The custom orchestrator

Instead of the preset's built-in flow, we drive the dialogue with our **own** `ControlPolicy` — a fixed research workflow. 
It needs no model; the next speaker is a pure function of the transcript:

```python
class ResearchWorkflowPolicy:
    ORDER = ("scout", "methodologist", "coach", "advisor")
    async def decide(self, ctx):
        spoken = {m.role_id for m in ctx.messages}
        for role in self.ORDER:
            if role not in spoken and role not in ctx.rejected_this_turn:   # skip unavailable
                return OrchestratorAction(action="select_speaker", target_role_id=role)
        return OrchestratorAction(action="stop", status=TerminationStatus.DONE)
```

That's the "bring your own orchestrator" story: you write one `decide` method; DCP's runtime supplies oversight, the human gate, termination, and replay around it. 
(Note `rejected_this_turn` — if a candidate is unavailable, this policy naturally skips to the next; the realized path adapts.)

## 2. Oversight that acts — grounding

The Scout's job is to cite sources. We attach a one-check `RubricOversight`:

```python
async def grounding_check(*, role, message, transcript):
    if role.role_id == "scout" and "http" not in message.content:
        return CheckOutcome(Assessment.WEAK, "cite a source (a URL)")
    return Assessment.OK

oversight = RubricOversight(grounding=grounding_check)
```

When the Scout's first draft has no citation, the check returns `weak` → the orchestrator routes the turn back for a **revision**, and the Scout speaks again with a source. 
This is D11 in action: verification *drives control*, it isn't just logged. 
In the transcript you'll see the Scout twice — the ungrounded draft, then the grounded revision.

## 3. The human gate

The Advisor is a `gate` role. 
When the workflow reaches it, the orchestrator opens a gate and waits for a human decision. 
In the examples that's scripted (`ScriptedHumanGateway`); in a real deployment it's your UI or an HTTP client answering the gate. 
Only after the Advisor approves does the dialogue reach `done`.

## 4. Durability & replay (D3)

Run it and you'll see the final line:

```
replayed from the log: 5 messages, 31 events
```

Nothing lived only in memory. `server.run(...)` returns the instance **reconstructed by replaying the append-only log**, and `restore(store, instance_id)` rebuilds that same object in any later session or process — the whole conversation is durable, auditable, and can be picked up later.

## 5. Resume across sessions

A research project spans days, and the advisor won't always be available today. 
When the workflow reaches an absent advisor, the orchestrator **suspends** — it pauses *without* terminating, leaving the instance non-terminal — and a later `run()` **resumes** it (SPEC §2.9):

```python
# day 1 — advisor away: pause before them
day1 = await server.run("proj", control_policy=ResearchWorkflowPolicy(suspend_before="advisor"), ...)
assert day1.status.value == "running"        # non-terminal, suspended

# day 2 — advisor back: a fresh run() continues the SAME instance to sign-off
day2 = await server.run("proj", control_policy=ResearchWorkflowPolicy(), ...)
assert day2.status.value == "done"           # resumed, not restarted
```

`suspend` is just a control action the policy returns; the runtime records `instance_suspended` and stops appending. 
Because state is the log (D3), resuming needs nothing but the same instance id.

## Run it

```bash
python docs/examples/research_companion_mock.py     # no key
```

Expected:

```
status: done  (turns: 5)

  scout: Prior work uses transformer retrievers.
  scout: Prior work uses transformer retrievers, e.g. http://arxiv.org/abs/2401.00001
  methodologist: Add a baseline and an ablation to isolate the gain.
  coach: Sharpen the contribution to one crisp sentence.
  advisor: Direction approved — proceed to a pilot.
```

For live agents, set a provider in `.env` and run `research_companion.py`.

## Where to go next

- Swap the fixed `ResearchWorkflowPolicy` for a model-driven one, or the preset's guided `flow`.
- Add checks to the rubric (safety, completeness) — see [07-extending-sharing.md](07-extending-sharing.md).
- Package your policy/template as a plugin so others can `pip install` it ([07-extending-sharing.md](07-extending-sharing.md#4-share-it--entry-points)).
