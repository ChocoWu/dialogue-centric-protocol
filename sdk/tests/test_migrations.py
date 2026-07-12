"""Phase 6.4 — Alembic migrations produce a usable schema (DB hardening)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("alembic")   # skip when the migrations extra isn't installed

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from dcp import schema as s  # noqa: E402
from dcp.registry import Registry  # noqa: E402
from dcp.state import SqlStore  # noqa: E402

_SDK = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_SDK / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _template() -> s.DialogueTemplate:
    return s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)])


def test_upgrade_head_creates_a_usable_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DCP_DATABASE_URL", raising=False)
    url = f"sqlite:///{tmp_path / 'dcp.db'}"
    command.upgrade(_cfg(url), "head")

    # the store did NOT create the tables — the schema is entirely from the migration
    reg = Registry(SqlStore(url, create_tables=False))
    reg.register_template(_template())
    inst = reg.instantiate(s.TemplateRef(template_id="t", version="1.0.0"),
                           owner="@o", instance_id="x")
    assert inst.status is s.InstanceStatus.CREATED
    assert reg.get_template("t", "1.0.0") is not None


def test_downgrade_then_upgrade_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DCP_DATABASE_URL", raising=False)
    url = f"sqlite:///{tmp_path / 'dcp.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")     # drops every table
    command.upgrade(cfg, "head")       # and rebuilds it
    Registry(SqlStore(url, create_tables=False)).register_template(_template())   # usable again
