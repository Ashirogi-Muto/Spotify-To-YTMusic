import re
import unicodedata

# Common version identifiers found in track titles.
VERSION_FLAGS = [
    "live", "remix", "lofi", "slowed", "reverb",
    "acoustic", "instrumental", "cover", "edit", 
    "radio edit", "extended", "remaster", "anniversary"
]

class Normalizer:
    @staticmethod
    def normalize_text(text: str) -> str:
        """
        Normalize via:
        1. NFKC unicode normalization
        2. Lowercase
        3. Remove EVERYTHING inside parentheses, brackets, or braces
        4. Strip any trailing hyphens/spaces left over
        """
        if not text:
            return ""
        
        # NFKC normalize and lowercase
        text = unicodedata.normalize('NFKC', text).lower()
        
        # Remove parentheses and brackets content e.g. "Song (Live at X)" -> "Song"
        text = re.sub(r'[\(\[].*?[\)\]]', '', text)
        
        # Cleanup extra spaces or lingering hyphens e.g. "Song - " -> "Song"
        text = text.replace('-', ' ').strip()
        text = re.sub(r'\s+', ' ', text)
        
        return text

    @staticmethod
    def extract_version_flags(raw_title: str) -> str:
        """
        Return a comma-separated string of version flags found in the raw title.
        Example: "Midnight City - Eric Prydz Private Remix" -> "remix"
                 "Hotel California (Live On MTV, 1994)" -> "live"
        """
        raw_lower = raw_title.lower()
        found_flags = set()
        
        for flag in VERSION_FLAGS:
            # simple substring search for now (could be regex \b boundaries if needed)
            if re.search(r'\b' + re.escape(flag) + r'\b', raw_lower):
                found_flags.add(flag)
                
        return ",".join(sorted(list(found_flags)))

    @staticmethod
    def is_version_compatible(spotify_flags: str, yt_title: str) -> bool:
        """
        If a yt candidate has a version flag NOT present in the spotify original, reject it.
        Example:
            Spotify original is "Song" (flags: "")
            YT candidate "Song (Live)" has "live" -> Reject.
            Spotify original is "Song (Remix)" (flags: "remix")
            YT candidate "Song (Remix)" has "remix" -> Accept.
        """
        spot_flags_set = set(f for f in spotify_flags.split(',') if f) if spotify_flags else set()
        yt_flags_raw = Normalizer.extract_version_flags(yt_title) if yt_title else ""
        yt_flags_set = set(f for f in yt_flags_raw.split(',') if f) if yt_flags_raw else set()
        
        # If the YT title contains a flag that is NOT in the spotify version, it's incompatible.
        # It's okay if the YT title *lacks* a flag because YT titles might be sloppy.
        # But we don't want to accidentally match a Live YT video for a Studio Spotify track.
        incompatible_flags = yt_flags_set - spot_flags_set
        
        if incompatible_flags:
            return False
            
        return True
