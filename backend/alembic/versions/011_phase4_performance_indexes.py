"""Phase 4 T20: Performance indexes for Phase 3 + Phase 4 tables.

Revision ID: 011
Revises: 010
Create Date: 2026-08-05
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_name(table: str, column: str) -> str:
    return f"idx_{table}_{column}"


def _create_index(table: str, column: str) -> None:
    idx = _index_name(table, column)
    op.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON {table}({column})")


def upgrade() -> None:
    # Phase 3: hr_requests
    _create_index("hr_requests", "status")
    _create_index("hr_requests", "applicant_id")
    _create_index("hr_requests", "approved_by")
    _create_index("hr_requests", "org_id")
    _create_index("hr_requests", "created_at")

    # Phase 3: finance_claims
    _create_index("finance_claims", "status")
    _create_index("finance_claims", "applicant_id")
    _create_index("finance_claims", "org_id")
    _create_index("finance_claims", "created_at")

    # Phase 3: finance_budgets
    _create_index("finance_budgets", "fiscal_year")
    _create_index("finance_budgets", "org_id")

    # Phase 3: finance_approval_records
    _create_index("finance_approval_records", "claim_id")
    _create_index("finance_approval_records", "approver_id")

    # Phase 4: cms_sites
    _create_index("cms_sites", "status")
    _create_index("cms_sites", "org_id")

    # Phase 4: estate_spaces
    _create_index("estate_spaces", "status")
    _create_index("estate_spaces", "department_id")
    _create_index("estate_spaces", "org_id")

    # Phase 4: job_postings
    _create_index("job_postings", "status")
    _create_index("job_postings", "org_id")


def downgrade() -> None:
    tables_cols = [
        ("hr_requests", ["status", "applicant_id", "approved_by", "org_id", "created_at"]),
        ("finance_claims", ["status", "applicant_id", "org_id", "created_at"]),
        ("finance_budgets", ["fiscal_year", "org_id"]),
        ("finance_approval_records", ["claim_id", "approver_id"]),
        ("cms_sites", ["status", "org_id"]),
        ("estate_spaces", ["status", "department_id", "org_id"]),
        ("job_postings", ["status", "org_id"]),
    ]
    for table, columns in tables_cols:
        for col in columns:
            op.execute(f"DROP INDEX IF EXISTS {_index_name(table, col)}")
