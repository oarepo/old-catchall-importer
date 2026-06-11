#!/usr/bin/env bash

set -euo pipefail

IMPORTER_PATH=$(dirname "$0")

if [ ! -d "${IMPORTER_PATH}/.venv" ] ; then
    # install the dependencies
    (cd "${IMPORTER_PATH}"; uv venv; uv pip install -e .)
fi

# activate the virtual environment
source "${IMPORTER_PATH}"/.venv/bin/activate

# export users
catchall-export users

# export records
catchall-export records
