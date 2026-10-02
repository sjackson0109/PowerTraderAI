#!/usr/bin/env python3
"""
PowerTrader AI - Order Management Migration Scripts
==================================================

Database migration scripts for order management system initialization
and schema updates.
"""

import logging
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

# Configure logging
logger = logging.getLogger(__name__)


class OrderManagementMigrations:
    """Database migration manager for order management system."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize migration manager."""
        import pt_paths

        if db_path is None:
            db_path = pt_paths.data_file("order_management.db")

        self.db_path = db_path
        self.migrations_dir = os.path.join(pt_paths.data_dir(), "migrations")

        # Ensure migrations directory exists
        os.makedirs(self.migrations_dir, exist_ok=True)

    def create_migrations_table(self):
        """Create migrations tracking table."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    migration_name TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    checksum TEXT
                )
            """)
            conn.commit()
            logger.info("Created migrations tracking table")
        finally:
            conn.close()

    def get_applied_migrations(self) -> List[str]:
        """Get list of applied migration names."""
        self.create_migrations_table()

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT migration_name FROM migrations ORDER BY applied_at")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def apply_migration(self, migration_name: str, migration_sql: str) -> bool:
        """Apply a single migration."""
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Check if already applied
            cursor.execute(
                "SELECT COUNT(*) FROM migrations WHERE migration_name = ?",
                (migration_name,),
            )
            if cursor.fetchone()[0] > 0:
                logger.info(f"Migration {migration_name} already applied")
                return True

            # Execute migration SQL
            cursor.executescript(migration_sql)

            # Record migration
            cursor.execute(
                "INSERT INTO migrations (migration_name) VALUES (?)", (migration_name,)
            )

            conn.commit()
            logger.info(f"Applied migration: {migration_name}")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to apply migration {migration_name}: {e}")
            return False
        finally:
            conn.close()

    def run_initial_migration(self) -> bool:
        """Run initial order management schema migration."""
        migration_sql = """
        -- Order Management System Initial Schema
        -- Migration: 001_initial_order_management

        PRAGMA foreign_keys = ON;

        -- Orders table
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            order_type TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity DECIMAL(20,8) NOT NULL,
            price DECIMAL(20,8),
            stop_price DECIMAL(20,8),
            filled_quantity DECIMAL(20,8) DEFAULT 0,
            average_fill_price DECIMAL(20,8),
            status TEXT NOT NULL DEFAULT 'PENDING',
            client_order_id TEXT UNIQUE,
            exchange_order_id TEXT,
            tag TEXT,
            user_id TEXT,
            commission DECIMAL(20,8) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submitted_at TIMESTAMP,
            filled_at TIMESTAMP,
            expires_at TIMESTAMP
        );

        -- Order conditions table
        CREATE TABLE IF NOT EXISTS order_conditions (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            condition_type TEXT NOT NULL,
            operator TEXT NOT NULL,
            target_value DECIMAL(20,8) NOT NULL,
            current_value DECIMAL(20,8),
            symbol TEXT,
            indicator_name TEXT,
            is_met BOOLEAN DEFAULT FALSE,
            met_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
        );

        -- Order executions table
        CREATE TABLE IF NOT EXISTS order_executions (
            id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            quantity DECIMAL(20,8) NOT NULL,
            price DECIMAL(20,8) NOT NULL,
            commission DECIMAL(20,8) DEFAULT 0,
            exchange_execution_id TEXT,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
        );

        -- Notifications table
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            order_id TEXT,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read BOOLEAN DEFAULT FALSE,
            user_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            read_at TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE SET NULL
        );

        -- Order templates table
        CREATE TABLE IF NOT EXISTS order_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            template_data TEXT NOT NULL,
            user_id TEXT,
            is_public BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
        CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
        CREATE INDEX IF NOT EXISTS idx_orders_symbol_status ON orders(symbol, status);

        CREATE INDEX IF NOT EXISTS idx_order_conditions_order_id ON order_conditions(order_id);
        CREATE INDEX IF NOT EXISTS idx_order_conditions_type ON order_conditions(condition_type);
        CREATE INDEX IF NOT EXISTS idx_order_conditions_is_met ON order_conditions(is_met);

        CREATE INDEX IF NOT EXISTS idx_order_executions_order_id ON order_executions(order_id);
        CREATE INDEX IF NOT EXISTS idx_order_executions_executed_at ON order_executions(executed_at);

        CREATE INDEX IF NOT EXISTS idx_notifications_order_id ON notifications(order_id);
        CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
        CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read);
        CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at);

        CREATE INDEX IF NOT EXISTS idx_order_templates_user_id ON order_templates(user_id);
        CREATE INDEX IF NOT EXISTS idx_order_templates_is_public ON order_templates(is_public);

        -- Triggers for updating timestamps
        CREATE TRIGGER IF NOT EXISTS orders_update_timestamp
            AFTER UPDATE ON orders
        BEGIN
            UPDATE orders SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS order_templates_update_timestamp
            AFTER UPDATE ON order_templates
        BEGIN
            UPDATE order_templates SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
        END;
        """

        return self.apply_migration("001_initial_order_management", migration_sql)

    def migrate_existing_powertrader_data(self) -> bool:
        """Migrate existing PowerTrader trade data to new order system."""
        migration_sql = """
        -- Migration: 002_migrate_existing_data
        -- Migrate existing PowerTrader positions and trades to order management

        -- This migration would analyze existing PowerTrader data files
        -- and create corresponding orders in the new system

        -- For now, this creates sample data structure for testing
        INSERT OR IGNORE INTO order_templates (
            id,
            name,
            description,
            template_data,
            is_public
        ) VALUES (
            'dca_template_001',
            'DCA Buy Order',
            'Dollar Cost Averaging buy order with neural level trigger',
            '{"order_type": "CONDITIONAL", "side": "BUY", "conditions": [{"type": "NEURAL_LEVEL", "operator": "GTE"}]}',
            1
        );

        INSERT OR IGNORE INTO order_templates (
            id,
            name,
            description,
            template_data,
            is_public
        ) VALUES (
            'trailing_stop_001',
            'Trailing Stop Loss',
            'Trailing stop loss order for profit management',
            '{"order_type": "CONDITIONAL", "side": "SELL", "conditions": [{"type": "PRICE", "operator": "LTE"}]}',
            1
        );

        INSERT OR IGNORE INTO order_templates (
            id,
            name,
            description,
            template_data,
            is_public
        ) VALUES (
            'take_profit_001',
            'Take Profit Order',
            'Take profit order at specific price level',
            '{"order_type": "LIMIT", "side": "SELL", "conditions": [{"type": "PRICE", "operator": "GTE"}]}',
            1
        );
        """

        return self.apply_migration("002_migrate_existing_data", migration_sql)

    def run_all_migrations(self) -> bool:
        """Run all pending migrations."""
        self.create_migrations_table()

        migrations = [
            ("001_initial_order_management", self.run_initial_migration),
            ("002_migrate_existing_data", self.migrate_existing_powertrader_data),
        ]

        applied_migrations = self.get_applied_migrations()
        success = True

        for migration_name, migration_func in migrations:
            if migration_name not in applied_migrations:
                logger.info(f"Running migration: {migration_name}")
                if not migration_func():
                    logger.error(f"Migration failed: {migration_name}")
                    success = False
                    break
            else:
                logger.debug(f"Skipping already applied migration: {migration_name}")

        if success:
            logger.info("All migrations completed successfully")
        else:
            logger.error("Migration process failed")

        return success

    def create_test_data(self) -> bool:
        """Create test data for development and testing."""
        test_data_sql = """
        -- Test data for order management system
        DELETE FROM notifications;
        DELETE FROM order_executions;
        DELETE FROM order_conditions;
        DELETE FROM orders;

        -- Sample orders for testing
        INSERT INTO orders (
            id, symbol, order_type, side, quantity, price, status,
            client_order_id, tag, user_id, created_at
        ) VALUES
        (
            'test_order_001',
            'BTCUSDT',
            'LIMIT',
            'BUY',
            0.001,
            45000.00,
            'PENDING',
            'PT_TEST_001',
            'DCA_STAGE_1',
            'test_user',
            datetime('now', '-1 hour')
        ),
        (
            'test_order_002',
            'ETHUSDT',
            'CONDITIONAL',
            'SELL',
            0.1,
            3200.00,
            'PENDING',
            'PT_TEST_002',
            'TRAILING_STOP',
            'test_user',
            datetime('now', '-30 minutes')
        );

        -- Sample conditions
        INSERT INTO order_conditions (
            id, order_id, condition_type, operator, target_value,
            symbol, is_met, created_at
        ) VALUES
        (
            'test_cond_001',
            'test_order_001',
            'NEURAL_LEVEL',
            'GTE',
            7,
            'BTCUSDT',
            0,
            datetime('now', '-1 hour')
        ),
        (
            'test_cond_002',
            'test_order_002',
            'PRICE',
            'LTE',
            3100.00,
            'ETHUSDT',
            0,
            datetime('now', '-30 minutes')
        );

        -- Sample notifications
        INSERT INTO notifications (
            id, order_id, notification_type, title, message,
            is_read, user_id, created_at
        ) VALUES
        (
            'test_notif_001',
            'test_order_001',
            'ORDER_CREATED',
            'Order Created: BTCUSDT',
            'Created DCA buy order for 0.001 BTC at $45,000',
            0,
            'test_user',
            datetime('now', '-1 hour')
        ),
        (
            'test_notif_002',
            'test_order_002',
            'ORDER_CREATED',
            'Order Created: ETHUSDT',
            'Created trailing stop order for 0.1 ETH',
            0,
            'test_user',
            datetime('now', '-30 minutes')
        );
        """

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.executescript(test_data_sql)
            conn.commit()
            logger.info("Created test data successfully")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create test data: {e}")
            return False
        finally:
            conn.close()

    def backup_database(self) -> str:
        """Create a backup of the database."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{self.db_path}.backup_{timestamp}"

        try:
            # Simple file copy for SQLite
            import shutil

            shutil.copy2(self.db_path, backup_path)
            logger.info(f"Database backed up to: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
            raise

    def verify_schema(self) -> bool:
        """Verify that all tables and indexes exist."""
        expected_tables = [
            "orders",
            "order_conditions",
            "order_executions",
            "notifications",
            "order_templates",
            "migrations",
        ]

        expected_indexes = [
            "idx_orders_symbol",
            "idx_orders_status",
            "idx_orders_user_id",
            "idx_orders_created_at",
            "idx_orders_symbol_status",
            "idx_order_conditions_order_id",
            "idx_order_conditions_type",
            "idx_order_executions_order_id",
            "idx_notifications_order_id",
        ]

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()

            # Check tables
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            actual_tables = [row[0] for row in cursor.fetchall()]

            missing_tables = set(expected_tables) - set(actual_tables)
            if missing_tables:
                logger.error(f"Missing tables: {missing_tables}")
                return False

            # Check indexes
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
            actual_indexes = [row[0] for row in cursor.fetchall()]

            missing_indexes = set(expected_indexes) - set(actual_indexes)
            if missing_indexes:
                logger.warning(f"Missing indexes: {missing_indexes}")
                # Indexes are not critical for functionality, just performance

            logger.info("Database schema verification completed")
            return True

        except Exception as e:
            logger.error(f"Schema verification failed: {e}")
            return False
        finally:
            conn.close()


def initialize_order_management_database(
    db_path: Optional[str] = None, create_test_data: bool = False
) -> bool:
    """Initialize the order management database with all migrations."""
    try:
        migration_manager = OrderManagementMigrations(db_path)

        # Backup existing database if it exists
        if os.path.exists(migration_manager.db_path):
            backup_path = migration_manager.backup_database()
            logger.info(f"Existing database backed up to: {backup_path}")

        # Run all migrations
        if not migration_manager.run_all_migrations():
            logger.error("Failed to run migrations")
            return False

        # Verify schema
        if not migration_manager.verify_schema():
            logger.error("Schema verification failed")
            return False

        # Create test data if requested
        if create_test_data:
            if not migration_manager.create_test_data():
                logger.error("Failed to create test data")
                return False

        logger.info(
            f"Order management database initialized successfully at: {migration_manager.db_path}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return False


if __name__ == "__main__":
    # Command line usage
    import sys

    if len(sys.argv) > 1:
        db_path = sys.argv[1]
        create_test = "--test-data" in sys.argv
    else:
        db_path = None
        create_test = True  # Create test data by default for development

    success = initialize_order_management_database(db_path, create_test)
    sys.exit(0 if success else 1)
