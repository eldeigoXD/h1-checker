import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'image_bank.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes SQLite schema for Image Bank."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS image_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_url TEXT UNIQUE NOT NULL,
            make TEXT,
            model TEXT,
            condition TEXT DEFAULT 'general',
            category TEXT DEFAULT 'general',
            surrounding_text TEXT,
            alt_text TEXT,
            section_title TEXT,
            dealer_id TEXT,
            use_count INTEGER DEFAULT 1,
            first_seen DATETIME,
            last_seen DATETIME
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS image_occurrences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            image_url TEXT NOT NULL,
            page_url TEXT NOT NULL,
            case_id TEXT,
            timestamp DATETIME
        )
    ''')
    
    # Indexes for fast filtering
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_make ON image_assets(make)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_model ON image_assets(model)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_category ON image_assets(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_condition ON image_assets(condition)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_use_count ON image_assets(use_count DESC)')
    
    conn.commit()
    conn.close()

def save_harvested_image(image_url, make, model, condition, category, surrounding_text="", alt_text="", section_title="", dealer_id="", page_url="", case_id=""):
    """
    Saves an extracted image asset or increments its use_count if already indexed.
    """
    if not image_url or not isinstance(image_url, str):
        return None

    now = datetime.utcnow().isoformat()
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        # Check if asset already exists
        cursor.execute("SELECT id, use_count, make, model, category, condition FROM image_assets WHERE image_url = ?", (image_url,))
        row = cursor.fetchone()
        
        if row:
            asset_id = row['id']
            new_count = row['use_count'] + 1
            
            # Enrich fields if current values are empty/general and new data is available
            new_make = make if (make and row['make'] in (None, '', 'unknown')) else row['make']
            new_model = model if (model and row['model'] in (None, '', 'unknown')) else row['model']
            new_category = category if (category and category != 'general' and row['category'] == 'general') else row['category']
            new_condition = condition if (condition and condition != 'general' and row['condition'] == 'general') else row['condition']
            
            cursor.execute('''
                UPDATE image_assets 
                SET use_count = ?, make = ?, model = ?, category = ?, condition = ?, last_seen = ?
                WHERE id = ?
            ''', (new_count, new_make, new_model, new_category, new_condition, now, asset_id))
        else:
            cursor.execute('''
                INSERT INTO image_assets 
                (image_url, make, model, condition, category, surrounding_text, alt_text, section_title, dealer_id, use_count, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            ''', (image_url, make or 'unknown', model or 'unknown', condition or 'general', category or 'general', surrounding_text[:500], alt_text[:250], section_title[:200], dealer_id, now, now))
            asset_id = cursor.lastrowid
            
        # Log occurrence
        cursor.execute('''
            INSERT INTO image_occurrences (image_url, page_url, case_id, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (image_url, page_url, case_id or '', now))
        
        conn.commit()
        return asset_id
    except Exception as e:
        print(f"[WARN] Failed to save image asset ({image_url}): {e}")
        conn.rollback()
        return None
    finally:
        conn.close()

def query_image_assets(make=None, model=None, condition=None, category=None, search=None, limit=50, offset=0):
    """Query harvested image assets with optional filters, sorted by use_count DESC."""
    conn = get_db()
    cursor = conn.cursor()
    
    query = "SELECT * FROM image_assets WHERE 1=1"
    params = []
    
    if make:
        query += " AND LOWER(make) = LOWER(?)"
        params.append(make)
    if model:
        query += " AND LOWER(model) = LOWER(?)"
        params.append(model)
    if condition and condition.lower() != 'all':
        query += " AND LOWER(condition) = LOWER(?)"
        params.append(condition)
    if category and category.lower() != 'all':
        query += " AND LOWER(category) = LOWER(?)"
        params.append(category)
    if search:
        query += " AND (LOWER(surrounding_text) LIKE ? OR LOWER(alt_text) LIKE ? OR LOWER(section_title) LIKE ? OR LOWER(image_url) LIKE ?)"
        term = f"%{search.lower()}%"
        params.extend([term, term, term, term])
        
    count_params = list(params)
    count_query = query.replace("SELECT *", "SELECT COUNT(*) as total", 1)
    cursor.execute(count_query, count_params)
    total_row = cursor.fetchone()
    total = total_row['total'] if total_row else 0

    query += " ORDER BY use_count DESC, id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return {'assets': rows, 'total': total, 'limit': limit, 'offset': offset}

def get_image_bank_stats():
    """Returns aggregated stats of harvested images by Make, Model, and Category."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total_assets, SUM(use_count) as total_occurrences FROM image_assets")
    totals = dict(cursor.fetchone() or {'total_assets': 0, 'total_occurrences': 0})
    
    cursor.execute("SELECT make, COUNT(*) as count FROM image_assets WHERE make != 'unknown' GROUP BY make ORDER BY count DESC LIMIT 15")
    makes = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT model, COUNT(*) as count FROM image_assets WHERE model != 'unknown' GROUP BY model ORDER BY count DESC LIMIT 15")
    models = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT category, COUNT(*) as count FROM image_assets GROUP BY category ORDER BY count DESC")
    categories = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return {
        'total_assets': totals['total_assets'] or 0,
        'total_occurrences': totals['total_occurrences'] or 0,
        'makes': makes,
        'models': models,
        'categories': categories
    }

def delete_image_asset(asset_id: int = None, image_url: str = None) -> bool:
    """Deletes an asset from image_assets and its recorded occurrences."""
    conn = get_db()
    cursor = conn.cursor()
    try:
        target_url = image_url
        if asset_id:
            cursor.execute("SELECT image_url FROM image_assets WHERE id = ?", (asset_id,))
            row = cursor.fetchone()
            if row:
                target_url = row['image_url']
            cursor.execute("DELETE FROM image_assets WHERE id = ?", (asset_id,))
        elif image_url:
            cursor.execute("DELETE FROM image_assets WHERE image_url = ?", (image_url,))
            
        if target_url:
            cursor.execute("DELETE FROM image_occurrences WHERE image_url = ?", (target_url,))
            
        conn.commit()
        return True
    except Exception as e:
        print(f"Error deleting image asset: {e}")
        return False
    finally:
        conn.close()

# Initialize database on module load
init_db()

