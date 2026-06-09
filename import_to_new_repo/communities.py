"""
Import the communities to actual Invenio instance
"""

import subprocess
import sys
from pathlib import Path

import yaml


def import_communities(path_to_communities_yaml):
    community_data = yaml.safe_load(Path(path_to_communities_yaml).open())
    for community_name, details in community_data.items():
        subprocess.check_call(
            ["invenio", "communities", "create", community_name, details["description"]]
        )


if __name__ == "__main__":
    import_communities(sys.argv[1])
