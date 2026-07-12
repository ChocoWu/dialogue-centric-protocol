"""Run the SAME component REMOTELY: host it over HTTP, connect, drive the identical dialogue.

    python docs/examples/component/run_remote.py

Starts a real uvicorn server hosting the component's ``decide`` handler, then connects to it over
HTTP and runs the demo dialogue — the orchestrator's decisions happen on the server. No API key.
"""

from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

import uvicorn

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _demo import run_with                          # noqa: E402
from dcp.component import (                          # noqa: E402
    ComponentManifest,
    connect,
    http_transport,
    resolve,
    serve_component,
)
from round_robin import decide                       # noqa: E402  (the remote wire handler)

_PORT = 8123


def _serve() -> None:
    manifest = ComponentManifest.model_validate_json((HERE / "dcp-component.json").read_text())
    app = serve_component(manifest, decide=decide)   # host the payload handler
    uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=_PORT, log_level="error")).run()


async def _run() -> None:
    ref = f"file://{HERE / 'dcp-component.json'}"
    plan = resolve(ref, mode="remote")
    transport = http_transport(plan)                 # endpoint from the manifest; open (no token)
    policy = await connect(plan, transport)          # verifies the descriptor (D20)
    print(f"connected to a remote {policy.__class__.__name__}; running the dialogue...\n")

    inst = await run_with(policy)                     # decisions happen on the server
    print(f"status: {inst.status.value}  (turns: {inst.turn})  [orchestrated REMOTELY]")
    for m in inst.messages:
        print(f"  {m.role_id}: {m.content}")


def main() -> None:
    threading.Thread(target=_serve, daemon=True).start()
    time.sleep(1.5)                                  # let uvicorn bind the port
    asyncio.run(_run())


if __name__ == "__main__":
    main()
