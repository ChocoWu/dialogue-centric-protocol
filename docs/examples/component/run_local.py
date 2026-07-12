"""Run the round-robin component LOCALLY: resolve → inspect → materialize → drive a dialogue.

    python docs/examples/component/run_local.py

No API key. The component's package isn't really on PyPI — but its module is importable from this
directory, so ``provision`` is a no-op and ``materialize`` just imports the entrypoint.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                      # make `round_robin` / `_demo` importable

from _demo import run_with                          # noqa: E402
from dcp.component import materialize, provision, render_plan, resolve   # noqa: E402


def main() -> None:
    ref = f"file://{HERE / 'dcp-component.json'}"
    plan = resolve(ref, mode="local")              # side-effect-free
    print("resolved plan (nothing has run yet):\n")
    print(render_plan(plan))

    provision(plan)                                # no-op: the module is already importable
    policy = materialize(plan)                     # import the entrypoint → a ControlPolicy
    print(f"\nmaterialized: {type(policy).__name__}\n")

    inst = asyncio.run(run_with(policy))
    print(f"status: {inst.status.value}  (turns: {inst.turn})")
    for m in inst.messages:
        print(f"  {m.role_id}: {m.content}")


if __name__ == "__main__":
    main()
