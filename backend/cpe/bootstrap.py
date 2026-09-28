from sqlalchemy import select, text
from .db import DB, User, engine
from .config import settings
from .security import hash_password


def bootstrap():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if engine.dialect.name == "postgresql" and settings.runtime_password:
        # Fixed role name; quote password using PostgreSQL's own literal formatter.
        with engine.begin() as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_roles WHERE rolname='cpe_runtime'")):
                conn.execute(text("CREATE ROLE cpe_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"))
            statement = conn.scalar(text("SELECT format('ALTER ROLE cpe_runtime PASSWORD %L', CAST(:password AS text))"), {"password":settings.runtime_password})
            conn.exec_driver_sql(statement)
            conn.execute(text("REVOKE CREATE ON SCHEMA public FROM PUBLIC"))
            conn.execute(text("GRANT USAGE ON SCHEMA public TO cpe_runtime"))
            conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO cpe_runtime"))
            conn.execute(text("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cpe_runtime"))
            conn.execute(text("REVOKE UPDATE, DELETE ON audit FROM cpe_runtime"))
            conn.execute(text("REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM cpe_runtime"))
    with DB.begin() as db:
        if db.scalar(select(User).where(User.email == settings.admin_email)):
            return
        if len(settings.admin_password) < 16:
            raise RuntimeError("Set CPE_ADMIN_PASSWORD to a unique password of at least 16 characters")
        db.add(User(email=settings.admin_email.lower(), password=hash_password(settings.admin_password), role="admin"))


if __name__ == "__main__":
    try:
        bootstrap()
    except Exception as exc:
        raise SystemExit("Bootstrap failed: " + type(exc).__name__ + ". Check deployment configuration.")
