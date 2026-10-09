import sqlite3
import time

DB_FILE = "albireo_state.db"

class LocalDB:
    """
    Handles local persistence of network state (contacts, chat history, governance logs).
    Provides a foundation for CRDT synchronization and offline history.
    """
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_tables()
        
    def _init_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS contacts (
                pub_key TEXT PRIMARY KEY,
                callsign TEXT,
                last_seen REAL
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                msg_id TEXT PRIMARY KEY,
                sender_key TEXT,
                timestamp REAL,
                content TEXT
            )
        ''')
        self.conn.commit()
        
    # --- Contacts ---
    def save_contact(self, pub_key, callsign):
        self.cursor.execute('''
            INSERT OR REPLACE INTO contacts (pub_key, callsign, last_seen)
            VALUES (?, ?, ?)
        ''', (pub_key, callsign, time.time()))
        self.conn.commit()
        
    def get_callsign(self, pub_key):
        self.cursor.execute('SELECT callsign FROM contacts WHERE pub_key=?', (pub_key,))
        row = self.cursor.fetchone()
        return row[0] if row else "Unknown"

    def get_all_contacts(self):
        self.cursor.execute('SELECT pub_key, callsign FROM contacts')
        return {r[0]: r[1] for r in self.cursor.fetchall()}
        
    # --- Chat History ---
    def save_chat(self, msg_id, sender_key, timestamp, content):
        self.cursor.execute('''
            INSERT OR IGNORE INTO chat_history (msg_id, sender_key, timestamp, content)
            VALUES (?, ?, ?, ?)
        ''', (msg_id, sender_key, timestamp, content))
        self.conn.commit()
        
    def get_all_chats(self):
        self.cursor.execute('SELECT msg_id, sender_key, timestamp, content FROM chat_history ORDER BY timestamp ASC')
        return [{"msg_id": r[0], "sender_key": r[1], "timestamp": r[2], "content": r[3]} for r in self.cursor.fetchall()]
        
    def get_chats_since(self, timestamp):
        self.cursor.execute('SELECT msg_id, sender_key, timestamp, content FROM chat_history WHERE timestamp > ? ORDER BY timestamp ASC', (timestamp,))
        return [{"msg_id": r[0], "sender_key": r[1], "timestamp": r[2], "content": r[3]} for r in self.cursor.fetchall()]

    def clear_chat_history(self):
        self.cursor.execute('DELETE FROM chat_history')
        self.conn.commit()
