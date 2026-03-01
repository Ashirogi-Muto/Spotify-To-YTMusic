import logging
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass, field
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from src.config import SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI

logger = logging.getLogger(__name__)

class SpotifyExtractionClient:
    def __init__(self):
        if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
            raise ValueError("SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET environment variables must be set.")
            
        auth_manager = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope="playlist-read-private playlist-read-collaborative user-library-read",
            cache_path=".spotipy_cache"
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)

    def extract_liked_songs(self) -> List[Dict[str, Any]]:
        """
        Fetch all user's liked tracks. Returns a list of standardized track dicts.
        """
        logger.info("Extracting Liked Songs from Spotify...")
        tracks = []
        limit = 50
        offset = 0

        while True:
            results = self.sp.current_user_saved_tracks(limit=limit, offset=offset)
            items = results.get('items', [])
            if not items:
                break
            
            for item in items:
                track = item.get('track')
                if track:
                    tracks.append(self._format_track(track))
            
            offset += limit
            
        logger.info(f"Extracted {len(tracks)} Liked Songs.")
        return tracks

    def extract_playlists(self, db) -> Tuple[List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]], Dict[str, int]]:
        """
        Fetch all user playlists and their tracks.
        Skips playlists that have already been saved to the database.
        Returns:
            - List of playlists (id, name, desc, public)
            - Dictionary mapping playlist_id to a list of its tracks.
            - Stats dict: {total, succeeded, failed_403, skipped_existing}
        """
        logger.info("Extracting Playlists from Spotify...")
        playlists = []
        playlist_tracks_map = {}
        stats = {"total": 0, "succeeded": 0, "failed_403": 0, "skipped_existing": 0}
        
        limit = 50
        offset = 0
        
        # Get existing playlists from DB so we can skip extracting their tracks again
        existing_playlists = {row['spotify_playlist_id'] for row in db.get_playlists()}
        
        while True:
            results = self.sp.current_user_playlists(limit=limit, offset=offset)
            items = results.get('items', [])
            if not items:
                break
                
            for item in items:
                playlists.append({
                    "id": item["id"],
                    "name": item["name"],
                    "description": item.get("description", ""),
                    "is_public": item.get("public", False)
                })
            
            offset += limit

        stats["total"] = len(playlists)

        for i, pl in enumerate(playlists):
            pl_id = pl["id"]
            if pl_id in existing_playlists:
                logger.debug(f"Skipping already-extracted playlist {pl['name']} ({i+1}/{len(playlists)})")
                stats["skipped_existing"] += 1
                continue
                
            logger.info(f"Fetching tracks for playlist {pl['name']} ({i+1}/{len(playlists)})")
            tracks = self._extract_playlist_tracks(pl_id)
            playlist_tracks_map[pl_id] = tracks
            
            if len(tracks) > 0:
                stats["succeeded"] += 1
            else:
                # Check if it was a 403 (we already logged it in _extract_playlist_tracks)
                stats["failed_403"] += 1
                logger.warning(f"  ⚠ Playlist '{pl['name']}' returned 0 tracks (likely 403 - not owned)")

        logger.info(f"\n📊 Extraction Stats: {stats['total']} total playlists")
        logger.info(f"   ✅ {stats['succeeded']} succeeded")
        logger.info(f"   ❌ {stats['failed_403']} returned 403 (0 tracks)")
        logger.info(f"   ⏭  {stats['skipped_existing']} skipped (already in DB)")
            
        return playlists, playlist_tracks_map, stats

    def _extract_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        tracks = []
        # API docs: max limit is 50 for both /items and Get Playlist endpoints
        limit = 50
        offset = 0
        
        while True:
            try:
                # The new /items endpoint only works for playlists the user OWNS or COLLABORATES on.
                # For followed/saved playlists from other users, it returns 403.
                results = self.sp._get(
                    f"playlists/{playlist_id}/items", 
                    limit=limit, 
                    offset=offset, 
                    additional_types="track"
                )
            except spotipy.exceptions.SpotifyException as e:
                if e.http_status == 403:
                    # Fallback: Use the Get Playlist endpoint which works for any playlist
                    # the user can see (owned, followed, or public). It embeds tracks.
                    logger.info(f"Playlist {playlist_id}: /items returned 403 (not owner/collaborator). "
                                f"Falling back to Get Playlist endpoint...")
                    return self._extract_playlist_tracks_via_get_playlist(playlist_id)
                if e.http_status == 429:
                    retry_after = int(e.headers.get('Retry-After', 30)) if e.headers else 30
                    logger.warning(f"Rate limited! Spotify says wait {retry_after}s. Sleeping...")
                    import time
                    time.sleep(retry_after + 1)
                    continue
                raise e
                
            items = results.get('items', [])
            if not items:
                break
                
            for item in items:
                # New /items endpoint returns track data under 'item' key,
                # not 'track'. Check both for compatibility.
                track_data = item.get('track') or item.get('item')
                if track_data and isinstance(track_data, dict):
                    tracks.append(self._format_track(track_data))
                    
            offset += limit
            
        return tracks

    def _extract_playlist_tracks_via_get_playlist(self, playlist_id: str) -> List[Dict[str, Any]]:
        """
        Fallback: Use GET /playlists/{id} which works for any visible playlist.
        The response includes a 'tracks' object with paginated items.
        """
        tracks = []
        try:
            playlist = self.sp.playlist(playlist_id, additional_types=("track",))
            items = playlist.get('tracks', {}).get('items', [])
            for item in items:
                track_data = item.get('track') or item.get('item')
                if track_data and isinstance(track_data, dict):
                    tracks.append(self._format_track(track_data))
            
            # Handle pagination if more than 100 tracks via the 'next' URL
            next_url = playlist.get('tracks', {}).get('next')
            while next_url:
                results = self.sp._get(next_url)
                for item in results.get('items', []):
                    track_data = item.get('track') or item.get('item')
                    if track_data and isinstance(track_data, dict):
                        tracks.append(self._format_track(track_data))
                next_url = results.get('next')
                
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 403:
                logger.warning(f"Cannot access playlist {playlist_id} at all (403). Skipping.")
            else:
                raise e
        return tracks

    def _format_track(self, track: Dict) -> Dict[str, Any]:
        """Flatten spotipy track dict to our structured DB form"""
        primary_artist = ""
        if track.get('artists') and len(track['artists']) > 0:
            primary_artist = track['artists'][0].get('name', 'Unknown Artist')
            
        return {
            "spotify_id": track.get('id', ''),
            "raw_title": track.get('name', ''),
            # normalized_title and version_flags will be computed by normalizer.py later
            "normalized_title": "",  
            "primary_artist": primary_artist,
            "duration_ms": track.get('duration_ms', 0),
            "version_flags": "" 
        }
