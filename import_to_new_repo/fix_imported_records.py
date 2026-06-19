import sys
from pathlib import Path
from typing import cast

import click
from flask import current_app
from invenio_access.permissions import system_identity
from invenio_rdm_records.services.services import RDMRecordService
from oarepo_runtime import current_runtime
from oarepo_runtime.typing import record_from_result

from import_to_new_repo.records import (
    load_records_to_memory,
    prepare_record,
)


def fix_record_metadata(identifier: str, fixed_metadata: dict):
    record_service: RDMRecordService = cast(
        "RDMRecordService", current_runtime.models["datasets"].service
    )

    # make sure that the record exists and is not deleted
    record_service.read(identity=system_identity, id_=identifier)

    # get the draft and update its metadata
    draft_record = record_service.edit(
        identity=system_identity, id_=identifier
    ).to_dict()

    draft_metadata = draft_record["metadata"]

    # 1. fix publisher
    draft_metadata["publisher"] = fixed_metadata.get(
        "publisher", draft_metadata["publisher"]
    )

    # 2. fix keywords
    draft_metadata["subjects"] = fixed_metadata.get(
        "subjects", draft_metadata["subjects"]
    )

    # save the updated metadata
    draft_record = record_from_result(
        record_service.update_draft(
            identity=system_identity, id_=identifier, data=draft_record
        )
    )

    # assign doi
    if "doi" in draft_record.pids:
        click.secho("    DOI already registered, skipping", fg="yellow")
    else:
        click.secho(f"    Registering DOI {identifier}", fg="yellow")
        click.secho(f"    Existing pids, {draft_record.pids}", fg="green")
        draft_record = record_from_result(
            record_service.pids.create(system_identity, identifier, "doi")
        )
        click.secho(f"    DOI recorded, {draft_record.pids}", fg="green")

    # re-publish the corrected draft. This will also take care about registration to the datacite
    record_service.publish(identity=system_identity, id_=identifier)


def fix_imported_records(records_dir: str, identifiers_to_fix: list[str]):
    records = load_records_to_memory(Path(records_dir), identifiers_to_fix)
    for record in records:
        prepare_record(record)

    for record in records:
        try:
            fix_record_metadata(record["id"], record["metadata"])
        except Exception as e:
            print(f"Failed to fix record {record['id']}: {e}")


if __name__ == "__main__":
    try:
        current_app.config.get("test")
    except:  # noqa E722
        raise Exception("This file needs to be run via invenio shell")
    # add the directory of the file to the python path, so that we can import from import_to_new_repo
    sys.path.append(str(Path(__file__).parent.parent))

    fix_imported_records(sys.argv[1], sys.argv[2:])
