# Steps to convert data to catchall

## Export to json data

### Import database into this tool

1. Run docker compose up, import the database dump into the postgres container

```bash
psql -h localhost -p 5832 -U catchall -W catchall <nr_data_prod_sql_dump-2026-05-21.sql
Password: catchall
```

2. Go to https://perun.e-infra.cz/organizations/3880/members, open devtools, set page size to 1000 and 
   capture getMembersPage request. Save its output to exported_data/nr_members_input.json

3. Run the export script

```bash
./export.sh
```

This command creates:
- `exported_data/users.yaml`
- `exported_data/communities.yaml`
- `exported_data/roles.yaml`

## Import into datarepo.eosc.cz

Run the import script:

```bash
./import.sh
```

This command imports the exported data into the datarepo.eosc.cz instance.

`IMPORTER_PATH` is the path to the `old-catchall-importer` directory.

```bash
export IMPORTER_PATH=$(pwd)
```

### Synchronize all communities

Run the following commands:

```bash
python ${IMPORTER_PATH}/import_to_new_repo/communities.py
invenio einfra synchronize_all_communities
```

### Create users

Run the following command:

```bash
python ${IMPORTER_PATH}/import_to_new_repo/create_users.py
```

### Link users to e-infra accounts

Run the following command:

```bash
invenio shell ${IMPORTER_PATH}/import_to_new_repo/link_users.py
```
