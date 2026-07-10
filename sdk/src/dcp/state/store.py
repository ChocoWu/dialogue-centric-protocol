"""Persistence: the append-only log + registered participants (SPEC §3.1/§3.4; A2, D3, D4).

The **event log is authoritative** (D3): an instance's runtime state is derived by replaying
its ordered ``messages + events`` (see :mod:`dcp.state.reducer`). The ``Store`` interface keeps
that log append-only — there is no update/delete for log records. The shipped implementation is
``SqlStore`` on SQLAlchemy 2.x (SQLite for dev, Postgres for production).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from sqlalchemy import Boolean, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from ..errors import RegistryError
from ..schema import (
    AccessGrant,
    DialogueTemplate,
    Event,
    Message,
    Participant,
    TemplateRef,
    Visibility,
)

#: A single append-only log record — a finalized Message or a process Event (SPEC §1.8/§1.9).
Record = Message | Event


@dataclass(frozen=True)
class InstanceHeader:
    """The immutable base of an instance — the part NOT derived from the log (SPEC §4.2)."""

    instance_id: str
    template_ref: TemplateRef
    owner: str
    visibility: Visibility
    dcp_version: str
    created_at: datetime


class _Base(DeclarativeBase):
    pass


class _InstanceRow(_Base):
    __tablename__ = "instances"

    instance_id: Mapped[str] = mapped_column(String, primary_key=True)
    template_id: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    owner: Mapped[str] = mapped_column(String)
    visibility: Mapped[str] = mapped_column(String)
    dcp_version: Mapped[str] = mapped_column(String)
    created_at: Mapped[str] = mapped_column(String)   # ISO 8601 (SQLite drops tz on DateTime)


class _LogRow(_Base):
    __tablename__ = "log"

    # Global autoincrement id defines total append order; filter by instance_id, order by id.
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    instance_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)          # "message" | "event"
    data: Mapped[str] = mapped_column(Text)            # record.model_dump_json()


class _ParticipantRow(_Base):
    __tablename__ = "participants"

    participant_id: Mapped[str] = mapped_column(String, primary_key=True)
    discoverable: Mapped[bool] = mapped_column(Boolean, index=True)
    data: Mapped[str] = mapped_column(Text)            # Participant.model_dump_json()


class _TemplateRow(_Base):
    __tablename__ = "templates"

    # (template_id, version) is the immutable identity of a registered template (SPEC §2.1).
    template_id: Mapped[str] = mapped_column(String, primary_key=True)
    version: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[str] = mapped_column(Text)            # DialogueTemplate.model_dump_json()


class _GrantRow(_Base):
    __tablename__ = "grants"

    # One tier per (instance, participant); re-granting overwrites (SPEC §1.6 AccessGrant, D5).
    instance_id: Mapped[str] = mapped_column(String, primary_key=True)
    participant_id: Mapped[str] = mapped_column(String, primary_key=True)
    data: Mapped[str] = mapped_column(Text)            # AccessGrant.model_dump_json()


@runtime_checkable
class Store(Protocol):
    """Persistence interface (SPEC §3.4). I/O edge; the semantic core depends only on this."""

    def create_instance(self, header: InstanceHeader) -> None: ...
    def get_header(self, instance_id: str) -> InstanceHeader | None: ...
    def list_instances(self) -> list[str]: ...
    def append(self, instance_id: str, record: Record) -> None: ...
    def load_records(self, instance_id: str) -> list[Record]: ...
    def register_participant(self, participant: Participant) -> None: ...
    def get_participant(self, participant_id: str) -> Participant | None: ...
    def list_participants(self, *, discoverable_only: bool = False) -> list[Participant]: ...
    def register_template(self, template: DialogueTemplate) -> None: ...
    def get_template(self, template_id: str, version: str) -> DialogueTemplate | None: ...
    def list_templates(self) -> list[DialogueTemplate]: ...
    def add_grant(self, grant: AccessGrant) -> None: ...
    def get_grant(self, instance_id: str, participant_id: str) -> AccessGrant | None: ...
    def list_grants(self, instance_id: str) -> list[AccessGrant]: ...


def _decode(kind: str, data: str) -> Record:
    if kind == "message":
        return Message.model_validate_json(data)
    return Event.model_validate_json(data)


class SqlStore:
    """SQLAlchemy-backed :class:`Store`. ``sqlite:///:memory:`` for tests, Postgres for prod."""

    def __init__(self, url: str = "sqlite:///:memory:") -> None:
        kwargs: dict[str, object] = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
            if ":memory:" in url:
                # One shared connection so the in-memory DB survives across threads (e.g. the
                # ASGI TestClient worker) instead of SingletonThreadPool's per-thread schema.
                kwargs["poolclass"] = StaticPool
        self._engine = create_engine(url, **kwargs)
        _Base.metadata.create_all(self._engine)

    # --- instances -------------------------------------------------------------------
    def create_instance(self, header: InstanceHeader) -> None:
        with Session(self._engine) as session:
            if session.get(_InstanceRow, header.instance_id) is not None:
                raise RegistryError(f"instance {header.instance_id!r} already exists")
            session.add(
                _InstanceRow(
                    instance_id=header.instance_id,
                    template_id=header.template_ref.template_id,
                    version=header.template_ref.version,
                    owner=header.owner,
                    visibility=str(header.visibility),
                    dcp_version=header.dcp_version,
                    created_at=header.created_at.isoformat(),
                )
            )
            session.commit()

    def get_header(self, instance_id: str) -> InstanceHeader | None:
        with Session(self._engine) as session:
            row = session.get(_InstanceRow, instance_id)
            if row is None:
                return None
            return InstanceHeader(
                instance_id=row.instance_id,
                template_ref=TemplateRef(template_id=row.template_id, version=row.version),
                owner=row.owner,
                visibility=Visibility(row.visibility),
                dcp_version=row.dcp_version,
                created_at=datetime.fromisoformat(row.created_at),
            )

    def list_instances(self) -> list[str]:
        with Session(self._engine) as session:
            stmt = select(_InstanceRow.instance_id).order_by(_InstanceRow.instance_id)
            return list(session.scalars(stmt))

    # --- append-only log -------------------------------------------------------------
    def append(self, instance_id: str, record: Record) -> None:
        kind = "message" if isinstance(record, Message) else "event"
        with Session(self._engine) as session:
            session.add(_LogRow(instance_id=instance_id, kind=kind, data=record.model_dump_json()))
            session.commit()

    def load_records(self, instance_id: str) -> list[Record]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(_LogRow).where(_LogRow.instance_id == instance_id).order_by(_LogRow.id)
            )
            return [_decode(r.kind, r.data) for r in rows]

    # --- participants (D4) -----------------------------------------------------------
    def register_participant(self, participant: Participant) -> None:
        with Session(self._engine) as session:
            if session.get(_ParticipantRow, participant.participant_id) is not None:
                raise RegistryError(f"participant {participant.participant_id!r} exists")
            session.add(
                _ParticipantRow(
                    participant_id=participant.participant_id,
                    discoverable=participant.discoverable,
                    data=participant.model_dump_json(),
                )
            )
            session.commit()

    def get_participant(self, participant_id: str) -> Participant | None:
        with Session(self._engine) as session:
            row = session.get(_ParticipantRow, participant_id)
            return Participant.model_validate_json(row.data) if row is not None else None

    def list_participants(self, *, discoverable_only: bool = False) -> list[Participant]:
        with Session(self._engine) as session:
            stmt = select(_ParticipantRow).order_by(_ParticipantRow.participant_id)
            if discoverable_only:
                stmt = stmt.where(_ParticipantRow.discoverable.is_(True))
            return [Participant.model_validate_json(r.data) for r in session.scalars(stmt)]

    # --- template catalog (SPEC §2.1; immutable per (id, version)) --------------------
    def register_template(self, template: DialogueTemplate) -> None:
        data = template.model_dump_json()
        with Session(self._engine) as session:
            existing = session.get(_TemplateRow, (template.template_id, template.version))
            if existing is not None:
                if existing.data != data:                  # immutability (SPEC §2.1, §6)
                    raise RegistryError(
                        f"template {template.template_id!r}@{template.version} already "
                        "registered with different content; bump the version"
                    )
                return                                      # identical re-register is idempotent
            session.add(
                _TemplateRow(
                    template_id=template.template_id, version=template.version, data=data
                )
            )
            session.commit()

    def get_template(self, template_id: str, version: str) -> DialogueTemplate | None:
        with Session(self._engine) as session:
            row = session.get(_TemplateRow, (template_id, version))
            return DialogueTemplate.model_validate_json(row.data) if row is not None else None

    def list_templates(self) -> list[DialogueTemplate]:
        with Session(self._engine) as session:
            stmt = select(_TemplateRow).order_by(
                _TemplateRow.template_id, _TemplateRow.version
            )
            return [DialogueTemplate.model_validate_json(r.data) for r in session.scalars(stmt)]

    # --- access grants (SPEC §1.6, D5) -----------------------------------------------
    def add_grant(self, grant: AccessGrant) -> None:
        with Session(self._engine) as session:
            session.merge(                                  # upsert: one tier per (inst, pid)
                _GrantRow(
                    instance_id=grant.instance_id,
                    participant_id=grant.participant_id,
                    data=grant.model_dump_json(),
                )
            )
            session.commit()

    def get_grant(self, instance_id: str, participant_id: str) -> AccessGrant | None:
        with Session(self._engine) as session:
            row = session.get(_GrantRow, (instance_id, participant_id))
            return AccessGrant.model_validate_json(row.data) if row is not None else None

    def list_grants(self, instance_id: str) -> list[AccessGrant]:
        with Session(self._engine) as session:
            stmt = (
                select(_GrantRow)
                .where(_GrantRow.instance_id == instance_id)
                .order_by(_GrantRow.participant_id)
            )
            return [AccessGrant.model_validate_json(r.data) for r in session.scalars(stmt)]


__all__ = ["Store", "SqlStore", "InstanceHeader", "Record"]
