#!/usr/bin/env python3
"""
DataPulse Secure Administrator Initialization & Promotion CLI Script.

Usage:
    python scripts/init_admin.py --password "SecurePass123!"
    python scripts/init_admin.py --promote
    python scripts/init_admin.py --email datapulseapplication@gmail.com --password "SecurePass123!"

Security note:
    Never hardcode passwords into source control. You may also set the
    ADMIN_INITIAL_PASSWORD environment variable instead of passing --password.
"""
import sys
import os
import argparse
import getpass

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.database import init_db
from app.services.admin_bootstrap import create_or_promote_admin, promote_user_to_admin, normalize_email


def main():
    parser = argparse.ArgumentParser(description="Initialize or promote DataPulse administrator account.")
    parser.add_argument("--email", default=None, help="Administrator email (defaults to configured ADMIN_EMAIL)")
    parser.add_argument("--password", default=None, help="Password for admin account (or set ADMIN_INITIAL_PASSWORD env var)")
    parser.add_argument("--full-name", default="Platform Administrator", help="Full name for the administrator account")
    parser.add_argument("--promote", action="store_true", help="Promote existing user to admin without changing password")

    args = parser.parse_args()

    # Ensure tables and migrations are up to date
    init_db()

    target_email = normalize_email(args.email or getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com"))
    configured_email = normalize_email(getattr(settings, "ADMIN_EMAIL", "datapulseapplication@gmail.com"))

    if target_email != configured_email:
        print(f"Error: Target email '{target_email}' does not match configured ADMIN_EMAIL '{configured_email}'.", file=sys.stderr)
        sys.exit(1)

    if args.promote:
        promoted = promote_user_to_admin(target_email)
        if promoted:
            print(f"Successfully promoted existing user '{target_email}' to Administrator (is_admin=1).")
            sys.exit(0)
        else:
            print(f"Error: User '{target_email}' was not found in the database. Use --password to create the account.", file=sys.stderr)
            sys.exit(1)

    password = args.password or os.environ.get("ADMIN_INITIAL_PASSWORD")
    if not password and sys.stdin.isatty():
        password = getpass.getpass("Enter password for administrator account: ")

    if not password:
        print("Error: Password is required to create or update admin account. Provide via --password or ADMIN_INITIAL_PASSWORD.", file=sys.stderr)
        sys.exit(1)

    try:
        res = create_or_promote_admin(
            email=target_email,
            password=password,
            full_name=args.full_name
        )
        print(f"Administrator account '{res['email']}' successfully {res['action']} with user ID: {res['id']}.")
        print("Administrative status verified: is_admin = 1")
    except Exception as e:
        print(f"Error during administrator bootstrap: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
