"""Interactive 2FA bootstrap for Picnic.

Usage (once per installation):
    python -m app.services.picnic.setup

Reads credentials and the token path from Settings, i.e. from the .env file
(PICNIC_MAIL or PICNIC_EMAIL, PICNIC_PASSWORD, PICNIC_COUNTRY_CODE,
PICNIC_TOKEN_PATH) or real env vars. Performs the full login flow, handles 2FA
by prompting on stdin, and writes the resulting auth token to the configured
token path (default /data/picnic_token.json; for local dev set
PICNIC_TOKEN_PATH=./.picnic_token.json in .env).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from python_picnic_api2 import PicnicAPI, Picnic2FAError, Picnic2FARequired

from app.config import get_settings


def main() -> int:
    settings = get_settings()
    email = settings.picnic_email
    password = settings.picnic_password
    country = settings.picnic_country_code or "DE"

    if not email or not password:
        print("error: set PICNIC_MAIL and PICNIC_PASSWORD in the environment", file=sys.stderr)
        return 2

    print(f"logging in as {email} ({country})...")
    api = PicnicAPI(country_code=country)
    try:
        api.login(email, password)
        print("login succeeded without 2FA")
    except Picnic2FARequired:
        print("2FA required. choose channel [SMS/EMAIL] (default SMS): ", end="", flush=True)
        channel = (input().strip().upper() or "SMS")
        api.generate_2fa_code(channel=channel)
        print(f"code sent via {channel}. enter code: ", end="", flush=True)
        code = input().strip()
        try:
            api.verify_2fa_code(code)
        except Picnic2FAError as e:
            print(f"verify failed: {e}", file=sys.stderr)
            return 1
        print("2FA verified")

    token = api.session.auth_token
    if not token:
        print("error: no auth token in session after login", file=sys.stderr)
        return 1

    path = Path(settings.picnic_token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": token}))
    path.chmod(0o600)
    print(f"token written to {path}")

    # Verify it actually works
    try:
        user = api.get_user()
        print(f"verified: logged in as {user.get('firstname')} {user.get('lastname')}")
    except Exception as e:
        print(f"warning: could not verify token via get_user: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
