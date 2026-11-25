"""Create the tables and seed the towns. Safe to run any number of times.

Run from the repo root:  python -m pipeline.init_db
"""

from pathlib import Path

from pipeline.config import LOCATIONS
from pipeline.db import get_connection

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

UPSERT_LOCATION = """
    INSERT INTO locations (name, latitude, longitude)
    VALUES (%(name)s, %(latitude)s, %(longitude)s)
    ON CONFLICT (name) DO UPDATE
        SET latitude  = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude
"""


def apply_schema(conn) -> None:
    """Run every numbered schema file (001_, 002_, ...) in order."""
    for path in sorted(SQL_DIR.glob("[0-9][0-9][0-9]_*.sql")):
        print(f"Applying {path.name}")
        conn.execute(path.read_text(encoding="utf-8"))


def seed_locations(conn) -> None:
    """Upsert the towns from config. Re-running updates coordinates, never duplicates."""
    with conn.cursor() as cur:
        cur.executemany(UPSERT_LOCATION, LOCATIONS)


def main() -> None:
    # One transaction: if anything fails, Postgres rolls back all of it,
    # including the CREATE TABLEs (DDL is transactional in Postgres).
    with get_connection() as conn:
        version = conn.execute("SELECT version()").fetchone()[0]
        print(f"Connected: {version}")
        apply_schema(conn)
        seed_locations(conn)
        count = conn.execute("SELECT count(*) FROM locations").fetchone()[0]
        print(f"Locations: {count}")


if __name__ == "__main__":
    main()
