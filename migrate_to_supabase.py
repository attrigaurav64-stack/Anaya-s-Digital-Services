"""
Database Migration Script: Local SQLite -> Supabase Cloud PostgreSQL
--------------------------------------------------------------------
This script copies all existing tables and data from instance/cybercafe.db
to your connected Supabase PostgreSQL database, and resets primary key sequences.
"""

import os
import sqlite3
from dotenv import load_dotenv
from app import app, db, Admin, Setting, Customer, Query, JobToken, Service, Payment, Invoice, Expense, WhatsAppMessage, Staff

load_dotenv()

SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "cybercafe.db")

def test_supabase_connection():
    target_url = os.getenv("DATABASE_URL")
    if not target_url or "sqlite" in target_url:
        print("❌ Error: DATABASE_URL in .env is not configured for Supabase/PostgreSQL.")
        print("Please update DATABASE_URL in .env with your Supabase PostgreSQL connection string.")
        return False
    
    print(f"Connecting to Cloud Database: {target_url.split('@')[-1] if '@' in target_url else 'Target DB'}...")
    try:
        with app.app_context():
            db.create_all()
            print("✅ Successfully connected to Supabase and verified schema!")
            return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False

def migrate_data():
    if not os.path.exists(SQLITE_DB_PATH):
        print(f"⚠️ Warning: Local SQLite database not found at {SQLITE_DB_PATH}. Skipping data import.")
        return

    print(f"Reading existing data from SQLite: {SQLITE_DB_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    models = [
        ("admin", Admin),
        ("setting", Setting),
        ("customer", Customer),
        ("query", Query),
        ("job_token", JobToken),
        ("service", Service),
        ("payment", Payment),
        ("invoice", Invoice),
        ("expense", Expense),
        ("whats_app_message", WhatsAppMessage),
        ("staff", Staff)
    ]

    with app.app_context():
        db.create_all()

        for table_name, model_cls in models:
            try:
                sqlite_cursor.execute(f"SELECT * FROM {table_name}")
                rows = sqlite_cursor.fetchall()
                if not rows:
                    print(f"  ℹ️ Table '{table_name}' has 0 rows.")
                    continue

                print(f"  🔄 Migrating {len(rows)} rows for '{table_name}'...")
                
                # Check column names expected by SQLAlchemy model
                model_cols = [column.name for column in model_cls.__table__.columns]
                
                inserted_count = 0
                for row in rows:
                    row_dict = dict(row)
                    # Filter out keys not present in model
                    filtered_dict = {k: v for k, v in row_dict.items() if k in model_cols}
                    
                    # Check if record already exists by ID
                    existing = model_cls.query.get(filtered_dict.get("id"))
                    if not existing:
                        instance = model_cls(**filtered_dict)
                        db.session.add(instance)
                        inserted_count += 1
                
                db.session.commit()
                print(f"  ✅ Table '{table_name}': {inserted_count} new rows copied.")

                # Reset PostgreSQL sequences for primary key 'id'
                try:
                    db.session.execute(db.text(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), COALESCE((SELECT MAX(id) FROM {table_name}), 1));"
                    ))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

            except Exception as e:
                db.session.rollback()
                print(f"  ⚠️ Error migrating '{table_name}': {e}")

    sqlite_conn.close()
    print("\n🎉 Migration completed successfully! Your Supabase Cloud database is ready.")

if __name__ == "__main__":
    if test_supabase_connection():
        migrate_data()
