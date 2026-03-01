import os
import sys
import logging
from typing import List, Dict, Optional, Any
from ytmusicapi import YTMusic

from src.rate_limiter import yt_rate_limited
from src.config import YTMUSIC_AUTH_FILE

logger = logging.getLogger(__name__)

class YouTubeMusicClient:
    def __init__(self):
        if not YTMUSIC_AUTH_FILE.exists():
            self._try_generate_from_raw_headers()
            
        try:
            self.yt = YTMusic(str(YTMUSIC_AUTH_FILE))
        except Exception as e:
            logger.warning(f"Failed to load {YTMUSIC_AUTH_FILE.name}: {e}. Attempting regeneration...")
            # Delete the corrupted file and try to regenerate
            if YTMUSIC_AUTH_FILE.exists():
                YTMUSIC_AUTH_FILE.unlink()
            self._try_generate_from_raw_headers()
            try:
                self.yt = YTMusic(str(YTMUSIC_AUTH_FILE))
            except Exception as e2:
                logger.error(f"Still failed after regeneration: {e2}")
                sys.exit(1)

    def _try_generate_from_raw_headers(self):
        """Attempt to generate headers_auth.json from raw_headers.txt."""
        import ytmusicapi
        raw_headers_path = YTMUSIC_AUTH_FILE.parent / "raw_headers.txt"
        
        if raw_headers_path.exists():
            logger.info(f"Found {raw_headers_path.name}. Converting raw headers into {YTMUSIC_AUTH_FILE.name}...")
            with open(raw_headers_path, "r") as f:
                headers_raw = f.read()
            ytmusicapi.setup(filepath=str(YTMUSIC_AUTH_FILE), headers_raw=headers_raw)
            logger.info("Successfully generated authentication file!")
        else:
            print(f"ERROR: No '{YTMUSIC_AUTH_FILE.name}' or 'raw_headers.txt' file found.")
            print("YouTube Music requires authentication via your browser headers.")
            print("1. Open YouTube Music in your browser and open Developer Tools (F12) -> Network tab.")
            print("2. Search for a request (e.g. to 'browse'), and copy the entire 'Request Headers'.")
            print("3. Paste those raw headers into a new file named 'raw_headers.txt' in this directory.")
            print("4. Run the program again. It will automatically convert it into a secure session.")
            sys.exit(1)

    @yt_rate_limited
    def search_songs(self, query: str) -> List[Dict]:
        """Search for songs on YT Music."""
        return self.yt.search(query=query, filter="songs")

    @yt_rate_limited
    def search_videos(self, query: str) -> List[Dict]:
        """Search for videos on YT Music as fallback."""
        return self.yt.search(query=query, filter="videos")

    @yt_rate_limited
    def get_library_playlists(self) -> List[Dict]:
        """Get the user's library playlists (limit=5000)"""
        return self.yt.get_library_playlists(limit=5000)

    @yt_rate_limited
    def create_playlist(self, title: str, description: str, privacy_status: str = "PRIVATE") -> str:
        """Create a YTMusic playlist and return the ID. Can return dict on error."""
        return self.yt.create_playlist(title=title, description=description, privacy_status=privacy_status)

    @yt_rate_limited
    def add_playlist_items(self, playlist_id: str, video_ids: List[str]):
        """Add songs to a specific playlist."""
        return self.yt.add_playlist_items(playlistId=playlist_id, videoIds=video_ids, duplicates=False)

    @yt_rate_limited
    def delete_playlist(self, playlist_id: str):
        """Delete a YTMusic playlist."""
        return self.yt.delete_playlist(playlist_id)

    @yt_rate_limited
    def rate_song(self, video_id: str, rating: str = "LIKE"):
        """Like/Dislike a song."""
        return self.yt.rate_song(video_id, rating)
