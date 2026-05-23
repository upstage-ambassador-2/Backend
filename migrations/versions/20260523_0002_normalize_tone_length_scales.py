"""normalize tone and length scales

Revision ID: 20260523_0002
Revises: 20260523_0001
Create Date: 2026-05-23 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op


revision: str = "20260523_0002"
down_revision: str | None = "20260523_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE personas
        SET tone = CASE
            WHEN tone IN ('매우 격식', '격식', '중립', '친근', '매우 친근') THEN tone
            WHEN tone LIKE '%매우%격식%' OR tone LIKE '%매우%정중%' OR tone LIKE '%공식%' THEN '매우 격식'
            WHEN tone LIKE '%격식%' OR tone LIKE '%정중%' OR tone LIKE '%공손%' OR tone LIKE '%업무%' OR tone LIKE '%결론%' THEN '격식'
            WHEN tone LIKE '%매우%친근%' OR tone LIKE '%친밀%' OR tone LIKE '%편안%' THEN '매우 친근'
            WHEN tone LIKE '%친근%' OR tone LIKE '%따뜻%' OR tone LIKE '%부드럽%' OR tone LIKE '%캐주얼%' THEN '친근'
            ELSE '중립'
        END
        """
    )
    op.execute(
        """
        UPDATE history
        SET tone = CASE
            WHEN tone <= 20 THEN 1
            WHEN tone <= 40 THEN 2
            WHEN tone <= 60 THEN 3
            WHEN tone <= 80 THEN 4
            ELSE 5
        END,
        length = CASE
            WHEN length <= 20 THEN 1
            WHEN length <= 40 THEN 2
            WHEN length <= 60 THEN 3
            WHEN length <= 80 THEN 4
            ELSE 5
        END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE history
        SET tone = CASE tone
            WHEN 1 THEN 0
            WHEN 2 THEN 25
            WHEN 3 THEN 50
            WHEN 4 THEN 75
            ELSE 100
        END,
        length = CASE length
            WHEN 1 THEN 0
            WHEN 2 THEN 25
            WHEN 3 THEN 50
            WHEN 4 THEN 75
            ELSE 100
        END
        """
    )
