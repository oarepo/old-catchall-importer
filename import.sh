#!/usr/bin/env bash

set -euo pipefail

IMPORTER_PATH=$(dirname "$0")

# check that invenio is installed
invenio --help &>/dev/null || { echo "invenio command not available. Please call from within the invenio virtual environment."; exit 1; }

IMPORT_COMMUNITIES=true
IMPORT_USERS=true

# iterate args
for arg in "$@"; do
    case $arg in
        --skip-communities)
            IMPORT_COMMUNITIES=false
            ;;
        --skip-users)
            IMPORT_USERS=false
            ;;
        --help)
            echo "Usage: $0 [--skip-communities] [--skip-users]"
            exit 0
            ;;
        *)
            echo "Usage: $0 [--skip-communities] [--skip-users]"
            exit 0
            ;;
    esac
done


if [ $IMPORT_COMMUNITIES == 'true' ] ; then
    # import communities
    echo "Importing communities..."
    python ${IMPORTER_PATH}/import_to_new_repo/communities.py "${IMPORTER_PATH}/exported_data/communities.yaml"

    # synchronize communities to einfra to make sure groups are created inside Perun
    echo "Synchronizing communities to einfra..."
    invenio einfra synchronize_all_communities
fi

# note: there is only "admin" role in the old system, so we don't need to import roles

if [ $IMPORT_USERS == 'true' ] ; then
    # import users
    echo "Importing users..."
    invenio shell ${IMPORTER_PATH}/import_to_new_repo/users.py "${IMPORTER_PATH}/exported_data/users.yaml"

    # invenio rdm rebuild-all-indices
    # read -r -p "Press Enter when workers show no activity..."
fi

if [ $IMPORT_RECORDS == 'true' ] ; then
    # import records
    echo "Importing records..."
    invenio shell ${IMPORTER_PATH}/import_to_new_repo/records.py ${IMPORTER_PATH}/exported_data/records/
fi

echo "All done!"
