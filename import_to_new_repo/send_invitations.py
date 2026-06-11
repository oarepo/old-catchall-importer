"""
This script will create and send invitations for all users in the exported_data/users.yaml

This action can not be taken back when started !!!
"""

import sys
from pathlib import Path

import click
from invenio_access.permissions import system_identity
from invenio_communities.members import MemberService
from invenio_communities.proxies import current_communities
from yaml import safe_load


def invite_user(user):
    member_service: MemberService = current_communities.service.members
    for community_slug, role in user.get("communities", {}).items():
        click.secho(
            f"Inviting {user['email']} to community {community_slug} as {role}",
            fg="cyan",
        )
        try:
            community = current_communities.service.read(
                system_identity, community_slug
            )
            if not community:
                click.secho(
                    f"Community {community_slug} not found, skipping.", fg="red"
                )
                continue
            member_service.invite(
                system_identity,
                community.id,
                {
                    "members": [{"type": "email", "id": user["email"]}],
                    "role": role,
                },
            )
            click.secho(
                f"Invited {user['email']} to community {community_slug} as {role}",
                fg="green",
            )
        except Exception as e:
            import traceback

            traceback.print_exc()
            click.secho(
                f"Failed to invite user {user['email']} to community {community_slug}: {e}",
                fg="red",
            )


def send_invitations(path_to_users: str):
    users = safe_load(Path(path_to_users).read_text())
    click.secho(
        f"\n\nThis command will send invitations to all users (total {len(users)}) that are present in the exported data.\n"
        "It will send mails and can not be taken back.\n\n"
        "Are you sure you want to continue?",
        fg="red",
    )
    if not click.confirm("Continue?"):
        return
    for user in users:
        invite_user(user)


if __name__ == "__main__":
    send_invitations(sys.argv[1])
