"""add joind filed

Revision ID: 597868aa7989
Revises: 5d86cd3de614
Create Date: 2026-03-27 14:40:23.520254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '597868aa7989'
down_revision: Union[str, Sequence[str], None] = '5d86cd3de614'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade():
    op.add_column(
        "employees",
        sa.Column("joined", sa.Date(), nullable=True)
    )

def downgrade():
    op.drop_column("employees", "joined")
