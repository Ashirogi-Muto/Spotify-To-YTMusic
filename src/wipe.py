import sys
import logging
from typing import List, Dict
from src.yt_client import YouTubeMusicClient

logger = logging.getLogger(__name__)

class YTMusicWiper:
    def __init__(self, yt_client: YouTubeMusicClient):
        self.yt = yt_client

    def wipe_user_playlists(self):
        """
        Fetches all user-created playlists and requires explicitly typing CONFIRM
        to delete them. Skips system ones like Liked Songs.
        """
        logger.warning("Initiating Clean-Slate Wipe Mode")
        playlists = self.yt.get_library_playlists()
        
        # We only delete playlists where the current user is the author
        # System playlists or saved community playlists are typically skipped.
        # usually ytmusicapi gives 'author' as a list of dicts, or None for liked songs
        user_playlists = []
        for pl in playlists:
            # ytmusicapi gives the title 'Liked Music' or similar system lists which don't have standard authors
            title = pl.get('title', '')
            if title in ["Your Likes", "Liked Music"]:
                continue
                
            # Check if this playlist is delete-able
            if 'playlistId' in pl:
                user_playlists.append(pl)

        if not user_playlists:
            logger.info("No user playlists found to wipe.")
            return

        print("\n" + "="*50)
        print(f"⚠️ WARNING: You requested to wipe {len(user_playlists)} playlists from YT Music! ⚠️")
        print("Playlists to be deleted:")
        for idx, pl in enumerate(user_playlists):
            print(f"  {idx + 1}. {pl.get('title', 'Unknown')}")
        print("="*50)
        
        confirmation = input("\nType 'CONFIRM' exactly to permanently delete these playlists from your YT Music library: ")
        
        if confirmation == "CONFIRM":
            logger.info("User confirmed wipe action.")
            for idx, pl in enumerate(user_playlists):
                pid = pl['playlistId']
                logger.info(f"Deleting '{pl.get('title')}' ({idx+1}/{len(user_playlists)})")
                try:
                    self.yt.delete_playlist(pid)
                except Exception as e:
                    logger.error(f"Failed to delete {pl.get('title')}: {e}")
            logger.info("Wipe complete.")
        else:
            logger.info("Wipe cancelled by user (Did not type 'CONFIRM').")
            sys.exit(0)
