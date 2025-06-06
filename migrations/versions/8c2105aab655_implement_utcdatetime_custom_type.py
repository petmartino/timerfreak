"""Implement UTCDateTime custom type

Revision ID: 8c2105aab655
Revises: 3de499ca6634
Create Date: 2025-06-06 02:49:33.988843

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8c2105aab655'
down_revision = '3de499ca6634'
branch_labels = None
depends_on = None


# In the newly created migration file (e.g., xxxxxxxx_implement_utcdatetime_custom_type.py)

from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
from dateutil import parser # Requires: pip install python-dateutil
from pytz import timezone as pytz_timezone # Requires: pip install pytz

# IMPORTANT: Set this to the timezone your server *was* in when the *old* data was generated
# by CURRENT_TIMESTAMP. Based on your dump's 'CDT' reference, 'America/Chicago' is highly likely.
ORIGINAL_SERVER_LOCAL_TZ_STR = 'America/Chicago'

def upgrade():
    conn = op.get_bind()
    original_tz = pytz_timezone(ORIGINAL_SERVER_LOCAL_TZ_STR)

    # Convert sequence.created_at
    results = conn.execute(sa.text("SELECT id, created_at FROM sequence WHERE created_at IS NOT NULL")).fetchall()
    for seq_id, naive_dt_str in results:
        try:
            naive_dt = parser.parse(naive_dt_str)
            local_dt = original_tz.localize(naive_dt) # Treat the stored value as local time
            utc_dt = local_dt.astimezone(timezone.utc) # Convert to true UTC
            utc_dt_str = utc_dt.strftime('%Y-%m-%d %H:%M:%S.%f') # Store back as naive UTC string
            conn.execute(sa.text("UPDATE sequence SET created_at = :utc_dt_str WHERE id = :seq_id"),
                         {'utc_dt_str': utc_dt_str, 'seq_id': seq_id})
        except Exception as e:
            print(f"Error converting sequence {seq_id} created_at '{naive_dt_str}': {e}")

    # Convert counter_log.timestamp
    results = conn.execute(sa.text("SELECT id, timestamp FROM counter_log WHERE timestamp IS NOT NULL")).fetchall()
    for log_id, naive_dt_str in results:
        try:
            naive_dt = parser.parse(naive_dt_str)
            local_dt = original_tz.localize(naive_dt)
            utc_dt = local_dt.astimezone(timezone.utc)
            utc_dt_str = utc_dt.strftime('%Y-%m-%d %H:%M:%S.%f')
            conn.execute(sa.text("UPDATE counter_log SET timestamp = :utc_dt_str WHERE id = :log_id"),
                         {'utc_dt_str': utc_dt_str, 'log_id': log_id})
        except Exception as e:
            print(f"Error converting counter_log {log_id} timestamp '{naive_dt_str}': {e}")

def downgrade():
    print("Downgrading timestamp conversion is not fully supported for this type of transformation.")
    pass