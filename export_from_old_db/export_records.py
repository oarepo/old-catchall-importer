import json
import os
from pathlib import Path

import boto3
import click
from tqdm import tqdm

from .db_vocab_lookups import _LOOKUP
from .migrate_refactored import convert_metadata
from .models import AccountsUser, FilesFiles, RecordsMetadata


old_catchall_s3 = boto3.client(
    "s3",
    aws_access_key_id=os.environ["OLD_CATCHALL_S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["OLD_CATCHALL_S3_SECRET_ACCESS_KEY"],
    endpoint_url=os.environ["OLD_CATCHALL_S3_ENDPOINT_URL"],
)
old_catchall_bucket_name = os.environ["OLD_CATCHALL_S3_BUCKET_NAME"]


def convert_record_metadata(record_metadata):
    converter, metadata = convert_metadata(record_metadata, _LOOKUP)
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


def export_record(
    session, record_id, record_uuid, record_metadata, created, updated, output_path
):
    owner_id = record_metadata["oarepo:ownedBy"]
    owner = session.query(AccountsUser).get(owner_id)
    user_identity = owner.oauthclient_useridentity[0].id
    community = record_metadata.get("oarepo:primaryCommunity", None)
    if community == "general":
        community = None
    is_draft = record_metadata.get("oarepo:draft", False) # TODO: The one record in "approved" state, not editing or published state would not resolve as draft; just for info

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
    converted_record = {
        "id": record_id,
        "owner": user_identity,
        "community": community,
        "is_draft": is_draft,
        "files": files,
        "metadata": convert_record_metadata(record_metadata),
        "created": created.isoformat(),
        "updated": updated.isoformat(),
    }
    with open(output_path, "w") as f:
        json.dump(converted_record, f, ensure_ascii=False, indent=2)


def export_records(session, output_dir):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for record in tqdm(
        session.query(RecordsMetadata), total=session.query(RecordsMetadata).count()
    ):
        if not record.json:
            # deleted record
            continue
        record_id = f"datst.{record.json['InvenioID']}"
        record_path = output_path / f"{record_id}.json"
        export_record(
            session,
            record_id,
            record.id,
            record.json,
            record.created,
            record.updated,
            record_path,
        )
