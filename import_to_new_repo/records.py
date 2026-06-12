"""

Load records from a JSON file and import them into the new repository.

This command needs to be called with invenio shell, not directly.

Record representation:
    {
        "id": "id of the record"
        "owner": "eppn of the owner",
        "community": "slug of the community",
        "doi": "assigned doi of the record",
        "metadata": {...},
    }

"""

import base64
import contextlib
import datetime
import hashlib
import json
import os
import sys
import traceback
from collections import Counter
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import boto3
import click
import requests
from alembic.command import current
from datasets.model import datasets_model
from flask import current_app
from invenio_access.permissions import system_identity
from invenio_accounts.models import User, UserIdentity
from invenio_communities.communities.records.models import CommunityMetadata
from invenio_db import db
from invenio_rdm_records.records.api import RDMDraft, RDMRecord
from invenio_records_resources.services.files.schema import FileSchema
from oarepo_runtime.proxies import current_runtime
from oarepo_runtime.typing import record_from_result
from sqlalchemy import text
from tqdm import tqdm

MULTIPART_CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB

preassigned_record_id = ContextVar("preassigned_record_id")

old_catchall_s3 = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("OLD_CATCHALL_S3_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("OLD_CATCHALL_S3_SECRET_ACCESS_KEY"),
    endpoint_url=os.getenv("OLD_CATCHALL_S3_ENDPOINT_URL"),
)
old_catchall_bucket_name = os.getenv("OLD_CATCHALL_S3_BUCKET_NAME")


def prepare_record(record):
    """Prepare a record for import."""
    owner = record["owner"]

    user_identity = db.session.query(UserIdentity).filter_by(id=owner).first()
    if user_identity is None:
        raise ValueError(f"UserIdentity not found for owner: {owner}")
    record["owner_id"] = str(user_identity.id_user)

    community_slug = record["community"]
    if community_slug is not None:
        community = (
            db.session.query(CommunityMetadata).filter_by(slug=community_slug).first()
        )
        if community is None:
            raise ValueError(f"Community not found for slug: {community_slug}")
        record["community_id"] = str(community.id)
    else:
        record["community_id"] = None

    doi = record.get("doi")
    if doi:
        record["doi"] = str(doi)


# TODO: restricted records !!!


def load_records_to_memory(
    records_dir: Path, identifiers_to_import: list[str]
) -> list[dict[str, Any]]:
    records = []
    for fn in records_dir.glob("*.json"):
        if identifiers_to_import and fn.name[:-5] not in identifiers_to_import:
            continue
        records.append(json.loads(fn.read_text()))
    return records


def patch_pid_field():
    """
    Patch pid fields in record and draft classes.

    The pid field will always take the pid from the context var, never mint its own.
    """
    record_cls: RDMRecord = datasets_model.Record
    draft_cls: RDMDraft = datasets_model.Draft

    print(record_cls, record_cls.pid.field._provider)
    print(draft_cls, draft_cls.pid.field._provider)

    class RecordIdFromContextProvider(record_cls.pid.field._provider):
        """A pid provider that always returns id from a contextvar."""

        @classmethod
        def generate_id(cls, options=None):
            """Generate record id."""
            return preassigned_record_id.get()

    class DraftIdFromContextProvider(draft_cls.pid.field._provider):
        """A pid provider that always returns id from a contextvar."""

        @classmethod
        def generate_id(cls, options=None):
            """Generate record id."""
            return preassigned_record_id.get()

    record_cls.pid.field._provider = RecordIdFromContextProvider
    draft_cls.pid.field._provider = DraftIdFromContextProvider


def load_records(record_service, record_id):
    published_record = None
    draft_record = None
    with contextlib.suppress(Exception):
        published_record = record_from_result(
            record_service.read(system_identity, record_id)
        )
        click.secho("    Found already published record", fg="yellow")
    if published_record is None:
        with contextlib.suppress(Exception):
            draft_record = record_from_result(
                record_service.read_draft(system_identity, record_id)
            )
            click.secho("    Found a draft record", fg="yellow")
    return published_record, draft_record


def assign_community_to_draft(draft_record, record_dict):
    draft_parent_rec = draft_record.parent
    community_id = record_dict.get("community_id")
    if community_id:
        if community_id in draft_parent_rec.communities:
            click.secho(
                f"    Community {community_id} already in record, skipping",
                fg="yellow",
            )
        else:
            click.secho(
                f"    Adding to {record_dict['community']} community",
                fg="yellow",
            )

            draft_parent_rec.communities.add(community_id)
            draft_parent_rec.communities.default = community_id

            draft_parent_rec.commit()
            db.session.commit()


def set_draft_owner(draft_record, record_dict):
    draft_parent_rec = draft_record.parent

    access = draft_parent_rec.access
    if access.owner and str(access.owner.owner_id) == str(record_dict["owner_id"]):
        click.secho(
            f"    Owner already set to {record_dict['owner']} ({db.session.query(User).get(record_dict['owner_id'])})",
            fg="yellow",
        )
    else:
        access.owner = {"user": record_dict["owner_id"]}
        click.secho(
            f"    Setting owner to {record_dict['owner']} ({db.session.query(User).get(record_dict['owner_id'])})",
            fg="yellow",
        )
        draft_parent_rec.commit()
        db.session.commit()


def assign_doi(record_service, draft_record, record_dict):
    if "doi" in draft_record.pids:
        click.secho("    DOI already registered, skipping", fg="yellow")
    else:
        click.secho(f"    Registering DOI {record_dict['doi']}", fg="yellow")
        click.secho(f"    Existing pids, {draft_record.pids}", fg="green")
        draft_record = record_from_result(
            record_service.pids.create(system_identity, record_dict["id"], "doi")
        )
        click.secho(f"    DOI recorded, {draft_record.pids}", fg="green")


def make_draft_record(record_service, draft_record, record_dict):
    if draft_record is None:
        click.secho("    Creating a new draft record", fg="yellow")
        draft_record = record_from_result(
            record_service.create(
                system_identity,
                {
                    "metadata": record_dict["metadata"],
                    "access": record_dict["access"],
                },
            )
        )
    if record_dict.get("community"):
        assign_community_to_draft(draft_record, record_dict)
    set_draft_owner(draft_record, record_dict)
    if record_dict.get("doi"):
        assign_doi(record_service, draft_record, record_dict)
    upload_files(record_service, draft_record, record_dict)

    return draft_record


class FileLimiter(object):
    def __init__(self, file_obj, read_limit):
        self.read_limit = read_limit
        self.amount_seen = 0
        self.file_obj = file_obj

        # So that requests doesn't try to chunk the upload but will instead stream it:
        self.len = read_limit

    def read(self, amount=-1):
        if self.amount_seen >= self.read_limit:
            return b""
        remaining_amount = self.read_limit - self.amount_seen
        if amount < 0 or amount > remaining_amount:
            amount = remaining_amount
        data = self.file_obj.read(min(amount, 120000))
        self.amount_seen += len(data)
        return data


def encode_digest(digest) -> str:
    """Encode to base64 as expected by s3 Content-MD5 header"""
    return base64.b64encode(digest).decode("utf-8")


def compute_checksum(
    s3_path, expected_size, pass_no, total_passes, chunk_size
) -> tuple[str, tuple[tuple[str, str, str], ...]] | None:
    """
    For each chunk, compute md5, sha256, sha512 and return as tuples"""
    ret = []
    total_md5 = hashlib.md5()

    try:
        response = old_catchall_s3.get_object(
            Bucket=old_catchall_bucket_name, Key=s3_path
        )["Body"]

        with tqdm(
            total=expected_size,
            unit="B",
            unit_scale=True,
            leave=False,
            desc=f"Computing (part) checksums (pass {pass_no} / {total_passes})",
        ) as pbar:
            size = 0
            while True:
                f = FileLimiter(response, chunk_size)
                md5 = hashlib.md5()
                sha256 = hashlib.sha256()
                sha512 = hashlib.sha512()

                chunk_size = 0
                while True:
                    chunk = f.read(120000)
                    if not chunk:
                        break
                    total_md5.update(chunk)
                    md5.update(chunk)
                    sha256.update(chunk)
                    sha512.update(chunk)
                    chunk_size += len(chunk)
                    pbar.update(len(chunk))
                if chunk_size == 0:
                    break
                if chunk_size != min(chunk_size, expected_size - size):
                    raise ValueError(
                        f"Expected chunk size {min(chunk_size, expected_size - size)}, got {chunk_size}"
                    )
                ret.append(
                    (
                        encode_digest(md5.digest()),
                        encode_digest(sha256.digest()),
                        encode_digest(sha512.digest()),
                    )
                )
                size += chunk_size

            if size != expected_size:
                raise ValueError(
                    f"Expected size for {s3_path} {expected_size}, got {size}"
                )
            return (total_md5.hexdigest(), tuple(ret))
    except Exception as e:
        click.secho(f"        Failed to compute checksum for {s3_path}: {e}", fg="red")
        return None


def compute_saved_checksum(stream, expected_size):
    md5 = hashlib.md5()
    size = 0
    with tqdm(
        total=expected_size,
        unit="B",
        unit_scale=True,
        leave=False,
        desc="Computing saved file checksum",
    ) as pbar:
        while chunk := stream.read(120000):
            md5.update(chunk)
            size += len(chunk)
            pbar.update(len(chunk))
    return md5.hexdigest()


def upload_single_file(
    record_service, draft_record, file_key, s3_path, md5_checksum, expected_size
):

    # determine whether to use multipart upload
    is_multipart = expected_size > MULTIPART_CHUNK_SIZE
    chunk_size = MULTIPART_CHUNK_SIZE
    n_parts = 1

    while (n_parts := (expected_size + chunk_size - 1) // chunk_size) > 10000:
        chunk_size *= 2

    click.secho(
        f"        multipart upload: {is_multipart}, chunk size {chunk_size}, n_parts {n_parts}",
        fg="yellow",
    )

    # pre-flight - download the file from S3 and check the checksum
    # we do not have checksums everywhere, so let's compute them 5 times and check they match
    n_checksums = 2
    checksums = {
        compute_checksum(s3_path, expected_size, pass_no + 1, n_checksums, chunk_size)
        for pass_no in range(n_checksums)
    }
    if len(checksums) > 1:
        raise ValueError(f"Checksum mismatch: {checksums}")

    computed_checksums = list(checksums)[0]
    if computed_checksums is None:
        raise ValueError(f"Failed to compute checksum for {s3_path}")

    md5_checksum, chunk_checksums = computed_checksums

    if len(chunk_checksums) != n_parts:
        raise ValueError(
            f"Expected {n_parts} chunk checksums, got {len(chunk_checksums)}"
        )

    response = old_catchall_s3.get_object(Bucket=old_catchall_bucket_name, Key=s3_path)
    object_stream = response["Body"]

    click.secho(
        f"        uploading to the repository, checksum {md5_checksum}", fg="yellow"
    )
    initialized = record_service.draft_files.init_files(
        system_identity,
        draft_record["id"],
        [
            {
                "key": file_key,
                "size": expected_size,
                "checksum": "md5:" + md5_checksum,
                "transfer": {
                    "type": "M" if is_multipart else "L",
                    "parts": n_parts,
                    "part_size": chunk_size,
                },
            }
        ],
    ).to_dict()["entries"][0]
    if is_multipart:
        upload_via_multipart(
            initialized, chunk_size, object_stream, expected_size, chunk_checksums
        )
    else:
        record_service.draft_files.set_file_content(
            system_identity,
            draft_record["id"],
            file_key,
            object_stream,
        )
    committed_record = record_from_result(
        record_service.draft_files.commit_file(
            system_identity, draft_record["id"], file_key
        )
    )

    # download the record's file content and check the checksum again
    try:
        with record_service.draft_files.get_file_content(
            system_identity, committed_record["id"], file_key
        ).open_stream(mode="rb") as stream:
            saved_checksum = compute_saved_checksum(stream, expected_size)
            if saved_checksum != md5_checksum:
                raise ValueError(
                    f"Saved checksum mismatch: expected {md5_checksum}, got {saved_checksum}"
                )
    except:
        record_service.draft_files.delete_file(
            system_identity,
            draft_record["id"],
            file_key,
        )
        raise


def upload_via_multipart(
    initialized, chunk_size, object_stream, expected_size, chunk_checksums
):
    size = 0
    for part_metadata, chunk_checksum in tqdm(
        zip(initialized["links"]["parts"], chunk_checksums),
        total=len(chunk_checksums),
        leave=False,
        unit="part",
    ):
        part_url = part_metadata["url"]
        current_chunk_size = min(chunk_size, expected_size - size)
        size += upload_single_part(
            part_url, object_stream, current_chunk_size, chunk_checksum[0]
        )
        if size == expected_size:
            break


def upload_single_part(part_url, object_stream, chunk_size, part_md5):
    resp = requests.put(
        part_url,
        data=FileLimiter(object_stream, chunk_size),
        headers={"Content-MD5": part_md5, "Content-Length": str(chunk_size)},
    )
    if resp.status_code != 200:
        click.secho(
            f"    Failed to upload part: {resp.status_code} {resp.text}", fg="red"
        )
        click.secho(resp.text, fg="red")
    resp.raise_for_status()
    return chunk_size


def upload_files(record_service, draft_record, record_dict):
    for file_data in record_dict.get("files", []):
        file_key = file_data.get("key")
        s3_path = file_data.get("s3")
        checksum = file_data.get("checksum")
        size = file_data.get("size")

        if s3_path is None:
            click.secho(f"    Skipping {file_key}, file does not exist on s3", fg="red")
            continue

        click.secho(f"    Uploading file '{file_key}' ({size} bytes)", fg="yellow")

        if file_key in draft_record.files:
            dumped_file = FileSchema().dump(draft_record.files[file_key])
            click.secho(
                f"        File already exists, status: {dumped_file['status']}",
                fg="yellow",
            )

            if dumped_file["status"] == "completed":
                click.secho(
                    f"        Skipping {file_key}, already uploaded", fg="yellow"
                )
                continue

            # partially uploaded, remove the file
            record_service.draft_files.delete_file(
                system_identity, draft_record["id"], file_key
            )

        for attempt in range(3):
            try:
                upload_single_file(
                    record_service, draft_record, file_key, s3_path, checksum, size
                )
                break
            except Exception as e:
                if attempt == 2:
                    raise
                import traceback

                traceback.print_exc()
                click.secho(f"        Upload failed: {e}, retrying...", fg="yellow")


def publish_record(record_service, draft_record):
    click.secho(f"    Publishing record {draft_record['id']}", fg="yellow")
    return record_from_result(
        record_service.publish(system_identity, draft_record["id"])
    )


def set_timestamps(record_service, published_record, created, updated):
    click.secho(
        f"    Checking timestamp of {published_record['id']} {created} {updated}",
        fg="yellow",
    )
    parsed_created = datetime.datetime.fromisoformat(created).replace(
        tzinfo=datetime.timezone.utc
    )
    parsed_updated = datetime.datetime.fromisoformat(updated).replace(
        tzinfo=datetime.timezone.utc
    )
    if (
        published_record.created != parsed_created
        or published_record.updated != parsed_updated
    ):
        click.secho("        Setting timestamp", fg="yellow")
        # we need to update the timestamps using a direct database update, otherwise the orm hook will overwrite it
        db.session.execute(
            text(
                "UPDATE datasets_metadata SET created = :created, updated = :updated WHERE id = :id"
            ),
            {
                "created": parsed_created,
                "updated": parsed_updated,
                "id": published_record.id,
            },
        )
        db.session.commit()
        record_service.indexer.index(published_record)


def upload_record(record_dict):
    click.secho(f"Creating record with pid {record_dict['id']}", fg="cyan")
    record_service = current_runtime.models["datasets"].service
    with preassigned_record_id.set(record_dict["id"]):
        published_record, draft_record = load_records(record_service, record_dict["id"])
        if published_record is None:
            draft_record = make_draft_record(record_service, draft_record, record_dict)
            published_record = publish_record(record_service, draft_record)
        set_timestamps(
            record_service,
            published_record,
            record_dict["created"],
            record_dict["updated"],
        )

    click.secho("    All done", fg="green")


def import_records(records_dir: str, identifiers_to_import: list[str]):
    records = load_records_to_memory(Path(records_dir), identifiers_to_import)
    for record in records:
        prepare_record(record)

    patch_pid_field()

    status_stream = open(f"status-{datetime.datetime.now().isoformat()}.log", "w")
    for record in records:
        if record["is_draft"]:
            print(f"SKIPPED-DRAFT: {record['id']}", file=status_stream, flush=True)
            continue
        if record["access"]["files"] != "public":
            print(
                f"CHECK-RESTRICTED-FILES-AFTER-IMPORT: {record['id']}",
                file=status_stream,
                flush=True,
            )
            if record["access"]["record"] != "public":
                print(
                    f"CHECK-RESTRICTED-RECORD-AFTER-IMPORT: {record['id']}",
                    file=status_stream,
                    flush=True,
                )
        try:
            upload_record(record)
            print(f"SUCCESS: {record['id']}", file=status_stream, flush=True)
        except Exception:
            print(f"FAILURE: {record['id']}", file=status_stream, flush=True)
            traceback.print_exc()
    status_stream.close()


if __name__ == "__main__":
    try:
        current_app.config.get("test")
    except:  # noqa E722
        raise Exception("This file needs to be run via invenio shell")
    import_records(sys.argv[1], sys.argv[2:])
