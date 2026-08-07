"""Drop portal_services table and rebase subsystems for v2 enterprise.

- DROP TABLE portal_services (services concept retired)
- DELETE stale subsystems not in the new 16-item enterprise catalog
- Upsert the 16 new enterprise subsystems
"""

from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ── New enterprise subsystem codes ────────────────────────────────────
NEW_CODES = [
    "oa", "supervision",                                    # 办公行政类
    "hr", "recruitment", "training", "wellness",            # 人力组织类
    "crm", "erp", "service-desk", "supply-chain",           # 经营业务类
    "finance", "fixed-assets", "facility", "repair",        # 财资后勤 & 支撑类
    "data-portal", "party",
]

# ── Old subsystem codes to remove (education-context legacy) ──────────
STALE_CODES = [
    "teaching-cloud", "website", "alumni", "student",
    "employment", "mental-health", "estate", "assets",
]


def upgrade() -> None:
    # 1. Drop portal_services table (data is no longer relevant)
    op.execute("DROP TABLE IF EXISTS portal_services")

    # 2. Remove stale subsystem rows that are not in the enterprise catalog
    for code in STALE_CODES:
        op.execute(f"DELETE FROM portal_subsystems WHERE code = '{code}'")

    # 3. Remove stale subsystem visits for codes that no longer exist
    for code in STALE_CODES:
        op.execute(f"DELETE FROM portal_subsystem_visits WHERE subsystem_code = '{code}'")


def downgrade() -> None:
    # Re-create portal_services table with original schema
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_services (
            code VARCHAR(64) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            category VARCHAR(64) NOT NULL,
            description TEXT NOT NULL,
            materials TEXT NOT NULL DEFAULT '',
            audience VARCHAR(128) NOT NULL DEFAULT '',
            contact VARCHAR(128) NOT NULL DEFAULT '',
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            subscribed_count INTEGER NOT NULL DEFAULT 0,
            updated_at VARCHAR(32) NOT NULL,
            created_at VARCHAR(32) NOT NULL,
            org_id VARCHAR(64),
            department_id VARCHAR(64),
            owner_id INTEGER,
            visibility VARCHAR(16) NOT NULL DEFAULT 'org',
            sensitivity VARCHAR(16) NOT NULL DEFAULT 'normal',
            created_by INTEGER,
            updated_by INTEGER
        )
        """
    )
    # Note: downgrade does not restore stale subsystem rows or service seed data.
    # Re-running the application's _seed_defaults() will re-populate from current
    # DEFAULT_SUBSYSTEMS and DEFAULT_SERVICES constants (if they still exist).
