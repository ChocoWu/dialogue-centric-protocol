# Runnable component example — one component, two delivery modes

A complete, key-free DCP **component**: a model-free round-robin orchestrator, described by a
manifest and run two ways — **local** (resolve → materialize) and **remote** (serve → connect) — from
the *same* [`dcp-component.json`](dcp-component.json). See [../../guide-components.md](../../guide-components.md).

## Files

| File | What it is |
|------|-----------|
| [`dcp-component.json`](dcp-component.json) | the manifest — one `control_policy`, with **both** a `local` and a `remote` access mode |
| [`round_robin.py`](round_robin.py) | the component: `RoundRobinPolicy` (local `ControlPolicy`) + `decide` (the remote wire handler) |
| [`_demo.py`](_demo.py) | a shared 2-agent dialogue driven by whatever policy you hand it |
| [`run_local.py`](run_local.py) | resolve → inspect → materialize → run |
| [`run_remote.py`](run_remote.py) | host over HTTP (uvicorn) → connect → run (decisions happen server-side) |

## Run it

```bash
python docs/examples/component/run_local.py     # resolve + materialize locally
python docs/examples/component/run_remote.py    # serve + connect over HTTP
```

Both print the same transcript:

```
status: done  (turns: 2)
  proposer: I propose 'Northstar'.
  critic: 'Northstar' is clear and low-risk. +1.
```

The only difference is *how the orchestrator was obtained* — materialized from local code, or
connected to a running server. That's the point: a component is portable across delivery modes.

## Notes

- **No install needed.** The scripts put this directory on `sys.path`, so the component's module is
  importable — `provision` is a no-op and `materialize` just imports the entrypoint. (`inspect` still
  *lists* the `pip install` it would run for a real consumer.)
- **JSON manifest** so it runs with no extra; the same shape works as YAML with `pip install 'dcp[yaml]'`.
- **`run_remote.py` needs a free port** (`127.0.0.1:8123`). The wire contract is the *projected
  payload* — note `round_robin.decide(payload)` reads a dict, while `RoundRobinPolicy.decide(ctx)`
  reads a `DialogueContext`.
