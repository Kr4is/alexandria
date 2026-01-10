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
        cursor.execute("PRAGMA table_info(book)")
        current_cols = [info[1] for info in cursor.fetchall()]
        
        new_columns = {
            'published_year': 'TEXT',
            'language': 'TEXT',
            'average_rating': 'REAL'
        }
        
        for col, dtype in new_columns.items():
            if col not in current_cols:
                print(f"Adding {col}...")
                cursor.execute(f"ALTER TABLE book ADD COLUMN {col} {dtype}")
                
        conn.commit()
        print("Migration successful!")
            
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
