"""Register a shortcode (and optionally grant a user access to it).

A small operational helper until the Phase 7 admin API/UI lands. A shortcode must be
registered here before anyone (including admins) can extract it.

    python -m app.scripts.shortcode_add --code 8890 --name "Client 8890"
    python -m app.scripts.shortcode_add --code 8890 --name "Client 8890" --grant analyst@example.com
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.db.models.user import User
from app.db.session import get_session_factory
from app.scripts.seed import grant_shortcode, upsert_shortcode


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Register a shortcode (optionally grant a user).")
    p.add_argument("--code", required=True, help="Shortcode value, e.g. 8890 (matches source_addr).")
    p.add_argument("--name", default=None, help="Human-friendly name.")
    p.add_argument("--description", default=None)
    p.add_argument("--grant", default=None, help="Email of a user to grant access to.")
    args = p.parse_args(argv)

    db = get_session_factory()()
    try:
        sc = upsert_shortcode(db, args.code, args.name or f"Client {args.code}", args.description)
        print(f"Shortcode registered: {sc.code} ({sc.name})")

        if args.grant:
            user = db.scalar(select(User).where(User.email == args.grant))
            if user is None:
                print(f"User not found: {args.grant}")
                return 2
            grant_shortcode(db, user, sc)
            print(f"Granted {sc.code} to {user.email}")

        db.commit()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
