"""Add v2.0.0 fields to redemption_requests table.

Revision ID: 003_add_redemption_v2_fields
Revises: 20241215_1000_002_create_business_tables
Create Date: 2024-12-17 10:00:00.000000

New fields for v2.0.0 contract compatibility:
- voucher_token_id: NFT Voucher Token ID
- has_voucher: Whether NFT Voucher has been minted
- pending_approval_shares: Pending approval shares snapshot
- waterfall_triggered: Whether waterfall liquidation was triggered
- waterfall_amount: Waterfall liquidation amount
- approval_tx_hash: On-chain approval transaction hash
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003_add_redemption_v2_fields'
down_revision = '20241215_1000_002_create_business_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add v2.0.0 fields to redemption_requests table."""
    # NFT Voucher fields
    op.add_column(
        'redemption_requests',
        sa.Column(
            'voucher_token_id',
            sa.Numeric(78, 0),
            nullable=True,
            comment='NFT Voucher Token ID'
        )
    )
    op.add_column(
        'redemption_requests',
        sa.Column(
            'has_voucher',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='是否已铸造 NFT Voucher'
        )
    )

    # Pending approval shares snapshot
    op.add_column(
        'redemption_requests',
        sa.Column(
            'pending_approval_shares',
            sa.Numeric(78, 0),
            nullable=True,
            comment='待审批份额快照 (来自 PPT.pendingApprovalSharesOf)'
        )
    )

    # Waterfall liquidation fields
    op.add_column(
        'redemption_requests',
        sa.Column(
            'waterfall_triggered',
            sa.Boolean(),
            nullable=False,
            server_default='false',
            comment='是否触发瀑布清算'
        )
    )
    op.add_column(
        'redemption_requests',
        sa.Column(
            'waterfall_amount',
            sa.Numeric(78, 0),
            nullable=True,
            comment='瀑布清算金额'
        )
    )

    # On-chain execution tracking
    op.add_column(
        'redemption_requests',
        sa.Column(
            'approval_tx_hash',
            sa.String(66),
            nullable=True,
            comment='链上审批交易哈希'
        )
    )

    # Create index for voucher queries
    op.create_index(
        'ix_redemption_requests_has_voucher',
        'redemption_requests',
        ['has_voucher'],
        unique=False
    )


def downgrade() -> None:
    """Remove v2.0.0 fields from redemption_requests table."""
    op.drop_index('ix_redemption_requests_has_voucher', table_name='redemption_requests')
    op.drop_column('redemption_requests', 'approval_tx_hash')
    op.drop_column('redemption_requests', 'waterfall_amount')
    op.drop_column('redemption_requests', 'waterfall_triggered')
    op.drop_column('redemption_requests', 'pending_approval_shares')
    op.drop_column('redemption_requests', 'has_voucher')
    op.drop_column('redemption_requests', 'voucher_token_id')
