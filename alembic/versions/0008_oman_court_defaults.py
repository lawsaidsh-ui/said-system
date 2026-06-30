"""align demo court data with Oman courts

Revision ID: 0008_oman_court_defaults
Revises: 0007_matter_ministry_case_number
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_oman_court_defaults"
down_revision = "0007_matter_ministry_case_number"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE matters
            SET court_name = CASE court_name
                WHEN 'محكمة دبي' THEN 'المحكمة الابتدائية بمسقط'
                WHEN 'محكمة أبوظبي' THEN 'محكمة الاستئناف بمسقط'
                WHEN 'محكمة الشارقة' THEN 'المحكمة الابتدائية بالسيب'
                WHEN 'محكمة عجمان' THEN 'المحكمة الابتدائية بنزوى'
                WHEN 'محكمة أم القيوين' THEN 'المحكمة الابتدائية بالرستاق'
                WHEN 'محكمة رأس الخيمة' THEN 'المحكمة الابتدائية بصحار'
                WHEN 'محكمة الفجيرة' THEN 'المحكمة الابتدائية بإبراء'
                WHEN 'محكمة اتحادية' THEN 'المحكمة العليا'
                ELSE court_name
            END
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE court_sessions
            SET court_name = CASE court_name
                WHEN 'محكمة دبي' THEN 'المحكمة الابتدائية بمسقط'
                WHEN 'محكمة أبوظبي' THEN 'محكمة الاستئناف بمسقط'
                WHEN 'محكمة الشارقة' THEN 'المحكمة الابتدائية بالسيب'
                WHEN 'محكمة عجمان' THEN 'المحكمة الابتدائية بنزوى'
                WHEN 'محكمة أم القيوين' THEN 'المحكمة الابتدائية بالرستاق'
                WHEN 'محكمة رأس الخيمة' THEN 'المحكمة الابتدائية بصحار'
                WHEN 'محكمة الفجيرة' THEN 'المحكمة الابتدائية بإبراء'
                WHEN 'محكمة اتحادية' THEN 'المحكمة العليا'
                ELSE court_name
            END
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE matters
            SET court_level = CASE court_level
                WHEN 'تمييز' THEN 'عليا'
                WHEN 'نقض' THEN 'طعن أمام المحكمة العليا'
                ELSE court_level
            END
            """
        )
    )
    conn.execute(sa.text("UPDATE office_settings SET value = 'مسقط، سلطنة عمان' WHERE key = 'address' AND value = 'دبي، الإمارات العربية المتحدة'"))
    conn.execute(sa.text("UPDATE office_settings SET value = '+968 0000 0000' WHERE key = 'phone' AND value = '0500000000'"))
    conn.execute(sa.text("UPDATE office_settings SET value = 'info@saeed-law.om' WHERE key = 'email' AND value = 'info@saeed-law.test'"))


def downgrade() -> None:
    pass
