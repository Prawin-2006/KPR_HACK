"""Add quality, count, hierarchy, transfer, reorder and response workflows.

This revision is intentionally additive and backfills product identity without
changing any historical inventory transaction.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text
from app.models import Base, Product, Transfer

revision = '0002_supply_workflows'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

def upgrade():
    conn = op.get_bind()
    # Some legacy engines require referenced tables to exist before ADD COLUMN.
    Product.__table__.create(bind=conn, checkfirst=True)
    Transfer.__table__.create(bind=conn, checkfirst=True)
    inspector = inspect(conn)
    columns = {t: {c['name'] for c in inspector.get_columns(t)} for t in inspector.get_table_names()}
    additions = {
        'facilities': [
            sa.Column('parent_id', sa.Integer(), sa.ForeignKey('facilities.id',name='fk_facilities_parent_id'), nullable=True),
            sa.Column('maximum_stock', sa.Integer(), nullable=True),
            sa.Column('reorder_point', sa.Integer(), nullable=True),
            sa.Column('expiry_warning_days', sa.Integer(), server_default='60', nullable=False),
        ],
        'batches': [
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id',name='fk_batches_product_id'), nullable=True),
            sa.Column('quality_status', sa.String(30), server_default='awaiting_quality', nullable=False),
            sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        ],
        'replenishments': [
            sa.Column('product_id', sa.Integer(), sa.ForeignKey('products.id',name='fk_replenishments_product_id'), nullable=True),
        ],
        'inventory_transactions': [
            sa.Column('transfer_id', sa.Integer(), sa.ForeignKey('stock_transfers.id',name='fk_inventory_transactions_transfer_id'), nullable=True),
        ],
    }
    for table, cols in additions.items():
        present = columns.get(table, set())
        missing=[col for col in cols if col.name not in present]
        if missing:
            # Batch mode also supports SQLite's add-column foreign-key constraints.
            with op.batch_alter_table(table) as batch:
                for col in missing:
                    batch.add_column(col)
    # Create new workflow tables using metadata, leaving every legacy table intact.
    Base.metadata.create_all(bind=conn)
    for table, name, column in [
        ('facilities','ix_facilities_parent_id','parent_id'),
        ('batches','ix_batches_product_id','product_id'),
        ('inventory_transactions','ix_inventory_transactions_transfer_id','transfer_id'),
        ('replenishments','ix_replenishments_product_id','product_id'),
    ]:
        indexes={i['name'] for i in inspect(conn).get_indexes(table)}
        if name not in indexes:
            op.create_index(name,table,[column])
    conn.execute(text("UPDATE batches SET quality_status = CASE WHEN storage_status = 'damaged' THEN 'damaged' WHEN storage_status IN ('quarantined','quarantine') THEN 'quarantined' WHEN verified = 1 THEN 'verified' ELSE 'awaiting_quality' END"))
    for row in conn.execute(text('SELECT DISTINCT product FROM batches WHERE product IS NOT NULL')).all():
        name = row[0]
        identifier = 'LEGACY-' + ''.join(c if c.isalnum() else '-' for c in name.upper()).strip('-')[:70]
        found=conn.execute(text('SELECT id FROM products WHERE name=:n ORDER BY id LIMIT 1'), {'n':name}).first()
        if not found:
            found=conn.execute(text('SELECT id FROM products WHERE identifier=:i'), {'i':identifier}).first()
        if not found:
            conn.execute(text('INSERT INTO products (identifier, name, category, unit, active) VALUES (:i,:n,:c,:u,:a)'), {'i': identifier, 'n': name, 'c': 'Anti-snake venom', 'u': 'vial', 'a': True})
            found=conn.execute(text('SELECT id FROM products WHERE identifier=:i'), {'i':identifier}).first()
        conn.execute(text('UPDATE batches SET product_id=:pid WHERE product=:n AND product_id IS NULL'), {'pid':found[0], 'n':name})

def downgrade():
    conn = op.get_bind()
    # Remove only extension columns/tables; preserve every legacy row and table.
    for table, names in {
        'inventory_transactions': ['transfer_id'],
        'batches': ['product_id', 'quality_status', 'version'],
        'replenishments': ['product_id'],
        'facilities': ['parent_id', 'maximum_stock', 'reorder_point', 'expiry_warning_days'],
    }.items():
        present = {c['name'] for c in inspect(conn).get_columns(table)}
        dropping={name for name in names if name in present}
        # SQLite batch mode recreates indexes unless extension indexes are removed first.
        for idx in inspect(conn).get_indexes(table):
            if set(idx.get('column_names') or ()) & dropping:
                op.drop_index(idx['name'], table_name=table)
        if dropping:
            foreign_keys=[fk for fk in inspect(conn).get_foreign_keys(table) if set(fk.get('constrained_columns') or ()) & dropping and fk.get('name')]
            with op.batch_alter_table(table) as batch:
                for fk in foreign_keys:
                    batch.drop_constraint(fk['name'],type_='foreignkey')
                for name in names:
                    if name in dropping:
                        batch.drop_column(name)
    new_tables = ['daily_stock_observations', 'batch_events', 'reorder_drafts', 'evaluation_labels', 'alert_events', 'discrepancies', 'count_lines', 'physical_counts', 'stock_transfers', 'products']
    for table in new_tables:
        if table in inspect(conn).get_table_names():
            op.drop_table(table)
