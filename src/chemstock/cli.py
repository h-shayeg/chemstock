"""Command line tools.

Example: python -m chemstock.cli create-user alice --role admin
"""

import argparse
import sys
from getpass import getpass

from sqlalchemy.orm import Session

from chemstock.db import get_engine
from chemstock.roles import Role
from chemstock.users import UserError, create_user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m chemstock.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser(
        "create-user", help="create a user (the password is asked interactively)"
    )
    create.add_argument("username")
    create.add_argument(
        "--role", choices=[role.value for role in Role], default=Role.MEMBER.value
    )
    args = parser.parse_args(argv)

    password = getpass("Password: ")
    if password != getpass("Repeat password: "):
        print("Error: the passwords do not match.", file=sys.stderr)
        return 1

    with Session(get_engine()) as session:
        try:
            user = create_user(session, args.username, password, args.role)
        except UserError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        print(f"Created {user.role} '{user.username}' (id {user.id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
