"""Manual NR -> datarepo migration, one record at a time, in the debugger.

Readability refactor of ``migrate.py`` — same observable behavior, same
``main()`` contract (verified by ``test_refactor_equivalence.py``).

This is deliberately small and linear. There is no command line: tweak the
knobs below, set a breakpoint inside the loop in `main()`, and step through.
For each source record a `RecordDataConverter` produces:

  converter.rec.source            — the raw NR JSON (destructively consumed by build())
  converter.rec.target            — the assembled datarepo record
  converter.unmapped              — source data build() never mapped (unplanned losses)
  converter.mapping_irregularities — known/expected conflicts to review

`main()` additionally validates each record's metadata against the live
datasets service schema and returns one result dict per record. Nothing is
written to any database — the write path does not exist yet.

Requirements to run:
  * cwd must be this folder (mapping tables are loaded via relative paths),
  * both DBs up: source NR at 127.0.0.1:5832, target datarepo at 127.0.0.1:5632,
  * an Invenio app context (see the __main__ block at the bottom).

Importing this module has side effects: `vocabularies_mapping_scripts`
regenerates vocabularies/mapping_tables/*.csv from both DBs, and those CSVs
plus the award table are then loaded into module globals.

The kinds of conflict this finds, and how to resolve each by hand, are written
up in plain language in CONFLICTS.md (same folder).

Connection details are abstracted away in db.py.
"""

from __future__ import annotations

import copy
import csv
import functools
import json
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import langcodes
from marshmallow import ValidationError
from marshmallow_utils.fields import EDTFDateString, SanitizedUnicode

# --------------------------------------------------------------------------- #
# mapping tables (loaded once, at import time, from cwd-relative paths)
# --------------------------------------------------------------------------- #

MAPPED_VOCABS = (
    "contributorsroles",
    "relationtypes",
    "languages",
    "licenses",
    "resourcetypes",
    "subjectcategories",
    "affiliations",
    "funders",
)
MAPPING_TABLES = {}  # vocab type -> {source slug: target id}
AWARD_TABLE = {}  # (projectID, projectName, fundingProgram) -> award entry


def _init_mapping_tables():
    global MAPPING_TABLES
    for tgt_code in MAPPED_VOCABS:
        with open(
            f"export_from_old_db/mapping_tables/{tgt_code}.csv",
            encoding="utf-8-sig",
            newline="",
        ) as f:
            rows = csv.reader(f)
            next(rows, None)  # header
            MAPPING_TABLES[tgt_code] = {row[0]: row[1] for row in rows}


# NOTE! en projectTitle in entries with czech projectName are claude-translated
def _init_award_table():
    global AWARD_TABLE
    with open("export_from_old_db/mapping_tables/funding_trio.json") as f:
        AWARD_TABLE = {
            (e["projectID"], e["projectName"], e["fundingProgram"]): e
            for e in json.load(f)
        }


_init_mapping_tables()
_init_award_table()

RECORDS_TO_DB_SLUG_TRANSFORM = {
    "contributorsroles": lambda rec_slug: rec_slug.replace("-", "_"),
    "affiliations": lambda rec_slug: rec_slug.replace("-", "_").replace("/", "."),
    "licenses": lambda rec_slug: rec_slug.replace("-", "_").replace("/", "."),
    "subjectcategories": lambda slug: slug.replace("/", "."),
}

# --------------------------------------------------------------------------- #
# mapping policy: what is mapped, what is dropped, what is noise
# --------------------------------------------------------------------------- #

DATE_EXCEPTION_MAP = {
    "2025-11-31": "2025-11-30",
}

ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dXx]")

# source description field -> CCMM descriptiontypes vocab id
_DESCRIPTION_FIELDS = {
    "abstract": "abstract",
    "methods": "methods",
    "technicalInfo": "technical-info",
    "technicalNotes": "technical-info",
    "notes": "other",
}

MAPPED_FIELDS = {
    "InvenioID",
    "titles",
    "creators",
    "dateAvailable",
    "dateCreated",
    "language",
    "rights",
    "subjectCategories",
    "keywords",
    "publisher",
    "accessRights",
    "oarepo:ownedBy",
    "oarepo:recordStatus",
    "persistentIdentifiers",
    "_files",
    # mapped below:
    "contributors",
    "abstract",
    "methods",
    "technicalInfo",
    "technicalNotes",
    "notes",
    "dateCollected",
    "fundingReferences",
    "relatedItems",
    "resourceType",
}
# Source keys we deliberately don't migrate. EMPTY FOR NOW — as you review the
# unmapped fields surfaced below, move the ones that are safe to drop here.
EXCEPTIONS: set[str] = {
    "$schema",
    "_bucket",
    "oarepo:doirequest",
    "oarepo:draft",
    "oarepo:validity",
}  # "_bucket is set for files individually?"
TO_BE_DECIDED = {
    "oarepo:primaryCommunity",
}

# taxonomy bookkeeping keys — never descriptive content, ignored everywhere
_VOCAB_NOISE = {
    "links",
    "self",
    "tree",
    "level",
    "status",
    "selectable",
    "is_ancestor",
    "ancestor",
    "busy_count",
    "descendants_count",
    "descendants_busy_count",
    "label",
    "ancestors",
    "data",
    "aliases",
}

MISSING_VOCAB_DATA = defaultdict(
    set
)  # accumulates vocab ids missing in the target, across records

# Per-vocab-entry leftovers: source keys the build methods knowingly leave
# behind, declared as decorator exceptions so they aren't flagged as losses.
# A path is a tuple of dict keys (lists along the way act as wildcards); an
# optional second element restricts the removal to that exact value.
AFFILIATIONS_LEFTOUTS = (
    (("affiliation", "slug"),),
    (("affiliation", "institutionCategory"),),  # not in our vocabs
    (
        ("affiliation", "title"),
    ),  # in vocabs but not in AffiliationRelationSchema; misses english translations
    (("affiliation", "nameType"),),  # organizational implicitly?
    (("affiliation", "relatedURI", "ROR"),),  # converted to identifier
    (("affiliation", "ico"),),  #
    (("affiliation", "relatedURI", "URL"),),
    (
        (
            "affiliation",
            "relatedRID",
        ),
    ),  # what is this?
    (("affiliation", "formerTitles"),),  # not in our vocabs
    (("affiliation", "nameTranslated"),),  # not in our vocabs
    (
        ("affiliation", "fullName"),
    ),  # sometimes differs from name in our vocabularies; we are using ours
)


CONTRIBUTOR_ROLE_LEFTOUTS = (
    (("role", "slug"),),
    (("role", "marcCode"),),  # not in our vocabs
    (
        ("role", "title", "cs"),
        "spolupracovník",
    ),  # NOTE! not in ccmm vocabs - RelatedPerson was used instead
    (("role", "title", "en"), "collaborator"),
    (("role", "title", "cs"), "vedoucí"),
    (("role", "title", "en"), "advisor"),
    (("role", "title", "cs"), "umělec"),
    (("role", "title", "en"), "artist"),
)

LANGUAGE_LEFTOUTS = (
    (("title", "cs"), "kannadština"),  # different/wrong titles in datarepo vocabs
    (("title", "cs"), "afarština"),
    (("title", "cs"), "abcházština"),
)

FUNDER_LEFTOUTS = (
    (("funder", "noTick"),),
    (("funder", "tickable"),),  # idk what this is
    (("funder", "CEA"),),
    (("funder", "slug"),),
    (("funder", "title"),),  # titles are wrong in current datarepo vocabs
    (("funder", "nameType"),),
    (("funder", "relatedURI", "DOI"),),
    (("funder", "relatedURI", "ROR"),),
)


@dataclass
class Record:
    source: dict
    target: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# nested-structure helpers
# --------------------------------------------------------------------------- #


def clean(value):
    """SanitizedUnicode-deserialise then strip whitespace; None stays None."""
    if value is None:
        return None
    return SanitizedUnicode().deserialize(value).strip()


def _lang_id(code):
    if not code:
        return None
    res = langcodes.Language.get(code.lower()).to_alpha3()
    assert res
    return res.upper()


def _walk_to_parent(obj, path):
    """Return the container holding path's last element."""
    for step in path[:-1]:
        obj = obj[step]
    return obj


def _del_from_vocabs_multiple(obj, paths):
    """Delete every path (a tuple of dict keys / list indices) from obj.

    Within one list, elements are deleted highest-index-first so removing one
    never shifts the indices of the others still to delete. Parents are looked
    up before any deletion, so a shift in one list can't invalidate a parent
    that another path still needs.
    """
    # Group the keys to delete by the container that holds them. Containers are
    # unhashable, so key the group by id() and keep the container alongside.
    groups = {}  # id(parent) -> (parent, keys_to_delete)
    for path in paths:
        parent = _walk_to_parent(obj, path)
        _, keys = groups.setdefault(id(parent), (parent, set()))
        keys.add(path[-1])

    for parent, keys in groups.values():
        if isinstance(parent, list):
            keys = sorted(keys, reverse=True)  # back-to-front keeps indices valid
        for key in keys:
            del parent[key]


def _set_if_present(target, target_key, source, source_key, del_from_source=False):
    """Copy source's (dotted-path) value into target[target_key] when truthy."""
    parts = source_key.split(".")
    cur = source
    for k in parts:
        cur = cur.get(k, {})
    if cur:
        target.setdefault(target_key, cur)
    if del_from_source:
        source_parent = _walk_to_parent(source, parts)
        del source_parent[parts[-1]]


# --------------------------------------------------------------------------- #
# strings, names, languages, dates
# --------------------------------------------------------------------------- #


def _pick_in_preferred_lang(d, *langs, return_lang=False):
    """Pick a string from a multilingual {cs,en,...} dict.

    A plain string is returned as-is. The languages given as `langs` are tried
    first, then cs, then en. With return_lang=True, returns (value, lang).
    """
    if not isinstance(d, dict):
        return d if isinstance(d, str) else None
    for lg in (*langs, "cs", "en"):
        if d.get(lg):
            if return_lang:
                return d[lg], lg
            return d[lg]
    raise ValueError(f"no preferred language in {d!r}")


def _split_name(full):
    """Split a full name into (family, given); given may be None."""
    if "," in full:
        fam, _, giv = full.partition(",")
        return fam.strip(), (giv.strip() or None)
    parts = full.split()
    return (
        (parts[-1], " ".join(parts[:-1])) if len(parts) >= 2 else (full.strip(), None)
    )


def cz_date_to_iso(value):
    """Convert a Czech-style 'D.M.YYYY' date to ISO 'YYYY-MM-DD', else None.

    Handles padded and unpadded day/month ('1.1.2022', '20.01.2026'). Returns
    None when the value isn't a Czech-style date or isn't a real calendar day
    (e.g. '31.11.2025'), so the caller can fall back to its own handling.
    """
    try:
        return datetime.strptime(value.strip(), "%d.%m.%Y").date().isoformat()
    except (ValueError, AttributeError):
        return None


def _get_id_from_coar_related_uri(ruri):
    return ruri["COAR"].rstrip("/").split("/")[-1]


def _is_draft(source):
    """
        nr_data_prod=# SELECT count(*), json->>'oarepo:recordStatus', json->>'oarepo:draft' FROM records_metadata GROUP BY json->>'oarepo:recordStatus', json->>'oarepo:draft';
     count | ?column?  | ?column?
    -------+-----------+----------
       225 |           |
       170 | published |
       104 | editing   | true
         1 | approved  |
    """
    return (
        source.get("oarepo:recordStatus", None) == "editing"
        or source.get("oarepo:draft", False) == True
    )


def _reverse_iterate(lst: list):
    """Yield (idx, elem) back-to-front so the caller can delete while iterating."""
    yield from reversed(list(enumerate(lst)))


def _get_from_mapping_tables(vtype, slug):
    key = (
        RECORDS_TO_DB_SLUG_TRANSFORM[vtype](slug)
        if vtype in RECORDS_TO_DB_SLUG_TRANSFORM
        else slug
    )
    return MAPPING_TABLES[vtype][key]


# --------------------------------------------------------------------------- #
# unmapped-data detection
#
# The build_* methods destructively consume self.nr (the source json) as they
# map fields. Whatever is left afterwards is data the migration would lose.
# The pieces here strip the losses we have explicitly accepted (`exceptions`)
# and record the rest in converter.unmapped for review.
# --------------------------------------------------------------------------- #


def _remove_exception(obj, exception):
    """Delete the field addressed by exception[0] from obj.

    A path is a tuple of dict keys. Any list met along the way is a wildcard:
    the rest of the path is applied to every element. So one exception can strip
    the field from all matching nodes (e.g. every creator). When exception[1] is
    given, only nodes whose value equals it are removed.
    """
    *steps, last = exception[0]
    has_value = len(exception) > 1
    exception_value = exception[1] if has_value else None

    def walk(node, steps):
        if isinstance(node, list):
            for item in node:  # a list addresses all elements
                walk(item, steps)
        elif steps:
            if isinstance(node, dict) and steps[0] in node:
                walk(node[steps[0]], steps[1:])  # descend one dict key
        elif isinstance(node, dict) and last in node:
            if not has_value or node[last] == exception_value:
                del node[last]  # reached a target — delete it

    walk(obj, steps)


def _prune_empty(node):
    """Recursively drop empty containers ({} / []) from node, in place.

    Walks the same dict/list/leaf structure as _remove_exception. After its
    children are pruned, any key/element whose value is an empty dict or list is
    removed, and that can cascade upward. Returns True if `node` itself is now an
    empty container (so its parent can drop it); scalars are never pruned.
    """
    if isinstance(node, dict):
        for key in list(node):  # snapshot: we mutate while iterating
            if _prune_empty(node[key]):
                del node[key]
        return not node
    if isinstance(node, list):
        for i in reversed(range(len(node))):  # reverse so deletions don't shift
            if _prune_empty(node[i]):
                del node[i]
        return not node
    return False  # leaf scalar — kept


def check_for_unmapped_data(field_name, field, exceptions=None):
    """Decorate a build_* method to flag what it left unmapped.

    Runs AFTER the method, i.e. on the source json the method has already
    destructively consumed. `field` names the source key to inspect (or is a
    callable returning the values). Declared `exceptions` paths are stripped
    from the live source first; whatever non-empty residue remains is recorded
    under `self.unmapped[field_name]`.
    """
    exceptions = exceptions or set()

    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            ret = func(self, *args, **kwargs)

            values = field(self) if isinstance(field, Callable) else self.nr.get(field)
            for exception in exceptions:
                if isinstance(values, list):
                    for v in values:
                        _remove_exception(v, exception)
                else:
                    _remove_exception(values, exception)

            # NOTE! explicit exception for organizational creators as there's no time to do this systematically
            if isinstance(values, list) and field_name == "creators":
                for idx, l in _reverse_iterate(values):
                    if "ico" in l:
                        del values[idx]

            leftovers = copy.deepcopy(values)
            all_mapped = _prune_empty(leftovers)
            if not all_mapped and leftovers is not None:
                self.unmapped[field_name] = leftovers
            return ret

        return wrapper

    return decorator


def _iter_leaves(node, path=()):
    """Yield (path, value) for every terminal value nested under dicts/lists.

    `path` is the tuple of dict keys walked to reach the leaf; list indices are
    omitted (a value's position inside a list isn't useful for "where did it
    come from"). `None`, empty strings and empty containers are skipped — they
    carry no data, so their absence in the target is never a loss.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in _VOCAB_NOISE:
                yield from _iter_leaves(v, path + (k,))
    elif isinstance(node, (list, tuple, set)):
        for v in node:
            yield from _iter_leaves(v, path)
    elif node is not None and node != "":
        yield path, node


def _value_key(v):
    """Normalize a leaf for comparison: stringify, strip, casefold.

    This lets an int id in the source match its stringified copy in the target,
    and ignores whitespace/case differences. It does NOT undo real transforms
    (language codes remapped, names split, dates reformatted) — those will still
    show up as misses, which is correct: the value as written in the source is
    genuinely not present verbatim in the target.
    """
    return str(v).strip().casefold()


def _vocab_leaves_with_path(obj, path=()):
    """Yield (path, value) for every meaning-bearing leaf of a source vocab entry.

    Bookkeeping keys (`_VOCAB_NOISE`) are skipped, and booleans are ignored —
    they're flags, never descriptive content we could lose.
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in _VOCAB_NOISE:
                yield from _vocab_leaves_with_path(v, path + (k,))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _vocab_leaves_with_path(v, path + (i,))
    elif isinstance(obj, bool):
        return
    elif obj is not None and obj != "":
        yield path, obj


def _delete_vocab_noise(obj):
    for k in _VOCAB_NOISE:
        obj.pop(k, None)


def _flag_unmapped_fields(converter: RecordDataConverter):
    """Flag every source field that has data but build() never mapped.

    Only fields with a truthy value are flagged (an empty/null field loses no
    data). Anything listed in EXCEPTIONS is treated as intentionally dropped.
    """
    for key in sorted(converter.rec.source):
        if key in MAPPED_FIELDS or key in EXCEPTIONS | TO_BE_DECIDED:
            continue
        if not converter.rec.source.get(key):
            continue  # present but empty — nothing lost
        converter.unmapped[key] = converter.rec.source[key]


# --------------------------------------------------------------------------- #
# the converter
# --------------------------------------------------------------------------- #


class RecordDataConverter:
    """Builds one datarepo record (self.rec.target) from one NR source json.

    The build_* methods consume self.nr destructively; whatever survives them
    ends up flagged in self.unmapped. Known/accepted oddities are collected in
    self.mapping_irregularities.
    """

    def __init__(self, src_json, look):
        self.metadata = {}
        self.rec = Record(src_json)
        self.nr = src_json
        self.look = look
        self.unmapped = {}
        self.mapping_irregularities = {}
        # Pristine copy — taken BEFORE the is_ancestor filtering below, so
        # original_src keeps the ancestor entries the migration drops.
        self.original_src = copy.deepcopy(src_json)

        self._filter_is_ancestor_entries("rights")
        self._filter_is_ancestor_entries("subjectCategories")

        self._original_data = copy.deepcopy(
            self.nr
        )  # debugger aid: post-filter snapshot

    def _filter_is_ancestor_entries(self, field):
        lst = self.nr.get(field) or []
        for idx, r in _reverse_iterate(lst):
            if r["is_ancestor"]:
                del lst[idx]

    def build(self):
        # Order is load-bearing: the methods consume self.nr destructively and
        # the decorators inspect what's left after each one. E.g.
        # build_publication_date only *reads* dateAvailable/dateCreated;
        # build_dates later pops them.
        self.build_titles()
        self.build_creators()
        self.build_publication_date()
        self.build_resource_type()
        self.build_languages()
        self.build_rights()
        self.build_subjects()
        self.build_keywords()
        self.build_publisher()
        self.build_contributors()
        self.build_descriptions()
        self.build_dates()
        self.build_funding()
        self.build_related()
        self.build_record()

        _flag_unmapped_fields(self)  # ensure nothing in the source was silently dropped
        return self.rec

    # --- vocabulary resolution ------------------------------------------- #

    def _resolve_vocab(
        self, field: str, vtype: str, vid: str | None, source=None, has_title=True
    ):
        """Resolve a vocabulary id to ({"id": ...} reference, full vocab json).

        Returns (None, None) when `vid` is missing or not present in the target
        `vtype` vocabulary — the caller decides how to flag/fall back, since the
        right message differs per field. `field` is documentation only: it names
        the target field for grep/debugging.

        When `source` (the original NR entry) is given, every meaning-bearing
        value in it that is present *anywhere* in the full target vocab record is
        deleted from the source (it is covered, nothing lost); bookkeeping noise
        is dropped too. What remains in the source is content the target vocab
        does not carry, and the unmapped-data check will surface it.
        """
        if not vid:
            return None, None
        vocab = self.look.record(vtype, vid)
        ref = self.look.ref(vtype, vid)
        if ref is None:
            MISSING_VOCAB_DATA["vtype"].add(
                vid
            )  # NOTE: literal "vtype" key, kept as in the original
            return None, None
        if has_title:
            ref["title"] = vocab["title"]
        if source is not None:
            target_vals = {_value_key(v) for _, v in _iter_leaves(vocab)}
            covered = {
                path
                for path, value in _vocab_leaves_with_path(source)
                if _value_key(value) in target_vals
            }
            _del_from_vocabs_multiple(source, covered)
            _delete_vocab_noise(source)
        return ref, vocab

    def _vocab_ref(
        self, field: str, vtype: str, vid: str | None, source=None, has_title=True
    ) -> dict | None:
        """Like _resolve_vocab, but returns just the reference (or None)."""
        ref, _ = self._resolve_vocab(field, vtype, vid, source, has_title)
        return ref

    def _vocab_ref_with_record(
        self, field: str, vtype: str, vid: str | None, source=None, has_title=True
    ):
        """Like _resolve_vocab; returns (ref, vocab json), (None, None) on a miss."""
        return self._resolve_vocab(field, vtype, vid, source, has_title)

    def _add_to_metadata(self, field, val):
        if val:
            if field in self.metadata and isinstance(self.metadata[field], list):
                self.metadata[field] += val
            elif field not in self.metadata:
                self.metadata[field] = val
            else:
                raise ValueError("wrong type for metadata field")

    # --- dates ------------------------------------------------------------ #

    def _validate_date(self, date):
        # TODO: use the correct ma field
        """
        from oarepo_runtime import current_runtime
        model = current_runtime.rdm_models[0]
        assert model.code == "datasets"
        schema_field = model.service_config.schema._declared_fields['metadata'].schema.declared_fields[
            'publication_date']
        """
        schema_field = EDTFDateString()
        if not date:
            return None
        try:
            d = schema_field.deserialize(date)
        except ValidationError:
            fixed = DATE_EXCEPTION_MAP.get(date) or cz_date_to_iso(date)
            d = schema_field.deserialize(fixed)
        assert d
        return d

    def _dtype(self, tid):
        return self._vocab_ref_with_record("metadata.dates", "datetypes", tid)

    def _process_date_interval(self, date_start, date_end, type_start, type_end):
        ret = []
        for date, type_id in ((date_start, type_start), (date_end, type_end)):
            ref, vocab = self._dtype(type_id)
            ret.append(
                {
                    "date": date,
                    "type": ref,
                    "description": _pick_in_preferred_lang(vocab["description"]),
                }
            )
        return ret

    def _parse_date(self, date, type_):
        assert type_ in ("dateCreated", "dateAvailable", "dateCollected")
        used_type = type_[4:]
        if not date:
            return []
        dates = None
        if isinstance(date, str) and "/" in date:
            split_dates = date.split("/")
            assert len(split_dates) == 2
            date = {"from": split_dates[0], "to": split_dates[1]}

        if isinstance(date, dict):
            assert len(date) == 2 and "from" in date and "to" in date
            frm = self._validate_date(date["from"])
            to = self._validate_date(date["to"])
            if frm and to:
                dates = {"from": frm, "to": to}
            elif not frm and not to:
                return []
            elif frm:
                date = frm
            elif to:
                date = to
        if dates:
            return self._process_date_interval(
                dates["from"], dates["to"], f"{used_type}Start", f"{used_type}End"
            )
        else:
            ref, vocab = self._dtype(used_type)
            return [
                {
                    "date": self._validate_date(date),
                    "type": ref,
                    "description": _pick_in_preferred_lang(vocab["description"]),
                }
            ]

    # --- people & organizations ------------------------------------------- #

    def _pop_leaf(self, src, key):
        assert not isinstance(src[key], (dict, list, tuple))
        return src.pop(key)

    def _person_or_org(self, entry):
        full = self._pop_leaf(entry, "fullName")
        type_ = self._pop_leaf(entry, "nameType").lower()
        assert full, "fullName is required"
        assert type_ in ("personal", "organizational")
        if type_ == "organizational":
            identifier = _get_from_mapping_tables("affiliations", entry["slug"])
            ref, vocab = self._vocab_ref_with_record(
                "affilation", "affiliations", identifier, entry, has_title=False
            )
            assert vocab["name"] == full
            return {
                "name": full,
                "type": "organizational",
                "identifiers": vocab["identifiers"],
            }

        fam, giv = _split_name(
            full
        )  # TODO: do we want this if the original doesn't have the split? - schema joins this
        p = {"name": full, "type": "personal", "family_name": fam}
        if giv:
            p["given_name"] = giv
        identifiers = []
        src_identifiers = entry.get("authorityIdentifiers", [])
        for idx, identifier in _reverse_iterate(src_identifiers):
            if identifier["scheme"] == "orcid":
                val = ORCID_RE.search(identifier["identifier"])
                if not val:  # some are nonsense
                    continue
                val = val.group(0)
                name_ref = self._vocab_ref(
                    "metadata.creators.person_or_org", "names", val, has_title=False
                )
                if not name_ref:
                    self.mapping_irregularities.setdefault(
                        "orcid_missing_in_vocabs", []
                    ).append(val)
                if "identifier" in identifier:
                    identifiers.append({"identifier": val, "scheme": "orcid"})
                    break
        # NOTE! we do not map other identifiers
        if "authorityIdentifiers" in entry:
            del entry["authorityIdentifiers"]

        p["identifiers"] = identifiers
        return p

    def _affiliations(self, affiliations: list | None) -> list:
        """Map source affiliation entries to AffiliationRelation dicts.

        affiliations = fields.List(fields.Nested(AffiliationRelationSchema))

        class AffiliationRelationSchema(ContribVocabularyRelationSchema):
            # invenio_vocabularies.contrib.affiliations.schema; vocab id XOR free-text name
            id = SanitizedUnicode()
            name = SanitizedUnicode()
            identifiers = IdentifierSet(fields.Nested(IdentifierSchema), dump_only=True)  # {identifier, scheme}
        """
        affiliations_list = []
        for a in affiliations or []:
            identifier = _get_from_mapping_tables("affiliations", a["slug"])
            ref, vocab = self._vocab_ref_with_record(
                "affilation", "affiliations", identifier, a, has_title=False
            )
            name = vocab["name"]
            affiliations_list.append({"name": name, **ref})  # Identifiers are dump only
        return affiliations_list

    def _person_org_with_affiliations(self, entry):
        person_or_org = self._person_or_org(entry)
        affiliations = self._affiliations(entry.get("affiliation"))
        return {"person_or_org": person_or_org, "affiliations": affiliations}

    def _contributor_role(self, entry):
        """Map the first source role to a vocab ref; flag any extra roles."""
        ret = None
        other_roles = []
        roles = entry["role"]
        reference_roles = {}
        for idx, role in _reverse_iterate(roles):
            slug = role["slug"]
            rid = _get_from_mapping_tables("contributorsroles", slug)
            role_ref, vocab = self._vocab_ref_with_record(
                "metadata.contributors", "contributorsroles", rid, source=role
            )
            reference_roles[slug] = role_ref

        for idx, (slug, ref) in enumerate(reference_roles.items()):
            if idx == 0:
                ret = ref
            else:
                other_roles.append(slug)
        if other_roles:
            self.mapping_irregularities["unmapped_contributor_roles"] = other_roles
        assert ret
        return ret

    def _contributor(self, entry):
        """
        contributors = fields.List(fields.Nested(ContributorSchema))

        class ContributorSchema(Schema):  # invenio_rdm_records...schemas.metadata.ContributorSchema
            person_or_org = fields.Nested(PersonOrOrganizationSchema, required=True)
            role = fields.Nested(VocabularySchema, required=True)
            affiliations = fields.List(fields.Nested(AffiliationRelationSchema))  # see _affiliations

        class PersonOrOrganizationSchema(Schema):
            type = SanitizedUnicode(required=True)  # "personal" | "organizational"
            name = SanitizedUnicode()
            given_name = SanitizedUnicode()
            family_name = SanitizedUnicode()
            identifiers = IdentifierSet(fields.Nested(IdentifierSchema))  # {identifier, scheme}

        class VocabularySchema(Schema):  # vocab relation; stored DB json additionally carries '@v'
            id = SanitizedUnicode(required=True)
            title = fields.Dict(dump_only=True)  # {lang_code: str}
        """
        return {
            **self._person_org_with_affiliations(entry),
            "role": self._contributor_role(entry),
        }

    # --- build_* methods, in build() call order ----------------------------- #

    @check_for_unmapped_data(
        "titles", "titles", exceptions={(("titleType",), "mainTitle")}
    )
    def build_titles(self):
        titles = self.nr.get("titles")
        main_title = None
        for title_entry in titles:
            if title_entry.get("titleType") == "mainTitle":
                title_i18nstr = title_entry["title"]
                main_title, lang = _pick_in_preferred_lang(
                    title_i18nstr, return_lang=True
                )  # translations are stored in AdditionalTitles
                del title_i18nstr[lang]
                if len(title_i18nstr) == 0:
                    titles.remove(title_entry)
                break
        assert main_title

        # remaining titles (incl. other languages of the main one) -> additional_titles
        """
        additional_titles = fields.List(fields.Nested(TitleSchema))

        class TitleSchema(Schema):  # invenio_rdm_records...schemas.metadata.TitleSchema
            title = SanitizedUnicode(required=True, validate=validate.Length(min=3))
            type = fields.Nested(VocabularySchema, required=True)  # titletypes
            lang = fields.Nested(VocabularySchema)                 # languages

        class VocabularySchema(Schema):  # vocab relation; stored DB json additionally carries '@v'
            id = SanitizedUnicode(required=True)
            title = fields.Dict(dump_only=True)  # {lang_code: str}
        """
        additional_titles = []
        for idx, title_entry in _reverse_iterate(titles):
            title_type = title_entry["titleType"]
            for lang, title_str in title_entry["title"].items():
                used_type = (
                    "translated-title" if title_type == "mainTitle" else title_type
                )
                type_ref = self._vocab_ref(
                    "metadata.additional_titles", "titletypes", used_type
                )
                lang_ref = self._vocab_ref(
                    "metadata.additional_titles", "languages", _lang_id(lang)
                )
                additional_titles.append(
                    {"type": type_ref, "title": title_str, "lang": lang_ref}
                )
            del titles[idx]

        self._add_to_metadata("title", main_title)
        self._add_to_metadata("additional_titles", additional_titles)

    @check_for_unmapped_data(
        "creators",
        "creators",
        exceptions={
            *AFFILIATIONS_LEFTOUTS,
        },
    )
    def build_creators(self):
        """
        creators = fields.List(fields.Nested(CreatorSchema))

        class CreatorSchema(Schema):  # invenio_rdm_records...schemas.metadata.CreatorSchema
            person_or_org = fields.Nested(PersonOrOrganizationSchema, required=True)
            role = fields.Nested(VocabularySchema)  # optional here, required for contributors
            affiliations = fields.List(fields.Nested(AffiliationRelationSchema))  # see _affiliations

        # PersonOrOrganizationSchema / VocabularySchema: see _contributor
        """
        creators = self.nr.get("creators")
        processed_creators = [self._person_org_with_affiliations(c) for c in creators]
        self._add_to_metadata("creators", processed_creators)

    # TODO: make sure the decision logic for which date is publication is correct or whether some of it should be decided manually
    def build_publication_date(self):
        # Reads dateAvailable/dateCreated non-destructively — build_dates pops them later.
        def _pick(date_list):
            if len(date_list) == 1:
                return date_list[0]["date"]
            if len(date_list) == 2:
                return date_list[1]["date"]
            assert False

        pubdate = None
        available = self._parse_date(
            self.nr.get("dateAvailable", None), "dateAvailable"
        )
        created = self._parse_date(self.nr.get("dateCreated", None), "dateCreated")
        if available:
            pubdate = _pick(available)
        elif created:
            pubdate = _pick(created)
        if pubdate:  # checked later to not duplicate the is published check
            self._add_to_metadata("publication_date", pubdate)

    @check_for_unmapped_data(
        "resourceType", "resourceType", exceptions={(("altLabels",),)}
    )
    def build_resource_type(self):
        resource_types = self.nr.get("resourceType")
        assert len(resource_types) == 1
        assert (
            resource_types[0]["links"]["self"]
            == "https://data.narodni-repozitar.cz/2.0/taxonomies/resourceType/datasets"
        )
        resource_type = resource_types[0]
        resource_type_id = MAPPING_TABLES["resourcetypes"][
            "datasets"
        ]  # whatever everything is datasets here
        resource_type_ref = self._vocab_ref(
            "metadata.resource_type",
            "resourcetypes",
            resource_type_id,
            source=resource_type,
        )
        self._add_to_metadata("resource_type", resource_type_ref)

    @check_for_unmapped_data("language", "language", exceptions={*LANGUAGE_LEFTOUTS})
    def build_languages(self):
        """
        languages = fields.List(fields.Nested(VocabularySchema))

        class VocabularySchema(Schema):  # vocab relation; stored DB json additionally carries '@v'
            id = SanitizedUnicode(required=True)
            title = fields.Dict(dump_only=True)  # {lang_code: str}
        """
        langs = []
        for l in self.nr.get("language") or []:
            lid = _get_from_mapping_tables("languages", l["slug"])
            ref = self._vocab_ref("metadata.languages", "languages", lid, source=l)
            langs.append(ref)
        self._add_to_metadata("languages", langs)

    @check_for_unmapped_data(
        "rights",
        "rights",
        exceptions={
            (("slug",),),
            (("noTick",),),  # wtf is this
            (("tickable",),),
        },
    )
    def build_rights(self):
        """
        rights = fields.List(fields.Nested(RightsSchema))

        class RightsSchema(Schema):  # invenio_rdm_records...schemas.metadata.RightsSchema
            # validates: existing id XOR free-text title/description/link, never both
            id = SanitizedUnicode()
            title = fields.Dict()        # {lang_code: str}, single locale allowed
            description = fields.Dict()  # {lang_code: str}, single locale allowed
            icon = fields.Str(dump_only=True)
            props = fields.Nested(PropsSchema)  # {url, scheme}
            link = SanitizedUnicode()  # must be a valid URL
        """
        rights = []
        for r in self.nr.get("rights") or []:
            rid = _get_from_mapping_tables(
                "licenses", r["slug"]
            )  # rights seem to be in all caps
            ref, vocab = self._vocab_ref_with_record(
                "metadata.rights", "licenses", rid, source=r
            )
            _set_if_present(ref, "description", vocab, "description")

            _set_if_present(ref, "link", r, "relatedURI.URL", del_from_source=True)
            rights.append(ref)

        self._add_to_metadata("rights", rights)

    @check_for_unmapped_data(
        "subjectCategories", "subjectCategories", exceptions={(("slug",),)}
    )
    def build_subjects(self):
        """
        subjects = fields.List(fields.Nested(SubjectRelationSchema))

        class SubjectRelationSchema(ContribVocabularyRelationSchema):
            # invenio_vocabularies.contrib.subjects.schema; vocab id XOR free-text subject
            id = SanitizedUnicode()
            subject = SanitizedUnicode()
            scheme = SanitizedUnicode(dump_only=True)
            title = fields.Dict(dump_only=True)
            props = fields.Dict(dump_only=True)
            identifiers = IdentifierSet(fields.Nested(IdentifierSchema))  # {identifier, scheme}
        """
        subjects = []
        for sc in self.nr.get("subjectCategories"):
            id_ = _get_from_mapping_tables("subjectcategories", sc["slug"])
            ref, vocab = self._vocab_ref_with_record(
                "metadata.subjects", "subjectcategories", id_, source=sc
            )
            subjects.append(
                {"id": id_, "subject": _pick_in_preferred_lang(vocab["title"])}
            )
        self._add_to_metadata("subjects", subjects)

    def build_publisher(self):
        """publisher is just a single string in the target."""
        pubs = self.nr.get("publisher")
        if isinstance(pubs, list) and pubs: # TODO: CCMM allows only one publisher
            assert "fullName" in pubs[0]
            pn = pubs[0]["fullName"] # TODO: person_or_org to str mapping required
            self.metadata["publisher"] = pn
        elif isinstance(pubs, str):
            self.metadata["publisher"] = pubs
        if len(pubs) > 1:
            self.mapping_irregularities["publisher_multiple"] = pubs[1:]

    @check_for_unmapped_data(
        "contributors",
        "contributors",
        exceptions={*CONTRIBUTOR_ROLE_LEFTOUTS, *AFFILIATIONS_LEFTOUTS},
    )
    def build_contributors(self):
        contributors = [
            a for c in self.nr.get("contributors", []) if (a := self._contributor(c))
        ]
        self._add_to_metadata("contributors", contributors)

    def _get_descriptions(self):
        # descriptions (abstract / methods / technicalInfo / technicalNotes / notes) #series-of-information; table-of-contents
        ret = {}
        for fld, dtype in _DESCRIPTION_FIELDS.items():
            block = self.nr.get(fld)
            if block:
                ret[dtype] = (block, fld)
        return ret

    @check_for_unmapped_data("descriptions", lambda self: self._get_descriptions())
    def build_descriptions(self):
        """
        additional_descriptions = fields.List(fields.Nested(DescriptionSchema))

        class DescriptionSchema(Schema):  # invenio_rdm_records...schemas.metadata.DescriptionSchema
            description = SanitizedHTML(required=True, validate=validate.Length(min=3))
            type = fields.Nested(VocabularySchema, required=True)  # descriptiontypes
            lang = fields.Nested(VocabularySchema)                 # languages

        class VocabularySchema(Schema):  # vocab relation; stored DB json additionally carries '@v'
            id = SanitizedUnicode(required=True)
            title = fields.Dict(dump_only=True)  # {lang_code: str}
        """
        descriptions = []
        for dtype, (block, original_dtype) in self._get_descriptions().items():
            type_ref = self._vocab_ref(
                "metadata.additional_descriptions", "descriptiontypes", dtype
            )
            if isinstance(block, dict):  # multilingual {cs,en,...}
                for lg, val in block.items():
                    if not val:
                        continue
                    d = {"description": val, "type": type_ref}
                    lang = _lang_id(
                        lg
                    ).upper()  # TODO: the lg here is not the same as slug and i'm not completely sure this maps correctly
                    lang_ref = self._vocab_ref(
                        "metadata.additional_descriptions", "languages", lang
                    )
                    d["lang"] = lang_ref
                    descriptions.append(d)
            elif isinstance(block, str):
                descriptions.append({"description": block, "type": type_ref})
            elif isinstance(block, list):
                for el in block:
                    if not el:
                        continue
                    descriptions.append({"description": el, "type": type_ref})
            else:
                assert False, f"Unexpected type for {original_dtype}: {type(block)}"
            del self.nr[original_dtype]

        self._add_to_metadata("additional_descriptions", descriptions)

    @check_for_unmapped_data(
        "dates",
        lambda self: [
            d
            for d in [
                self.nr.get("dateAvailable"),
                self.nr.get("dateCreated"),
                self.nr.get("dateCollected"),
            ]
            if d
        ],
    )
    def build_dates(self):
        # dates (available / created / collected; collected ranges split) ---------
        """
        dates = fields.List(fields.Nested(DateSchema))

        class DateSchema(Schema):  # invenio_rdm_records...schemas.metadata.DateSchema
            date = EDTFDateTimeString(required=True)  # EDTF date or interval
            type = fields.Nested(VocabularySchema, required=True)  # datetypes
            description = fields.Str()

        class VocabularySchema(Schema):  # vocab relation; stored DB json additionally carries '@v'
            id = SanitizedUnicode(required=True)
            title = fields.Dict(dump_only=True)  # {lang_code: str}
        """
        dates = []
        dates += self._parse_date(self.nr.pop("dateAvailable", None), "dateAvailable")
        dates += self._parse_date(self.nr.pop("dateCreated", None), "dateCreated")
        dates += self._parse_date(self.nr.pop("dateCollected", None), "dateCollected")
        self._add_to_metadata("dates", dates)

    @check_for_unmapped_data(
        "funding", "fundingReferences", exceptions={*FUNDER_LEFTOUTS}
    )
    def build_funding(self):
        """
        funding = fields.List(fields.Nested(FundingSchema))

        class FundingSchema(Schema):  # invenio_rdm_records...schemas.metadata.FundingSchema
            funder = fields.Nested(FunderRelationSchema, required=True)
            award = fields.Nested(AwardRelationSchema)

        class FunderRelationSchema(ContribVocabularyRelationSchema):  # vocab id XOR free-text name
            id = SanitizedUnicode()
            name = SanitizedUnicode(validate=validate.Length(min=1))

        class AwardRelationSchema(Schema):  # vocab id XOR free-text number/title
            id = SanitizedUnicode()
            number = SanitizedUnicode()
            title = i18n_strings  # {lang_code: str}
            identifiers = IdentifierSet(fields.Nested(IdentifierSchema))  # {identifier, scheme}
            acronym = SanitizedUnicode()
            program = SanitizedUnicode()
            # NB: award 'subjects'/'organizations' from the old jsonschema live on the full
            # Award vocab schema only, not on this relation schema
        """
        funding = []
        frs = self.nr.get("fundingReferences") or []
        for idx, fr in _reverse_iterate(frs):
            entry: dict[str, Any] = {}
            funders = fr.get("funder") if fr.get("funder") else None
            if funders:
                assert len(funders) == 1
                funder = funders[0]
                fname = (
                    funder["fullName"]
                    if "fullName" in funder
                    else _pick_in_preferred_lang(funder["title"])
                )
                slug = funder["slug"]
                identifier = _get_from_mapping_tables("funders", slug)
                funder_ref, vocab = self._vocab_ref_with_record(
                    "funders", "funders", identifier, funder, has_title=False
                )
                entry["funder"] = {"name": fname, **funder_ref}

            award: dict[str, Any] = {}
            assert fr.get("projectID") or fr.get("projectName")
            project_id = clean(fr.get("projectID"))
            project_name = clean(fr.get("projectName"))
            funding_program = clean(fr.get("fundingProgram"))

            if project_id == "ER 341/20-1":
                project_name = "Deutsche Forschungsgemeinschaft"

            award_title = AWARD_TABLE[(project_id, project_name, funding_program)][
                "projectTitle"
            ]
            if project_name:
                award["title"] = award_title
            if project_id:
                award["number"] = fr["projectID"]
            if funding_program:
                award["program"] = fr["fundingProgram"]
            del fr["fundingProgram"]
            del fr["projectID"]
            del fr["projectName"]
            entry["award"] = award
            if entry:
                funding.append(entry)

        self._add_to_metadata("funding", funding)

    def _create_related_resource(self, related_resource_data, resource_type_id):
        ret = {}
        ret["publication_date"] = related_resource_data.pop("itemYear")
        ret["title"] = related_resource_data.pop("itemTitle")
        ret["identifiers"] = related_resource_data.pop("itemPIDs")
        ret["creators"] = [
            self._person_org_with_affiliations(c)
            for c in related_resource_data["itemCreators"]
        ]
        ret["resource_type"] = self._vocab_ref(
            "metadata.resource_type", "resourcetypes", resource_type_id
        )
        return ret

    @check_for_unmapped_data(
        "relatedItems",
        "relatedItems",
        exceptions={
            (("itemRelationType", "hint"),),
            (("itemRelationType", "pair"),),
            (
                ("itemResourceType", "title"),
            ),  # different values in new vocabs, taken from them
            (("itemResourceType", "coarType"),),
            (("itemResourceType", "nuslType"),),  # do we want to do something with this
            (("itemResourceType", "relatedURI", "COAR"),),  # - mapped to resource type
            (("itemURL",),),
        },
    )
    def build_related(self):
        # related items -> related_identifiers (have a PID/URL) / related_resources
        """
        related_identifiers = fields.List(fields.Nested(RelatedIdentifierSchema))

        class RelatedIdentifierSchema(IdentifierSchema):
            # invenio_rdm_records...schemas.metadata.RelatedIdentifierSchema
            identifier = SanitizedUnicode(required=True)
            scheme = SanitizedUnicode(required=True)
            relation_type = fields.Nested(VocabularySchema)  # relationtypes; validated as required
            resource_type = fields.Nested(VocabularySchema)  # resourcetypes

        class VocabularySchema(Schema):  # vocab relation; stored DB json additionally carries '@v'
            id = SanitizedUnicode(required=True)
            title = fields.Dict(dump_only=True)  # {lang_code: str}
        """
        rel_ids, rel_res = [], []

        for related_item in self.nr.get("relatedItems") or []:
            item_relation_types = related_item.get("itemRelationType")
            item_resource_types = related_item.get("itemResourceType")
            assert len(item_relation_types) == 1
            assert len(item_resource_types) == 1
            item_relation_type = item_relation_types[0]
            item_resource_type = item_resource_types[0]

            slug = item_relation_type["links"]["self"].rstrip("/").split("/")[-1]
            relation_type = _get_from_mapping_tables("relationtypes", slug)

            resource_type = _get_id_from_coar_related_uri(
                item_resource_type["relatedURI"]
            )
            del item_resource_type["relatedURI"]

            related_resource = self._create_related_resource(
                related_item, resource_type
            )
            rel_res.append(related_resource)

            def _add_vocab_references(e, relation_source, resource_source):
                if relation_type:
                    e["relation_type"] = self._vocab_ref(
                        "metadata.related",
                        "relationtypes",
                        relation_type,
                        source=relation_source,
                    )
                if resource_type:
                    e["resource_type"] = self._vocab_ref(
                        "metadata.related",
                        "resourcetypes",
                        resource_type,
                        source=resource_source,
                    )
                return e

            if related_resource["identifiers"]:
                for p in related_resource["identifiers"]:
                    rel_ids.append(
                        _add_vocab_references(
                            {"identifier": p["identifier"], "scheme": p["scheme"]},
                            item_relation_types[0],
                            item_resource_types[0],
                        )
                    )
            elif related_item.get("itemURL"):
                rel_ids.append(
                    _add_vocab_references(
                        {"identifier": related_item["itemURL"], "scheme": "url"},
                        item_relation_types[0],
                        item_resource_types[0],
                    )
                )

        self._add_to_metadata("related_identifiers", rel_ids)
        self._add_to_metadata("related_resources", rel_res)

    @check_for_unmapped_data("keywords", "keywords")
    def build_keywords(self):
        # CCMM docs: subjects - "Collection of subjects (keywords, concepts, classification codes) curated by a single source.,
        keywords_set = set()
        for idx, kw in _reverse_iterate(self.nr.get("keywords") or []):
            if isinstance(kw, dict):
                for lang, val in kw.items():
                    if val:
                        keywords_set.add(val)
            elif isinstance(kw, str):
                assert kw
                keywords_set.add(kw)
            elif isinstance(kw, list):
                pass
            else:
                assert False, f"Unexpected type for keyword: {type(kw)}"
            del self.nr.get("keywords")[idx]
        self._add_to_metadata("subjects", [{"subject": text} for text in keywords_set])

    def build_record(self):
        """Non-metadata parts of the record: access, state, files."""
        ar_code = None
        for ar in self.nr.get("accessRights") or []:
            ar_code = _get_id_from_coar_related_uri(ar.get("relatedURI"))
            break
        if ar_code == "c_abf2":
            access = {"record": "public", "files": "public"}
        elif (
            ar_code == "c_f1cf"
        ):  # embargoed — RDM has no embargoed state, no date in source
            access = {"record": "public", "files": "restricted"}
        elif ar_code == "c_16ec":
            access = {"record": "restricted", "files": "restricted"}
        else:
            self.mapping_irregularities["access_rights_code"] = (
                f"access rights {ar_code!r} not in target vocab"
            )
            access = {"record": "restricted", "files": "restricted"}

        access["embargo"] = {"until": None, "active": False, "reason": None}

        self.record_data = {"access": access}


def convert_old_catchall_metadata(metadata, look):
    """"""
    converter = RecordDataConverter(metadata, look)
    converter.build()
    return converter, converter.metadata, converter.record_data
