"""Command line tools.

Examples:
    python -m chemstock.cli create-user alice --role admin
    python -m chemstock.cli set-owner alice
"""

import argparse
import sys
from getpass import getpass

from sqlalchemy.orm import Session

from chemstock.db import get_engine
from chemstock.roles import Role
from chemstock.users import UserError, create_user, set_owner


def _create_user(args: argparse.Namespace) -> int:
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


def _set_owner(args: argparse.Namespace) -> int:
    with Session(get_engine()) as session:
        try:
            user, previous = set_owner(session, args.username)
        except UserError as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
        print(f"'{user.username}' is now the owner.")
        if previous is not None:
            print(f"The previous owner '{previous}' is now an admin.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m chemstock.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser(
        "create-user", help="create a user (the password is asked interactively)"
    )
    create.add_argument("username")
    create.add_argument(
        "--role",
        choices=[role.value for role in Role if role is not Role.OWNER],
        default=Role.MEMBER.value,
    )

    owner = commands.add_parser(
        "set-owner", help="make an existing user the owner (the one main admin)"
    )
    owner.add_argument("username")

    args = parser.parse_args(argv)
    if args.command == "create-user":
        return _create_user(args)
    return _set_owner(args)


if __name__ == "__main__":
    raise SystemExit(main())
