#
# Copyright (C) 2024 CESNET z.s.p.o.
#
# oarepo-oidc-einfra  is free software; you can redistribute it and/or
# modify it under the terms of the MIT License; see LICENSE file for more
# details.
#
"""Low-level API for Perun targeted at the operations needed by E-INFRA OIDC extension."""

from __future__ import annotations

import json
from pathlib import Path

import click
import yaml


def export_eppns():
    input_path = Path("exported_data/nr_members_input.json")
    output_path = Path("exported_data/eppn_mapping.yaml")

    all_members = json.loads(input_path.read_text())

    mapping_table = {}
    for member in all_members["data"]:
        user_id = member["user"]["id"]
        for attr in member["userExtSources"]:
            if attr["extSource"]["name"] == "https://login.e-infra.cz/idp/":
                eppn = attr["login"]
                mapping_table[eppn] = {
                    "user_id": user_id,
                    "first_name": member["user"]["firstName"],
                    "last_name": member["user"]["lastName"],
                }
                break
        else:
            click.secho(f"No EPPN found for user {user_id}", fg="red")

    yaml.safe_dump(mapping_table, output_path.open("w"), allow_unicode=True)
