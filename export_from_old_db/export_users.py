import click
from yaml import safe_dump

from .models import AccountsRole, AccountsUser

SKIPPED_COMMUNITIES = {"general"}


def export_users(session):
    click.secho("Exporting communities ...", fg="blue")
    role_data = []
    community_data = {}
    community_map = {}
    for role in session.query(AccountsRole).order_by("id").all():
        if role.name.startswith("community:"):
            _, community_name, community_role = role.name.split(":")
            community_map[role.id] = (community_name, community_role)
            community_data[community_name] = {
                "name": community_name,
                "description": (role.description or "")
                .rsplit("-", maxsplit=1)[0]
                .strip(),
            }
        else:
            role_data.append(
                {
                    "id": role.id,
                    "name": role.name,
                    "description": (role.description or "").strip(),
                }
            )
    safe_dump(role_data, open("exported_data/roles.yaml", "w"))
    click.secho(f"Roles exported successfully ({len(role_data)} roles)", fg="green")

    safe_dump(community_data, open("exported_data/communities.yaml", "w"))
    click.secho(
        f"Communities exported successfully ({len(community_data)} communities)",
        fg="green",
    )

    click.secho("Exporting users...", fg="blue")

    user_list = []
    for user in session.query(AccountsUser).order_by("id").all():
        user_roles = get_user_roles(user.role, community_map)
        user_communities, is_general_submitter = get_user_community_roles(
            user.role, community_map
        )
        if is_general_submitter:
            user_roles.append("submitter")

        if not user_roles and not user_communities:
            continue

        user_data = {
            "id": user.id,
            "email": user.email,
            "active": user.active,
            "identities": [identity.id for identity in user.oauthclient_useridentity],
            "extra_data": next(
                iter(
                    [account.extra_data for account in user.oauthclient_remoteaccount]
                ),
                None,
            ),
        }
        if user_roles:
            user_data["roles"] = user_roles
        if user_communities:
            user_data["communities"] = user_communities
        user_list.append(user_data)

    safe_dump(
        user_list, open("exported_data/users.yaml", "w"), default_flow_style=False
    )
    click.secho(f"Users exported successfully ({len(user_list)} users)", fg="green")


def get_user_roles(roles, community_map):
    return [role.id for role in roles if role.id not in community_map]


community_role_mapping = {
    "member": "member",
    "publisher": "submitter",
    "curator": "curator",
}

community_role_levels = {
    "member": 1,
    "submitter": 2,
    "curator": 3,
}


def get_user_community_roles(roles, community_map):
    community_roles = {}
    is_general_submitter = False

    for role in roles:
        if role.id not in community_map:
            continue
        community_name = community_map[role.id][0]
        original_community_role = community_map[role.id][1]
        mapped_community_role = community_role_mapping[original_community_role]

        if community_name in SKIPPED_COMMUNITIES:
            if mapped_community_role == "submitter":
                is_general_submitter = True
            continue

        if (
            community_name not in community_roles
            or community_role_levels[mapped_community_role]
            > community_role_levels[community_roles[community_name]]
        ):
            community_roles[community_name] = mapped_community_role

    return community_roles, is_general_submitter
