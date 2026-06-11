import datetime
import sys

import click
import yaml
from flask import current_app
from invenio_access.permissions import system_identity
from invenio_communities.members.errors import AlreadyMemberError
from invenio_communities.proxies import current_communities
from invenio_db import db
from invenio_oauthclient.models import RemoteAccount, UserIdentity
from oarepo_oidc_einfra.proxies import current_einfra_oidc

EINFRA_APP = "e-infra"


def create_user(email):
    click.secho(
        f"Adding user {email} ...",
        nl=False,
        fg="cyan",
    )
    datastore = current_app.extensions["security"].datastore
    user = datastore.get_user_by_email(email)
    if user:
        click.secho(" already exists", fg="green")
        return user

    datastore.create_user(
        email=email,
        active=True,
        confirmed_at=datetime.datetime.now(datetime.UTC),
    )
    db.session.commit()
    click.secho(" created", fg="green")
    return datastore.get_user_by_email(email)


def create_einfra_link(user, identities, extra_data):
    click.secho(f"  linking user {user.email} to einfra ...", fg="cyan", nl=False)
    if not identities:
        click.secho(
            f"  WARNING: user {user.email} has no identities, skipping",
            fg="yellow",
        )
        return
    if len(identities) != 1:
        click.secho(
            f"  WARNING: user {user.email} has {len(identities)} identities, skipping",
            fg="yellow",
        )
        return
    einfra_identity = identities[0]

    user_identity = (
        db.session.query(UserIdentity)
        .filter_by(id_user=user.id, method=EINFRA_APP)
        .first()
    )
    if not user_identity:
        db.session.add(
            UserIdentity(id_user=user.id, method=EINFRA_APP, id=einfra_identity)
        )
        db.session.commit()

    remote_account = (
        db.session.query(RemoteAccount)
        .filter_by(user_id=user.id, client_id=EINFRA_APP)
        .first()
    )
    if not remote_account:
        db.session.add(
            RemoteAccount(user_id=user.id, client_id=EINFRA_APP, extra_data=extra_data)
        )
        db.session.commit()
    click.secho("  done", fg="green")


def import_users(users_file):
    users = yaml.safe_load(open(users_file))
    for user_data in users:
        user = create_user(user_data["email"])
        create_einfra_link(user, user_data["identities"], user_data["extra_data"] or {})


if __name__ == "__main__":
    import_users(sys.argv[1])
