import click

from export_from_old_db.export_eppns import export_eppns

from .db import get_session
from .export_users import export_users


@click.group()
def cli():
    """Main CLI group."""
    pass


@cli.command(name="users")
def _export_users():
    """Export users from the old database."""
    with get_session() as session:
        export_users(session)


@cli.command(name="eppns")
def _export_eppns():
    """Export EPPNs from the old database."""
    export_eppns()
