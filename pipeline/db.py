"""The single place that knows how to connect to Postgres."""

import os

import psycopg
from dotenv import load_dotenv

# Locally this reads .env; in GitHub Actions there's no .env and the variable
# comes from repo secrets instead. load_dotenv never overrides a variable that's already set.
load_dotenv()


def get_connection() -> psycopg.Connection:
    """Open a connection. Use it as `with get_connection() as conn:`.

    On leaving the `with` block, psycopg commits if no error happened, rolls
    back if one did, and closes the connection.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to .env (local) or to GitHub secrets (CI)."
        )
    # Neon may be paused; the first connect can take a few seconds to wake it.
    return psycopg.connect(url, connect_timeout=20)
