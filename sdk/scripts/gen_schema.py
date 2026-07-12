#!/usr/bin/env python
"""Generate JSON Schema from the Pydantic source-of-truth models (methodology item 7).

Writes one ``<Entity>.json`` per top-level entity into ``schema/generated/``. These files are
GENERATED — do not hand-edit; regenerate with ``python scripts/gen_schema.py``. The Pydantic
models in ``dcp.schema`` remain authoritative (SPEC Normative Content clause).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dcp import schema as s  # noqa: E402
from dcp.component import ComponentManifest  # noqa: E402

_TOP_LEVEL = [
    s.DialogueTemplate,
    s.DialogueInstance,
    s.Participant,
    s.Role,
    s.Message,
    s.Event,
    s.ModelBinding,
    s.PreActionVerification,
    s.PostActionVerification,
    s.TerminationRecord,
    s.RolesCast,
    s.AccessGrant,
    s.ServerInfo,
    ComponentManifest,      # the Phase-7 component contract (portable, non-Python-validatable)
]

_BANNER = "GENERATED from dcp.schema (Pydantic v2) — do not edit; run scripts/gen_schema.py."


def main() -> int:
    out = Path(__file__).resolve().parents[1] / "schema" / "generated"
    out.mkdir(parents=True, exist_ok=True)
    for model in _TOP_LEVEL:
        doc = model.model_json_schema()
        doc = {"$comment": _BANNER, **doc}
        (out / f"{model.__name__}.json").write_text(
            json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(f"wrote {len(_TOP_LEVEL)} schemas to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
