"""Starts a throwaway embedded Postgres when DATABASE_URL is not provided (CI provides one)."""
import os


def ensure_database_url() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    import pgserver

    srv = pgserver.get_server(os.environ.get("PGSERVER_DIR", "/tmp/mangatranslate-pgtest"), cleanup_mode="stop")
    uri = srv.get_uri().replace("postgresql://", "postgresql+psycopg://")
    os.environ["DATABASE_URL"] = uri
    return uri
