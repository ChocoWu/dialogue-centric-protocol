"""The ``dcp`` command-line interface (Phase 6.3b).

A small stdlib-only CLI over the SDK, so a new user can inspect and serve DCP without writing code:

    dcp info                 # version, configured providers, capabilities, installed plugins
    dcp presets              # built-in dialogue templates
    dcp plugins              # installed third-party components (entry points)
    dcp serve [--db --host --port]              # run the HTTP + SSE server
    dcp show <instance_id> [--db --timeline]    # print an instance's transcript from a database
    dcp inspect <ref> [--mode]                  # resolve a component; print its no-side-effect plan
    dcp install <ref> [--mode --yes --lock]     # resolve + provision a component into this env
    dcp use <ref> [--mode --yes --token]        # install/connect, then materialize/confirm
    dcp connect <ref> [--token]                 # verify a remote endpoint; print its descriptor

Registered as the ``dcp`` console script (see pyproject ``[project.scripts]``).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from . import __version__
from .config import Config


def _cmd_info(args: argparse.Namespace) -> int:
    from .registry import Registry
    from .state import SqlStore

    info = Registry(SqlStore()).server_info()
    print(f"DCP {__version__}  (protocol {info.dcp_version})\n")
    print("capabilities:")
    for name, on in info.capabilities.model_dump().items():
        print(f"  {name:<18} {'on' if on else 'off'}")
    print("\nmodel providers:")
    for p in info.model_providers:
        print(f"  {p.provider:<12} {'configured' if p.configured else 'not configured'}")
    print("\nplugins:")
    if info.plugins:
        for group, names in info.plugins.items():
            print(f"  {group}: {', '.join(names)}")
    else:
        print("  (none installed)")
    return 0


def _cmd_presets(args: argparse.Namespace) -> int:
    from . import presets

    print("presets:")
    for name in presets.list_presets():
        print(f"  {name:<20} {presets.get_preset(name).title}")
    return 0


def _cmd_plugins(args: argparse.Namespace) -> int:
    from .plugins import GROUPS, list_plugins

    found = list_plugins()
    if not found:
        print("no plugins installed. Contribute components via entry points (docs/07-extending-sharing.md).")
        return 0
    for group in GROUPS:
        rows = [p for p in found if p.group == group]
        if rows:
            print(f"{group}:")
            for p in rows:
                print(f"  {p.name:<20} -> {p.value}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .delivery import build_app
    from .registry import Registry
    from .state import SqlStore

    app = build_app(Registry(SqlStore(args.db)))
    print(f"serving DCP on http://{args.host}:{args.port}  (db: {args.db})")
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    from .errors import RegistryError
    from .state import SqlStore, restore

    store = SqlStore(args.db)
    try:
        if args.timeline:
            from .viewer import render_timeline
            print(render_timeline(store, args.instance_id))   # transcript + control + oversight
            return 0
        inst = restore(store, args.instance_id)
    except RegistryError as exc:
        print(f"error: {exc}")
        return 1
    print(f"{inst.instance_id}  status={inst.status.value}  owner={inst.owner}  turn={inst.turn}")
    print(f"roster: {', '.join(f'{r.participant_id}({r.tier.value})' for r in inst.roster) or '—'}")
    print("transcript:")
    for m in inst.messages:
        print(f"  {m.role_id}: {m.content}")
    if not inst.messages:
        print("  (no messages yet)")
    return 0


def _resolve_for_cli(args: argparse.Namespace) -> object:
    from .component import resolve

    return resolve(args.ref, mode=args.mode)


def _confirm(plan: object, assume_yes: bool) -> bool:
    """Show side effects and ask for consent (unless ``--yes``). No side effects have run yet."""
    from .component import render_plan

    print(render_plan(plan))                                     # type: ignore[arg-type]
    if assume_yes:
        return True
    return input("\nproceed? [y/N] ").strip().lower() in ("y", "yes")


def _cmd_inspect(args: argparse.Namespace) -> int:
    from .component import render_plan
    from .errors import ComponentError

    try:
        plan = _resolve_for_cli(args)
    except ComponentError as exc:
        print(f"error: {exc}")
        return 1
    print(render_plan(plan))                                     # type: ignore[arg-type]
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    from .component import provision, write_lock
    from .errors import ComponentError

    try:
        plan = _resolve_for_cli(args)
        if not _confirm(plan, args.yes):
            print("aborted.")
            return 1
        report = provision(plan)                                 # type: ignore[arg-type]
        if args.lock:
            write_lock(plan, args.lock)                          # type: ignore[arg-type]
    except ComponentError as exc:
        print(f"error: {exc}")
        return 1
    if report.action == "already-present":
        print(f"\n✓ {report.package} already present — nothing to install.")
    else:
        print(f"\n✓ installed {report.spec}.")
    for art in report.artifacts:
        origin = "cached" if art.from_cache else "downloaded"
        print(f"  artifact {art.uri} — {origin} ({art.path})")
    if args.lock:
        print(f"  wrote lockfile {args.lock}")
    return 0


def _cmd_use(args: argparse.Namespace) -> int:
    from .component import materialize, provision
    from .errors import ComponentError

    try:
        plan = _resolve_for_cli(args)
        if plan.selected_mode.type == "remote":                  # type: ignore[attr-defined]
            return _use_remote(plan, args)
        if not _confirm(plan, args.yes):
            print("aborted.")
            return 1
        report = provision(plan)                                 # type: ignore[arg-type]
        obj = materialize(plan, artifacts=report.artifacts)      # type: ignore[arg-type]
    except ComponentError as exc:
        print(f"error: {exc}")
        return 1
    kind = plan.manifest.component.kind.value                    # type: ignore[attr-defined]
    print(f"\n✓ ready — materialized {kind}: {type(obj).__name__}")
    return 0


def _use_remote(plan: object, args: argparse.Namespace) -> int:
    import asyncio

    from .component import connect, http_transport

    if not _confirm(plan, args.yes):
        print("aborted.")
        return 1
    transport = http_transport(plan, token=args.token)           # type: ignore[arg-type]
    asyncio.run(connect(plan, transport))                        # type: ignore[arg-type]
    kind = plan.manifest.component.kind.value                    # type: ignore[attr-defined]
    print(f"\n✓ connected — remote {kind} verified and ready")
    return 0


def _cmd_connect(args: argparse.Namespace) -> int:
    import asyncio

    from .component import http_transport, resolve
    from .errors import ComponentError

    try:
        plan = resolve(args.ref, mode="remote")
        transport = http_transport(plan, token=args.token)
        descriptor = asyncio.run(transport.describe())
        from .component import verify_descriptor
        verify_descriptor(descriptor, plan.manifest, plan.selected_mode)  # type: ignore[arg-type]
    except ComponentError as exc:
        print(f"error: {exc}")
        return 1
    d = descriptor.component
    print(f"✓ connected to {d.namespace}/{d.name} @ {d.version}  ({d.kind.value})")
    print(f"  interface {descriptor.interface.name.value} {descriptor.interface.version} "
          f"over {descriptor.binding.protocol} {descriptor.binding.version}")
    if descriptor.deployment:
        print(f"  deployment revision: {descriptor.deployment.revision}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dcp", description="DCP — Dialogue-centric Protocol")
    parser.add_argument("--version", action="version", version=f"dcp {__version__}")
    default_db = Config.from_env().database_url
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("info", help="version, providers, capabilities, plugins").set_defaults(
        func=_cmd_info)
    sub.add_parser("presets", help="list built-in dialogue templates").set_defaults(
        func=_cmd_presets)
    sub.add_parser("plugins", help="list installed plugins").set_defaults(func=_cmd_plugins)

    serve = sub.add_parser("serve", help="run the HTTP + SSE server")
    serve.add_argument("--db", default=default_db, help="SQLAlchemy database URL")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=_cmd_serve)

    show = sub.add_parser("show", help="print an instance's transcript from a database")
    show.add_argument("instance_id")
    show.add_argument("--db", default=default_db, help="SQLAlchemy database URL")
    show.add_argument("--timeline", action="store_true",
                      help="show the full timeline (control decisions + oversight verdicts)")
    show.set_defaults(func=_cmd_show)

    for name, func, helptext in (
        ("inspect", _cmd_inspect, "resolve a component and print its (side-effect-free) plan"),
        ("install", _cmd_install, "resolve + provision a component into this environment"),
        ("use", _cmd_use, "install/connect, then materialize and confirm the component"),
        ("connect", _cmd_connect, "verify a remote component endpoint and print its descriptor"),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("ref", help="a component reference (file://, installed://, path)")
        if name != "connect":
            p.add_argument("--mode", default=None, choices=["local", "remote"],
                           help="select an access mode (default: the manifest's first)")
        if name not in ("inspect", "connect"):
            p.add_argument("--yes", "-y", action="store_true", help="skip the consent prompt")
        if name in ("use", "connect"):
            p.add_argument("--token", default=None, help="bearer token for a remote endpoint")
        if name == "install":
            p.add_argument("--lock", default=None, metavar="PATH",
                           help="write a reproducible lockfile of the resolved plan")
        p.set_defaults(func=func)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
