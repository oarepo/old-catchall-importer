"""All database access for the manual migration lives here.

The migration script (`migrate.py`) never touches the database directly — it
just asks this module for the source records and the lookups it needs, so the
migration logic stays readable and you can focus on the data, not the wiring.

Two databases:
  source = live NR production Postgres   (docker nr-data-prod-db, 127.0.0.1:5832)
  target = datarepo                      (docker datarepo-db-1,    127.0.0.1:5632)
Change the DSNs below if the containers/ports move.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
import sqlalchemy
from sqlalchemy.orm import Session

engine = sqlalchemy.create_engine(
    "postgresql://datarepo:datarepo@localhost:5632/datarepo"
)


@dataclass
class Lookups:
    """Everything the transform needs to resolve ids — fetched once up front."""
    vocab: dict[str, set[str]]           # vocab type -> {valid ids}
    vocab_records: dict[str, dict[str, dict]]  # vtype -> id -> {uuid, revision, json}
    existing_slugs: set[str] = field(default_factory=set)

    def has(self, vtype: str, vid: str) -> bool:
        return vid in self.vocab.get(vtype, ())

    def record(self, vtype: str, vid: str) -> dict | None:
        """The full target vocabulary record JSON for (vtype, vid), or None.

        This is the *whole* entry (title, props, …), so the transform can check
        that everything the source carried is actually present in the target
        vocabulary and nothing is silently dropped.
        """
        entry = self.vocab_records.get(vtype, {}).get(vid)
        return entry["json"] if entry else None

    def ref(self, vtype: str, vid: str) -> dict | None:
        """A dereferenced vocabulary reference ``{"id": ...}``, or None.
        """
        entry = self.vocab_records.get(vtype, {}).get(vid)
        if not entry:
            return None
        return {"id": vid}

def load_lookups() -> Lookups:
    """Build the Lookups from the target DB.

    ``get_session`` is a context-manager factory yielding a SQLAlchemy session
    (see ``export_from_old_db.db.get_session``).
    """
    with Session(engine) as session:
        vocab: dict[str, set[str]] = {}
        vocab_records: dict[str, dict[str, dict]] = {}
        rows = session.execute(
            text("SELECT id::text, version_id, json FROM vocabularies_metadata"))
        for uuid_, version_id, j in rows:
            vt = (j.get("type") or {}).get("id")
            vid = j.get("id")
            if not vt or not vid:
                continue
            vocab.setdefault(vt, set()).add(vid)
            vocab_records.setdefault(vt, {})[vid] = {
                "uuid": uuid_, "revision": (version_id or 1) - 1, "json": j}

        rows = session.execute(
            text("SELECT id, pid, version_id, json FROM affiliation_metadata"))
        for uuid_, pid, version_id, j in rows: # TODO: double check the revisions are correct
            vocab.setdefault("affiliations", set()).add(pid)
            vocab_records.setdefault("affiliations", {})[pid] = {"uuid": uuid_, "revision": (version_id or 1) - 1, "json": j}

        rows = session.execute(
            text("SELECT id, pid, version_id, json FROM funder_metadata"))
        for uuid_, pid, version_id, j in rows:
            vocab.setdefault("funders", set()).add(pid)
            vocab_records.setdefault("funders", {})[pid] = {"uuid": uuid_, "revision": (version_id or 1) - 1, "json": j}

        rows = session.execute(
            text("SELECT id, pid, version_id, json FROM name_metadata"))
        for uuid_, pid, version_id, j in rows:
            vocab.setdefault("names", set()).add(pid)
            vocab_records.setdefault("names", {})[pid] = {"uuid": uuid_, "revision": (version_id or 1) - 1, "json": j}

        """
        rows = session.execute(
            text("SELECT id, pid, version_id, json FROM award_metadata"))
        for uuid_, pid, version_id, j in rows:
            if "number" in j:
                pid = j["number"]
            vocab.setdefault("awards", set()).add(pid)
            vocab_records.setdefault("awards", {})[pid] = {"uuid": uuid_, "revision": (version_id or 1) - 1, "json": j}
        """

    return Lookups(vocab, vocab_records)

_LOOKUP = load_lookups()