import json
import os
from pathlib import Path

import boto3
import click
from tqdm import tqdm

from .db_vocab_lookups import _LOOKUP
from .migrate_refactored import convert_old_catchall_metadata
from .models import AccountsUser, FilesFiles, RecordsMetadata

old_catchall_s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ["OLD_CATCHALL_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["OLD_CATCHALL_S3_SECRET_ACCESS_KEY"],
    endpoint_url=os.environ["OLD_CATCHALL_S3_ENDPOINT_URL"],
)
old_catchall_bucket_name = os.environ["OLD_CATCHALL_S3_BUCKET_NAME"]


def convert_record_metadata(record_metadata):
    converter, metadata = convert_old_catchall_metadata(record_metadata, _LOOKUP)
    return metadata


def lookup_s3_path(session, file_id, file_key, record_id, is_draft):
    s3_path = session.query(FilesFiles).get(file_id).uri.replace("s3://nr_pilot/", "")
    try:
        old_catchall_s3.head_object(Bucket=old_catchall_bucket_name, Key=s3_path)
        return s3_path
    except Exception as e:
        click.secho(
            f"    Failed to lookup S3 path for {'draft' if is_draft else 'published'} record {record_id}, file {file_key}, s3 path {s3_path}: {e}",
            fg="red",
        )
        return None


def convert_record(session, record_id, record_uuid, record_metadata, created, updated):
    owner_id = record_metadata["oarepo:ownedBy"]
    owner = session.query(AccountsUser).get(owner_id)
    user_identity = owner.oauthclient_useridentity[0].id
    community = record_metadata.get("oarepo:primaryCommunity", None)
    if community == "general":
        community = None
    is_draft = record_metadata.get(
        "oarepo:draft", False
    )  # TODO: The one record in "approved" state, not editing or published state would not resolve as draft; just for info

    files = [
        {
            "key": f["key"],
            "s3": lookup_s3_path(session, f["file_id"], f["key"], record_id, is_draft),
            "checksum": f["checksum"],
            "size": f["size"],
            "mimetype": f.get("mime_type"),
        }
        for f in record_metadata.get("_files", [])
    ]
    total_files_size = sum(f["size"] for f in files)
    converter, metadata, record_data = convert_old_catchall_metadata(
        record_metadata, _LOOKUP
    )
    if community in ("generic", "general"):
        community = None

    converted_record = {
        "id": record_id,
        "owner": user_identity,
        "community": community,
        "is_draft": is_draft,
        "files": files,
        "metadata": metadata,
        "access": record_data["access"],
        "created": created.isoformat(),
        "updated": updated.isoformat(),
        "total_files_size": total_files_size,
    }
    return converted_record


def export_records(session, output_dir, split=None):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_converted = []

    for record in tqdm(
        session.query(RecordsMetadata), total=session.query(RecordsMetadata).count()
    ):
        if not record.json:
            # deleted record
            continue
        record_id = f"datst.{record.json['InvenioID']}"
        converted_record = convert_record(
            session,
            record_id,
            record.id,
            record.json,
            record.created,
            record.updated,
        )
        all_converted.append(
            (
                record_id,
                converted_record,
            )
        )

    all_converted.sort(key=lambda x: x[1]["total_files_size"])

    if split:
        output_directories = [output_path / f"split_{i + 1}" for i in range(int(split))]
        for directory in output_directories:
            directory.mkdir(parents=True, exist_ok=True)
    else:
        output_directories = [output_path]

    idx = 0
    for record_id, converted_record in all_converted:
        record_path = output_directories[idx] / f"{record_id}.json"
        with open(record_path, "w") as f:
            json.dump(converted_record, f, ensure_ascii=False, indent=2)
        idx = (idx + 1) % len(output_directories)
