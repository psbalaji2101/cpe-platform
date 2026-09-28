"""Initial evidence platform schema."""
from alembic import op
from cpe.db import Base
revision = "0001"
down_revision = None


def upgrade():
    Base.metadata.create_all(op.get_bind())
    if op.get_bind().dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute("CREATE INDEX event_message_trgm ON events USING gin (message gin_trgm_ops)")


def downgrade():
    raise RuntimeError("Initial schema downgrade is destructive. Restore a tested backup instead.")
