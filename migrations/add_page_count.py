import sqlite3
import os

# Database path
base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
db_path = os.path.join(base_dir, 'instance', 'alexandria.db')

def migrate():
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(book)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'page_count' not in columns:
            print("Adding page_count column to book table...")
            cursor.execute("ALTER TABLE book ADD COLUMN page_count INTEGER")
            conn.commit()
            print("Migration successful!")
        else:
            print("Column page_count already exists.")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
