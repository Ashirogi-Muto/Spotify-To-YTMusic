import os
import sys
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from config import BASE_DIR

console = Console()

class SetupWizard:
    def __init__(self):
        self.env_path = BASE_DIR / ".env"
        self.raw_headers_path = BASE_DIR / "raw_headers.txt"
        self.auth_json_path = BASE_DIR / "headers_auth.json"

    def run(self):
        console.print(Panel("[bold cyan]Welcome to the Spotify → YT Music Setup Wizard![/bold cyan]\n"
                            "Let's get your API credentials set up.", expand=False))
        
        # Check Spotify
        if not self._check_spotify_creds():
            self._setup_spotify()
            
        # Check YT Music
        if not self._check_ytmusic_creds():
            self._setup_ytmusic()
            
        console.print("\n[bold green]✅ Initialization complete! You are ready to start migrating.[/bold green]")
        
    def _check_spotify_creds(self) -> bool:
        if not self.env_path.exists():
            return False
            
        content = self.env_path.read_text()
        return "SPOTIPY_CLIENT_ID" in content and "SPOTIPY_CLIENT_SECRET" in content
        
    def _check_ytmusic_creds(self) -> bool:
        return self.auth_json_path.exists()

    def _setup_spotify(self):
        console.print("\n[bold blue]=== Step 1: Spotify Developer API ===[/bold blue]")
        console.print("To read your Spotify library, you need a free Developer API key.")
        console.print("1. Go to: [link=https://developer.spotify.com/dashboard/]https://developer.spotify.com/dashboard/[/link]")
        console.print("2. Log in and click [bold]'Create app'[/bold].")
        console.print("3. Give it a name/desc (e.g., 'Migration Tool').")
        console.print("4. Set Redirect URI exactly to: [bold cyan]http://127.0.0.1:8080/callback/[/bold cyan]")
        console.print("5. Check the developer terms box and save.")
        console.print("6. Click [bold]'Settings'[/bold] or [bold]'Show Client Secret'[/bold].\n")
        
        client_id = Prompt.ask("[yellow]Paste your Spotify Client ID[/yellow]").strip()
        client_secret = Prompt.ask("[yellow]Paste your Spotify Client Secret[/yellow]").strip()
        
        env_content = ""
        if self.env_path.exists():
            env_content = self.env_path.read_text()
            
        # Remove old ones if they exist (safeguard)
        lines = [line for line in env_content.splitlines() if not line.startswith("SPOTIPY_")]
        
        lines.append(f"SPOTIPY_CLIENT_ID={client_id}")
        lines.append(f"SPOTIPY_CLIENT_SECRET={client_secret}")
        lines.append(f"SPOTIPY_REDIRECT_URI=http://127.0.0.1:8080/callback/")
        
        self.env_path.write_text("\n".join(lines) + "\n")
        
        # Also inject into current environment so we don't need a restart
        os.environ["SPOTIPY_CLIENT_ID"] = client_id
        os.environ["SPOTIPY_CLIENT_SECRET"] = client_secret
        os.environ["SPOTIPY_REDIRECT_URI"] = "http://127.0.0.1:8080/callback/"
        
        console.print("[green]✓ Spotify credentials saved to .env![/green]")

    def _setup_ytmusic(self):
        console.print("\n[bold red]=== Step 2: YouTube Music Authentication ===[/bold red]")
        console.print("To modify YouTube Music, we need your authenticated request headers.")
        console.print("1. Open Firefox/Chrome and go to [link=https://music.youtube.com]music.youtube.com[/link]. Ensure you are logged in.")
        console.print("2. Open Developer Tools (F12) -> Go to the [bold]'Network'[/bold] tab.")
        console.print("3. In the Network filter box, type: [cyan]browse[/cyan]")
        console.print("4. Click on the first row that appears (usually just named 'browse').")
        console.print("5. In the details pane on the right, look for [bold]'Request Headers'[/bold].")
        console.print("   - In Firefox: Click the raw toggle and copy everything.")
        console.print("   - In Chrome: Find 'Request Headers', click 'View source' (if available) or copy the entire block starting with an 'accept:' line.")
        
        console.print(f"\n[bold yellow]ACTION REQUIRED:[/bold yellow] Paste the copied headers into the file [cyan]{self.raw_headers_path}[/cyan]")
        
        # Ensure file exists and is empty
        self.raw_headers_path.write_text("")
        
        while True:
            Prompt.ask("\n[bold]Press ENTER once you have pasted the headers and saved the file...[/bold]")
            headers_raw = self.raw_headers_path.read_text().strip()
            
            if not headers_raw:
                console.print("[red]File is still empty! Please paste the headers and try again.[/red]")
                continue
                
            if "Cookie:" not in headers_raw and "cookie:" not in headers_raw:
                console.print("[red]The headers are missing the 'cookie:' field. Make sure you copied the entire Request Headers block.[/red]")
                continue
            
            try:
                import ytmusicapi
                # ytmusicapi.setup takes a multiline string of raw headers
                ytmusicapi.setup(filepath=str(self.auth_json_path), headers_raw=headers_raw)
                
                # Setup adds comments, let's verify it wrote realistic JSON
                with open(self.auth_json_path, 'r') as f:
                    content = f.read()
                    if "user-agent" not in content.lower():
                        raise ValueError("Auth file seems incomplete")
                        
                console.print(f"[green]✓ YouTube Music auth file generated successfully at {self.auth_json_path.name}![/green]")
                break
            except Exception as e:
                console.print(f"[bold red]Failed to parse headers:[/bold red] {e}")
                console.print("[yellow]Please try copying the raw request headers again.[/yellow]")

def run_wizard():
    wizard = SetupWizard()
    wizard.run()

if __name__ == "__main__":
    run_wizard()
