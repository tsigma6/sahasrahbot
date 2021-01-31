"""empty message

Revision ID: 243a52b2162f
Revises: 0475581f0725
Create Date: 2021-01-31 14:59:27.371770

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '243a52b2162f'
down_revision = '0475581f0725'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('tournament_games',
    sa.Column('episode_id', mysql.INTEGER(display_width=11), autoincrement=False, nullable=False),
    sa.Column('event', sa.String(length=45, collation='utf8_bin'), nullable=True),
    sa.Column('game_number', mysql.INTEGER(display_width=11), nullable=True),
    sa.Column('settings', sa.JSON(), nullable=True),
    sa.Column('submitted', mysql.TINYINT(display_width=1), nullable=True),
    sa.Column('created', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
    sa.Column('updated', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'), nullable=True),
    sa.PrimaryKeyConstraint('episode_id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('tournament_games')
    # ### end Alembic commands ###
