"""Canonical UTC precision for stable inclusive time-window comparisons."""
from alembic import op
revision = "0002"
down_revision = "0001"


def upgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute('''UPDATE events SET timestamp = to_char(timestamp::timestamptz AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00' WHERE timestamp <> '' ''')


def downgrade():
    # Increased precision is lossless and does not need reversal.
    pass
