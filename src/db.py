import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from src.config import DB_PATH, TOOL_VERSION

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._conn = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        """Initializes the database schema if it doesn't already exist."""
        with self.conn:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS songs (
                    spotify_id TEXT PRIMARY KEY,
                    raw_title TEXT NOT NULL,
                    normalized_title TEXT NOT NULL,
                    primary_artist TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    version_flags TEXT NOT NULL,
                    yt_video_id TEXT,
                    similarity_score REAL,
                    match_status TEXT DEFAULT 'UNMATCHED',
                    match_attempted BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_songs_yt_video_id ON songs(yt_video_id);
                CREATE INDEX IF NOT EXISTS idx_songs_match_attempted ON songs(match_attempted);

                CREATE TABLE IF NOT EXISTS playlists (
                    spotify_playlist_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    is_public BOOLEAN
                );

                CREATE TABLE IF NOT EXISTS playlist_songs (
                    playlist_id TEXT NOT NULL,
                    spotify_song_id TEXT NOT NULL,
                    position_index INTEGER NOT NULL,
                    FOREIGN KEY (playlist_id) REFERENCES playlists (spotify_playlist_id),
                    FOREIGN KEY (spotify_song_id) REFERENCES songs (spotify_id),
                    PRIMARY KEY (playlist_id, position_index)
                );
                
                CREATE INDEX IF NOT EXISTS idx_playlist_songs_playlist ON playlist_songs(playlist_id);

                CREATE TABLE IF NOT EXISTS migration_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            
            # Initialize or update meta info
            self.conn.execute(
                "INSERT OR REPLACE INTO migration_meta (key, value) VALUES (?, ?)", 
                ("tool_version", TOOL_VERSION)
            )

    def mark_run_timestamp(self):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO migration_meta (key, value) VALUES (?, ?)", 
                ("last_run_timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
            )

    def insert_songs(self, songs: List[Dict[str, Any]]):
        """Insert or ignore songs into the database for extraction."""
        with self.conn:
            self.conn.executemany("""
                INSERT OR IGNORE INTO songs 
                (spotify_id, raw_title, normalized_title, primary_artist, duration_ms, version_flags)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (
                    s['spotify_id'], 
                    s['raw_title'], 
                    s['normalized_title'], 
                    s['primary_artist'], 
                    s['duration_ms'], 
                    s['version_flags']
                ) for s in songs
            ])

    def insert_playlist(self, p_id: str, name: str, desc: str, is_public: bool):
        with self.conn:
            self.conn.execute("""
                INSERT OR IGNORE INTO playlists (spotify_playlist_id, name, description, is_public)
                VALUES (?, ?, ?, ?)
            """, (p_id, name, desc, is_public))

    def insert_playlist_songs(self, entries: List[tuple]):
        """entries is a list of tuples: (playlist_id, spotify_song_id, position_index)"""
        with self.conn:
            self.conn.executemany("""
                INSERT OR IGNORE INTO playlist_songs (playlist_id, spotify_song_id, position_index)
                VALUES (?, ?, ?)
            """, entries)

    def get_unmatched_songs(self) -> List[sqlite3.Row]:
        """Fetch songs that haven't been successfully matched yet, and haven't had a match attempted in this cycle."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM songs WHERE yt_video_id IS NULL AND match_attempted = 0")
        return cursor.fetchall()

    def update_song_match(self, spotify_id: str, yt_video_id: Optional[str], score: Optional[float], status: str):
        with self.conn:
            self.conn.execute("""
                UPDATE songs 
                SET yt_video_id = ?, similarity_score = ?, match_status = ?, match_attempted = 1, updated_at = CURRENT_TIMESTAMP
                WHERE spotify_id = ?
            """, (yt_video_id, score, status, spotify_id))
            
    def get_playlists(self) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM playlists")
        return cursor.fetchall()
        
    def get_playlist_tracks(self, playlist_id: str) -> List[sqlite3.Row]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT s.spotify_id, s.yt_video_id, ps.position_index, s.match_status
            FROM playlist_songs ps
            JOIN songs s ON ps.spotify_song_id = s.spotify_id
            WHERE ps.playlist_id = ?
            ORDER BY ps.position_index ASC
        """, (playlist_id,))
        return cursor.fetchall()

    def reset(self):
        """Drop all tables and re-initialize the schema. For fresh start."""
        with self.conn:
            self.conn.executescript("""
                DROP TABLE IF EXISTS playlist_songs;
                DROP TABLE IF EXISTS playlists;
                DROP TABLE IF EXISTS songs;
                DROP TABLE IF EXISTS migration_meta;
            """)
        self._init_db()

    def get_status(self) -> Dict[str, Any]:
        """Return a status dashboard of current DB state."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM songs")
        total_songs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM songs WHERE yt_video_id IS NOT NULL AND match_status != 'UNMATCHED'")
        matched = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM songs WHERE yt_video_id IS NULL OR match_status = 'UNMATCHED'")
        unmatched = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM songs WHERE match_attempted = 1")
        attempted = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM playlists")
        total_playlists = cursor.fetchone()[0]
        
        cursor.execute("SELECT value FROM migration_meta WHERE key = 'last_run_timestamp'")
        row = cursor.fetchone()
        last_run = row[0] if row else "Never"
        
        return {
            "total_songs": total_songs,
            "matched": matched,
            "unmatched": unmatched,
            "match_attempted": attempted,
            "total_playlists": total_playlists,
            "last_run": last_run
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
