import logging
from typing import List
from src.yt_client import YouTubeMusicClient
from src.db import Database

logger = logging.getLogger(__name__)

class Reconstructor:
    def __init__(self, yt_client: YouTubeMusicClient, db: Database):
        self.yt = yt_client
        self.db = db

    def reconstruct_playlists(self):
        """
        Creates playlists on YT Music based on DB 'playlists' table,
        then batches track inserts by exactly maintaining original order.
        """
        playlists = self.db.get_playlists()
        if not playlists:
            logger.info("No playlists found in DB to reconstruct.")
            return

        for pl in playlists:
            pl_spot_id = pl['spotify_playlist_id']
            pl_name = pl['name']
            pl_desc = pl['description'] or f"Imported from Spotify to YT Music."
            is_public = "PUBLIC" if pl['is_public'] else "PRIVATE"
            
            # Special case for "Spotify - Liked Songs" pseudo-playlist
            if pl_spot_id == "liked_songs_pseudo_id":
                is_public = "PRIVATE"

            tracks = self.db.get_playlist_tracks(pl_spot_id)
            if not tracks:
                logger.info(f"Skipping empty playlist: {pl_name}")
                continue

            valid_video_ids = [t['yt_video_id'] for t in tracks if t['yt_video_id'] is not None and t['match_status'] != 'UNMATCHED']
            if not valid_video_ids:
                logger.warning(f"Playlist '{pl_name}' has 0 matched tracks. Skipping creation.")
                continue

            logger.info(f"Creating YT Playlist: {pl_name}")
            new_yt_playlist_id = self.yt.create_playlist(
                title=pl_name, 
                description=pl_desc, 
                privacy_status=is_public
            )
            
            # Ensure playlist creation succeeded before continuing
            if isinstance(new_yt_playlist_id, dict) or not new_yt_playlist_id:
                logger.error(f"Failed to create YT playlist '{pl_name}'. Response: {new_yt_playlist_id}")
                continue

            # Batch Insert into YT Music (API limit is usually ~50-100 per request)
            BATCH_SIZE = 50
            for i in range(0, len(valid_video_ids), BATCH_SIZE):
                batch = valid_video_ids[i:i+BATCH_SIZE]
                logger.info(f" -> Inserting tracks {i+1} to {min(i+BATCH_SIZE, len(valid_video_ids))} into '{pl_name}'")
                self.yt.add_playlist_items(new_yt_playlist_id, batch)

        logger.info("Reconstruction phase complete.")
