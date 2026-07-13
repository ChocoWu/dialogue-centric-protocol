#!/usr/bin/env python3
"""Create a DialogueTemplate from a built-in preset (presets.get_preset).

Run:
  python docs/examples/template_create_preset.py
"""
from pathlib import Path
import sys

from dcp import presets


def main() -> None:
    print("Available presets:")
    for name in presets.list_presets():
        print(" -", name)

    tmpl = presets.get_preset("design_review")
    print("\nPicked preset 'design_review':")
    print(tmpl.model_dump(mode="json"))


if __name__ == "__main__":
    main()
