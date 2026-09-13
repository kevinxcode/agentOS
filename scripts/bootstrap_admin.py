#!/usr/bin/env python3
"""Create the sole admin using a prompt or AGENTOS_BOOTSTRAP_PASSWORD_FILE.

Run with the API environment: uv run --project services/api python scripts/bootstrap_admin.py
--email admin@example.com. Passwords are never accepted as command-line arguments.
"""

import argparse
import asyncio
import getpass
import os
from pathlib import Path
from typing import NoReturn

from sqlalchemy import select

from agentos.auth.models import AdminUser
from agentos.auth.service import BootstrapError, bootstrap_admin
from agentos.config import get_settings
from agentos.db import create_database


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage()
        self.exit(2, "unrecognized arguments or invalid usage; use --help\n")


def read_password() -> str:
    password_file = os.environ.get("AGENTOS_BOOTSTRAP_PASSWORD_FILE")
    if password_file:
        with Path(password_file).open(encoding="utf-8") as stream:
            contents = stream.read()
        if contents.endswith("\r\n"):
            password = contents[:-2]
        elif contents.endswith(("\r", "\n")):
            password = contents[:-1]
        else:
            password = contents
        if "\r" in password or "\n" in password or not 12 <= len(password) <= 1024:
            raise BootstrapError("Password must contain 12 to 1024 characters on one line")
        return password
    return getpass.getpass("Administrator password: ")


async def run(email: str) -> bool:
    database = create_database(get_settings().database_url)
    try:
        async with database.session_factory() as db:
            existing = await db.scalar(select(AdminUser))
            password = None if existing is not None else read_password()
            return await bootstrap_admin(db, email, password)
    finally:
        await database.close()


def main() -> int:
    parser = SafeArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    try:
        created = asyncio.run(run(args.email))
    except BootstrapError as error:
        print(str(error))
        return 1
    except Exception:
        # Configuration/driver exceptions can embed credentials or connection strings.
        print("Bootstrap failed; check configuration and database availability")
        return 1
    print(
        "Administrator created; TOTP enrollment is required"
        if created
        else "Administrator exists"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
