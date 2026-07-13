#!/usr/bin/env python3
"""Load a *shared* template by name via its plugin entry point (the sharing mechanism).

Sharing in DCP is not a raw import: you `pip install` a package that declares a `dcp.templates`
entry point, and DCP discovers it. Install the bundled example plugin first, then run this:

    pip install -e examples/plugin-example
    python docs/examples/template_create_plugin_share.py

See docs/07-extending-sharing.md for the full recipe.
"""
from __future__ import annotations

from dcp import plugins


def main() -> None:
    # Discovery is metadata-only — nothing is imported just by being installed.
    available = plugins.available_plugins()
    if "two_agent_debate" not in available.get("dcp.templates", []):
        raise SystemExit(
            "The example plugin isn't installed, so its template can't be discovered. Install it:\n"
            "    pip install -e examples/plugin-example\n"
            f"(currently discovered templates: {available.get('dcp.templates', [])})"
        )

    # Resolve the template BY NAME through the `dcp.templates` entry point — no import of the
    # plugin's module in this file. This is exactly how a consumer uses a shared component.
    tmpl = plugins.load_template("two_agent_debate")
    print("Loaded shared template 'two_agent_debate' (resolved by name via its entry point):")
    print(tmpl.model_dump(mode="json"))

    # A control policy / oversight / agent share the same way — resolve by name:
    #   plugins.load_control_policy("round_robin")
    #   plugins.load_oversight_policy("no_shouting")
    #   build_provider(ModelBinding(provider="echo", model="…"))   # a `dcp.providers` agent


if __name__ == "__main__":
    main()
