# Spotify to YouTube Music Migration Tool

This project provides a robust, interactive command-line pipeline to migrate your Spotify library (Liked Songs and Playlists) to YouTube Music.

## Features

- **Interactive Menu**: Run all phases step-by-step from a unified menu.
- **Smart Semantic Matching**: Maps Spotify tracks to YouTube Music using semantic comparisons of title and artist, handling live/remix version matches correctly.
- **Resilient Pipeline**: Uses a local SQLite database to cache progress. If the extraction or matching fails or is interrupted, you can resume exactly where you left off.
- **Reporting**: Generates detailed `matched.json`, `unmatched.json`, and `summary.txt` reports in the `output/` directory.

## Prerequisites

1. Set up your `.env` file in the root directory:
   ```env
   SPOTIPY_CLIENT_ID=your_spotify_client_id
   SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
   SPOTIPY_REDIRECT_URI=http://127.0.0.1:8080/callback/
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. Generate your YouTube Music `headers_auth.json` (see ytmusicapi documentation for header extraction).

## Usage

Simply run the main interactive script:

```bash
python3 main.py
```

### Menu Options

1. **Extract from Spotify**: Pulls your Liked Songs and Playlists into the local database.
2. **Match tracks to YT Music**: Queries YouTube Music to find semantic matches for all extracted tracks.
3. **Reconstruct playlists**: Creates the matched playlists on your YouTube Music account.
4. **Run full pipeline**: Runs steps 1 → 2 → 3 sequentially, pausing for confirmation after each phase.
5. **View migration status**: Check how many tracks are extracted, matched, or unmatched.
6. **Generate reports**: Writes matching reports to the `output/` directory.
7. **Wipe YT Music playlists**: Deletes all user-created playlists on YT Music (requires explicit confirmation). Useful for starting over.
8. **Reset database**: Wipes the local database cache for a fresh start.
9. **Re-authenticate Spotify**: Triggers a new Spotify OAuth flow.

## Architecture

- `main.py` - The interactive CLI entry point.
- `src/` - Core modules (`config.py`, `db.py`, `matcher.py`, `spotify_client.py`, `yt_client.py`, etc.)
- `tests/` - Contains the `verify_pipeline.py` script for end-to-end testing.
- `output/` - Generated reports land here.

## Testing

To run the end-to-end verification tests (dry-run safe):

```bash
PYTHONPATH=. python3 tests/verify_pipeline.py
```


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

