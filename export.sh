#!/usr/bin/env bash

set -euo pipefail

IMPORTER_PATH=$(dirname "$0")

if [ ! -d "${IMPORTER_PATH}/.venv" ] ; then
    # install the dependencies
    (cd "${IMPORTER_PATH}"; uv venv; uv pip install -e .)
fi

# activate the virtual environment
source "${IMPORTER_PATH}"/.venv/bin/activate


if [ -z "${OLD_CATCHALL_S3_ACCESS_KEY}" ]; then
    echo "OLD_CATCHALL_S3_ACCESS_KEY is not set"
    exit 1
fi
if [ -z "${OLD_CATCHALL_S3_SECRET_ACCESS_KEY}" ]; then
    echo "OLD_CATCHALL_S3_SECRET_ACCESS_KEY is not set"
    exit 1
fi
if [ -z "${OLD_CATCHALL_S3_BUCKET_NAME}" ]; then
    echo "OLD_CATCHALL_S3_BUCKET_NAME is not set"
    exit 1
fi
if [ -z "${OLD_CATCHALL_S3_ENDPOINT_URL}" ]; then
    echo "OLD_CATCHALL_S3_ENDPOINT_URL is not set"
    exit 1
fi

# export users
catchall-export users

# export records
catchall-export records --split 4
