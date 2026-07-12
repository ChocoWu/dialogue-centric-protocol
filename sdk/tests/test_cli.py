"""Phase 6.3b — the `dcp` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from dcp import schema as s
from dcp.cli import main
from dcp.registry import Registry
from dcp.state import SqlStore


def test_version_flag_exits() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_no_command_prints_help_and_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 1
    assert "usage: dcp" in capsys.readouterr().out


def test_info(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "DCP" in out and "model providers:" in out
    assert "mock" in out and "capabilities:" in out


def test_presets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["presets"]) == 0
    out = capsys.readouterr().out
    assert "research_companion" in out and "debate" in out


def test_plugins_none_installed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["plugins"]) == 0
    assert "no plugins installed" in capsys.readouterr().out


def test_show_reads_an_instance_from_a_db(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"sqlite:///{tmp_path / 'dcp.db'}"
    reg = Registry(SqlStore(url))
    reg.register_template(s.DialogueTemplate(
        template_id="t", version="1.0.0", title="T",
        termination_policy=s.TerminationPolicy(condition="done"),
        roles=[s.Role(role_id="a", name="A", kind=s.RoleKind.AGENT,
                      response_requirement=s.ResponseRequirement.REQUIRED)]))
    reg.instantiate(s.TemplateRef(template_id="t", version="1.0.0"),
                    owner="@owner", instance_id="proj")

    assert main(["show", "--db", url, "proj"]) == 0
    out = capsys.readouterr().out
    assert "proj" in out and "status=created" in out and "@owner" in out

    # --timeline renders the full log (control + oversight); a created instance shows lifecycle
    assert main(["show", "--db", url, "proj", "--timeline"]) == 0
    tl = capsys.readouterr().out
    assert "instance proj" in tl and "joined @owner" in tl


def test_show_unknown_instance_returns_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    url = f"sqlite:///{tmp_path / 'dcp.db'}"
    SqlStore(url)  # create the schema
    assert main(["show", "--db", url, "nope"]) == 1
    assert "error" in capsys.readouterr().out


def test_serve_builds_app_and_calls_uvicorn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: dict[str, object] = {}

    def _fake_run(app: object, **kw: object) -> None:
        calls["app"] = app
        calls["kw"] = kw

    monkeypatch.setattr("uvicorn.run", _fake_run)
    assert main(["serve", "--port", "9099", "--db", "sqlite:///:memory:"]) == 0
    assert calls["app"] is not None
    assert calls["kw"] == {"host": "127.0.0.1", "port": 9099}
    assert "serving DCP" in capsys.readouterr().out
