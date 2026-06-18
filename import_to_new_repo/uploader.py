import os

import boto3
import click
import requests

READ_SIZE = 1024 * 1024  # 1 MB per read


class SizedStreamReader:
    """Iterable with a known length so requests sends Content-Length, not chunked encoding."""

    def __init__(self, stream, size):
        self._stream = stream
        self._size = size

    def __len__(self):
        return self._size

    def __iter__(self):
        remaining = self._size
        while remaining > 0:
            chunk = self._stream.read(min(READ_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def upload_single_part(args):
    part_url, s3_path, stream_start_pos, chunk_size, part_md5 = args
    # this is a standalone function so that it can be called with a multiprocessing pool

    for current_try in range(3):
        try:
            old_catchall_bucket_name = os.getenv("OLD_CATCHALL_S3_BUCKET_NAME")

            old_catchall_s3 = boto3.client(
                "s3",
                aws_access_key_id=os.getenv("OLD_CATCHALL_S3_ACCESS_KEY"),
                aws_secret_access_key=os.getenv("OLD_CATCHALL_S3_SECRET_ACCESS_KEY"),
                endpoint_url=os.getenv("OLD_CATCHALL_S3_ENDPOINT_URL"),
            )

            response = old_catchall_s3.get_object(
                Bucket=old_catchall_bucket_name,
                Key=s3_path,
                Range=f"bytes={stream_start_pos}-{stream_start_pos + chunk_size - 1}",
            )
            object_stream = response["Body"]

            resp = requests.put(
                part_url,
                data=SizedStreamReader(object_stream, chunk_size),
                headers={"Content-MD5": part_md5},
            )
            if resp.status_code != 200:
                click.secho(
                    f"    Failed to upload part: {resp.status_code} {resp.text}",
                    fg="red",
                )
                click.secho(resp.text, fg="red")
            resp.raise_for_status()
            return chunk_size
        except Exception as e:
            click.secho(f"    Failed to upload part: {e}", fg="red")
            if current_try == 2:
                click.secho("    Giving up after 3 attempts", fg="red")
                raise RuntimeError(str(e))
            else:
                click.secho(f"    Retrying... ({current_try + 1}/3)", fg="yellow")
                continue
