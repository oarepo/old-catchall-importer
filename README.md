# Steps to convert data to catchall

## Export to json data

### Import database into this tool

1. Run docker compose up, import the database dump into the postgres container

```bash
psql -h localhost -p 5832 -U catchall -W catchall <nr_data_prod_sql_dump-2026-05-21.sql
Password: catchall
```

2. Set the following environment variables:

```bash
export OLD_CATCHALL_S3_ACCESS_KEY=
export OLD_CATCHALL_S3_SECRET_ACCESS_KEY=
export OLD_CATCHALL_S3_BUCKET_NAME=
export OLD_CATCHALL_S3_ENDPOINT_URL=
```

3. Run the export script

```bash
./export.sh
```

This command creates:
- `exported_data/users.yaml`
- `exported_data/communities.yaml`
- `exported_data/roles.yaml`
- `exported_data/eppn_mapping.yaml`
- `exported_data/records`

## Import into datarepo.eosc.cz

1. Copy this repository **with** the `exported_data` directory to the web container.

`IMPORTER_PATH` is the path to the `old-catchall-importer` directory.

```bash
export IMPORTER_PATH=$(pwd)
```

2. Run the import script inside the web container. If running locally, it needs to be run from the repository root
with the virtualenv activated. 

```bash
${IMPORTER_PATH}/import.sh
```

This command imports the exported data into the datarepo.eosc.cz instance.

## Invite users to e-infra

Inside the web container, run the following commands:

```bash
invenio shell ${IMPORTER_PATH}/import_to_new_repo/send_invitations.py  ${IMPORTER_PATH}/exported_data/users.yaml
```

Note: please check it on a single user before running it on all users !!!
