"""consolidation loan kind and consolidated status

L72: an approved consolidation creates an installment of the new kind
`consolidation_loan` (vendor `consolidation`), and the installments it paid off
get the new status `consolidated`. Two CHECKs pin the loan: its kind and vendor
come together, and it carries its payment and rate. The platform-data CHECK
exempts the loan's vendor, whose late fee is unknown (NULL, never a made-up 0).

No existing row has the new kind, status or vendor. The downgrade refuses while
any exists: the narrower CHECKs would reject them.

Revision ID: 31616ed1dc70
Revises: 8f1c2d4e6a90
Create Date: 2026-10-27 20:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "31616ed1dc70"
down_revision: str | Sequence[str] | None = "8f1c2d4e6a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = "kind IN ('purchase', 'cash_withdrawal', 'cash_loan')"
KINDS = "kind IN ('purchase', 'cash_withdrawal', 'cash_loan', 'consolidation_loan')"
STATUSES_BEFORE = "status IN ('active', 'paid_off', 'cancelled', 'disputed')"
STATUSES = "status IN ('active', 'paid_off', 'cancelled', 'disputed', 'consolidated')"
DEBT_DATA = (
    "(min_payment IS NOT NULL AND late_fee_per_period IS NOT NULL AND monthly_rate IS NOT NULL)"
)
PLATFORM_DATA_BEFORE = f"vendor = 'manual' OR {DEBT_DATA}"
PLATFORM_DATA = f"vendor IN ('manual', 'consolidation') OR {DEBT_DATA}"
LOAN_VENDOR = "ck_installments_consolidation_loan_vendor"
LOAN_TERMS = "ck_installments_consolidation_loan_terms"


def _replace_check(name: str, condition: str) -> None:
    op.drop_constraint(op.f(name), "installments", type_="check")
    op.create_check_constraint(op.f(name), "installments", condition)


def upgrade() -> None:
    """Upgrade schema."""
    _replace_check("ck_installments_kind_valid", KINDS)
    _replace_check("ck_installments_status_valid", STATUSES)
    _replace_check("ck_installments_platform_debt_data_complete", PLATFORM_DATA)
    op.create_check_constraint(
        op.f(LOAN_VENDOR),
        "installments",
        "(kind = 'consolidation_loan') = (vendor = 'consolidation')",
    )
    op.create_check_constraint(
        op.f(LOAN_TERMS),
        "installments",
        "kind <> 'consolidation_loan' OR (min_payment IS NOT NULL AND monthly_rate IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM installments WHERE kind = 'consolidation_loan' "
        "OR status = 'consolidated' OR vendor = 'consolidation') THEN "
        "RAISE EXCEPTION 'consolidation rows exist; cannot downgrade'; END IF; END $$"
    )
    op.drop_constraint(op.f(LOAN_TERMS), "installments", type_="check")
    op.drop_constraint(op.f(LOAN_VENDOR), "installments", type_="check")
    _replace_check("ck_installments_platform_debt_data_complete", PLATFORM_DATA_BEFORE)
    _replace_check("ck_installments_status_valid", STATUSES_BEFORE)
    _replace_check("ck_installments_kind_valid", KINDS_BEFORE)
