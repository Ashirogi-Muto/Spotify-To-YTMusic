import sys
import os
import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.db import Database
from src.spotify_client import SpotifyExtractionClient
from src.yt_client import YouTubeMusicClient
from src.normalizer import Normalizer
from src.matcher import MatcherEngine
from src.reconstruct import Reconstructor
from src.wipe import YTMusicWiper
from src.utils import generate_reports
from src.setup import SetupWizard

# Configure Rich Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

logger = logging.getLogger("main")
console = Console()

BANNER = """
╔══════════════════════════════════════════════════╗
║       Spotify → YT Music Migration Tool         ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║  1. Extract from Spotify                         ║
║  2. Match tracks to YT Music                     ║
║  3. Reconstruct playlists on YT Music            ║
║  4. Run full pipeline (1 → 2 → 3)               ║
║  ─────────────────────────────────────────────   ║
║  5. View migration status                        ║
║  6. Generate reports                             ║
║  7. Wipe YT Music playlists                      ║
║  8. Reset database (fresh start)                 ║
║  9. Re-authenticate Spotify                      ║
║  10. API Setup Wizard (First time setup)         ║
║  0. Exit                                         ║
║                                                  ║
╚══════════════════════════════════════════════════╝
"""


def phase_prompt(phase_name: str) -> str:
    """Prompt user after a phase completes. Returns 'p', 'r', or 'e'."""
    while True:
        console.print(f"\n[bold green]✓ {phase_name} complete.[/bold green]")
        choice = console.input("[bold cyan][P]roceed / [R]etry / [E]xit: [/bold cyan]").strip().lower()
        if choice in ('p', 'r', 'e', 'proceed', 'retry', 'exit'):
            return choice[0]
        console.print("[red]Invalid choice. Enter P, R, or E.[/red]")


def do_extract(db: Database):
    """Phase 1: Extract liked songs and playlists from Spotify."""
    console.rule("[bold blue]Phase 1: Spotify Extraction")
    spotify = SpotifyExtractionClient()

    # Extract Liked Songs
    liked_songs = spotify.extract_liked_songs()
    for s in liked_songs:
        s['normalized_title'] = Normalizer.normalize_text(s['raw_title'])
        s['version_flags'] = Normalizer.extract_version_flags(s['raw_title'])
    db.insert_songs(liked_songs)

    # Store Liked Songs pseudo-playlist
    db.insert_playlist("liked_songs_pseudo_id", "Your Likes", "Imported Spotify Liked Songs", False)
    db.insert_playlist_songs([
        ("liked_songs_pseudo_id", s['spotify_id'], idx)
        for idx, s in enumerate(liked_songs)
    ])

    # Extract Playlists (with 403 tracking)
    playlists, playlist_tracks_map, stats = spotify.extract_playlists(db)
    for pl in playlists:
        db.insert_playlist(pl['id'], pl['name'], pl['description'], pl['is_public'])

        tracks = playlist_tracks_map.get(pl['id'], [])
        for s in tracks:
            s['normalized_title'] = Normalizer.normalize_text(s['raw_title'])
            s['version_flags'] = Normalizer.extract_version_flags(s['raw_title'])

        db.insert_songs(tracks)
        db.insert_playlist_songs([
            (pl['id'], t['spotify_id'], idx)
            for idx, t in enumerate(tracks)
        ])

    console.print("[green]✓ Extraction complete and saved to DB.[/green]")
    
    # Show stats summary
    table = Table(title="Extraction Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_row("Liked Songs", str(len(liked_songs)))
    table.add_row("Total Playlists", str(stats['total']))
    table.add_row("Playlists Succeeded", str(stats['succeeded']))
    table.add_row("Playlists 403'd", str(stats['failed_403']))
    table.add_row("Playlists Skipped (cached)", str(stats['skipped_existing']))
    console.print(table)

    return stats


def do_match(db: Database):
    """Phase 2: Match unmatched songs to YT Music using semantic matching."""
    console.rule("[bold blue]Phase 2: YT Music Semantic Matching")

    unmatched = db.get_unmatched_songs()
    if len(unmatched) == 0:
        console.print("[green]All tracks already matched. Nothing to do.[/green]")
        return

    logger.info(f"Found {len(unmatched)} unmatched tracks. Booting Matcher Engine...")
    yt = YouTubeMusicClient()
    matcher = MatcherEngine()

    matched_count = 0
    for idx, row in enumerate(unmatched):
        song_dict = dict(row)
        query = f"{song_dict['raw_title']} {song_dict['primary_artist']}"

        logger.info(f"Matching [{idx+1}/{len(unmatched)}]: {query}")

        candidates = yt.search_songs(query)
        if not candidates:
            candidates = yt.search_videos(query)

        best_id, score, status = matcher.evaluate_candidates(song_dict, candidates)
        db.update_song_match(song_dict['spotify_id'], best_id, score, status)
        
        if status != 'UNMATCHED':
            matched_count += 1

        if (idx + 1) % 50 == 0:
            logger.info(f"Checkpoint: {idx+1}/{len(unmatched)} processed ({matched_count} matched so far)")

    console.print(f"[green]✓ Matching complete. {matched_count}/{len(unmatched)} matched.[/green]")


def do_reconstruct(db: Database):
    """Phase 3: Create playlists on YT Music from matched tracks."""
    console.rule("[bold blue]Phase 3: YT Playlist Reconstruction")
    yt = YouTubeMusicClient()
    reconstructor = Reconstructor(yt, db)
    reconstructor.reconstruct_playlists()
    console.print("[green]✓ Reconstruction complete.[/green]")


def do_full_pipeline(db: Database):
    """Run all 3 phases sequentially with prompts between each."""
    phases = [
        ("Extraction", lambda: do_extract(db)),
        ("Matching", lambda: do_match(db)),
        ("Reconstruction", lambda: do_reconstruct(db)),
    ]

    for i, (name, fn) in enumerate(phases):
        while True:
            fn()
            action = phase_prompt(f"Phase {i+1}: {name}")
            if action == 'p':
                break  # proceed to next phase
            elif action == 'r':
                console.print(f"[yellow]↻ Retrying {name}...[/yellow]")
                continue  # re-run same phase
            elif action == 'e':
                console.print("[bold red]Exiting pipeline. Progress saved to DB.[/bold red]")
                return

    # Finalization
    console.rule("[bold blue]Migration Complete")
    db.mark_run_timestamp()
    generate_reports(db)
    console.print("[green]✓ Full pipeline complete! Reports generated.[/green]")


def do_status(db: Database):
    """Show migration status dashboard."""
    console.rule("[bold blue]Migration Status")
    status = db.get_status()

    table = Table(title="Database Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green", justify="right")
    table.add_row("Total Songs", str(status['total_songs']))
    table.add_row("Matched", str(status['matched']))
    table.add_row("Unmatched", str(status['unmatched']))
    table.add_row("Match Attempted", str(status['match_attempted']))
    table.add_row("Total Playlists", str(status['total_playlists']))
    table.add_row("Last Run", status['last_run'])
    
    if status['total_songs'] > 0:
        pct = (status['matched'] / status['total_songs']) * 100
        table.add_row("Match Rate", f"{pct:.1f}%")

    console.print(table)


def do_reports(db: Database):
    """Generate matched/unmatched/summary reports."""
    console.rule("[bold blue]Report Generation")
    db.mark_run_timestamp()
    generate_reports(db)
    console.print("[green]✓ Reports generated: matched.json, unmatched.json, summary.txt[/green]")


def do_wipe():
    """Wipe all user-created YT Music playlists."""
    console.rule("[bold red]YT Music Playlist Wipe")
    yt = YouTubeMusicClient()
    wiper = YTMusicWiper(yt)
    wiper.wipe_user_playlists()


def do_reset(db: Database):
    """Reset the database (drop all tables, fresh start)."""
    console.rule("[bold red]Database Reset")
    console.print("[bold red]⚠ WARNING: This will delete ALL extracted data![/bold red]")
    console.print("All songs, playlists, and match results will be lost.")
    
    confirm = console.input("\n[bold]Type 'RESET' to confirm: [/bold]").strip()
    if confirm == "RESET":
        db.reset()
        console.print("[green]✓ Database reset complete. All tables cleared and re-initialized.[/green]")
    else:
        console.print("[yellow]Reset cancelled.[/yellow]")


def do_reauth_spotify():
    """Re-authenticate with Spotify (delete cache and re-run OAuth)."""
    console.rule("[bold blue]Spotify Re-Authentication")
    
    cache_path = os.path.join(os.path.dirname(__file__), '.spotipy_cache')
    if os.path.exists(cache_path):
        os.remove(cache_path)
        console.print("[yellow]♻ Deleted old token cache.[/yellow]")
    
    from config import SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI
    from spotipy.oauth2 import SpotifyOAuth
    
    auth = SpotifyOAuth(
        client_id=SPOTIPY_CLIENT_ID,
        client_secret=SPOTIPY_CLIENT_SECRET,
        redirect_uri=SPOTIPY_REDIRECT_URI,
        scope='playlist-read-private playlist-read-collaborative user-library-read',
        cache_path=cache_path,
        open_browser=False
    )
    
    auth_url = auth.get_authorize_url()
    console.print(f"\n[bold cyan]Open this URL in your browser:[/bold cyan]")
    console.print(f"[link={auth_url}]{auth_url}[/link]\n")
    console.print("[dim]After login, you'll be redirected to a page that won't load.[/dim]")
    console.print("[dim]Copy the ENTIRE URL from the address bar and paste below.[/dim]\n")
    
    redirect_url = console.input("[bold]Paste redirect URL: [/bold]").strip()
    
    try:
        code = auth.parse_response_code(redirect_url)
        auth.get_access_token(code)
        console.print("[green]✓ Spotify re-authentication successful![/green]")
    except Exception as e:
        console.print(f"[red]✗ Authentication failed: {e}[/red]")


def main():
    """Interactive menu-driven main loop."""
    # Check credentials on startup
    wizard = SetupWizard()
    if not wizard._check_spotify_creds() or not wizard._check_ytmusic_creds():
        wizard.run()

    db = Database()

    console.print(BANNER, style="bold")

    while True:
        try:
            choice = console.input("\n[bold cyan]Select option (0-9): [/bold cyan]").strip()

            if choice == '1':
                do_extract(db)
            elif choice == '2':
                do_match(db)
            elif choice == '3':
                do_reconstruct(db)
            elif choice == '4':
                do_full_pipeline(db)
            elif choice == '5':
                do_status(db)
            elif choice == '6':
                do_reports(db)
            elif choice == '7':
                do_wipe()
            elif choice == '8':
                do_reset(db)
            elif choice == '9':
                do_reauth_spotify()
            elif choice == '10':
                SetupWizard().run()
            elif choice == '0':
                console.print("[bold]Goodbye! 👋[/bold]")
                db.close()
                sys.exit(0)
            else:
                console.print("[red]Invalid option. Enter a number 0-9.[/red]")

            # Re-show menu after action
            console.print(BANNER, style="bold")

        except KeyboardInterrupt:
            console.print("\n[bold red]Interrupted. Progress saved. Returning to menu...[/bold red]")
            console.print(BANNER, style="bold")
            continue


if __name__ == "__main__":
    try:
        # Support --auto flag for backward compatibility
        if "--auto" in sys.argv:
            db = Database()
            dry_run = "--dry-run" in sys.argv
            
            do_extract(db)
            do_match(db)
            
            if not dry_run:
                do_reconstruct(db)
            else:
                console.print("[yellow]--dry-run: Skipping reconstruction.[/yellow]")
            
            db.mark_run_timestamp()
            generate_reports(db)
            db.close()
        else:
            main()
    except KeyboardInterrupt:
        console.print("[bold red]\nProcess interrupted by user. Safe to resume later.\n[/bold red]")
        sys.exit(0)
