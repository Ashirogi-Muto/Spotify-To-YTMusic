import logging
from typing import List, Dict, Optional, Any, Tuple
from sentence_transformers import SentenceTransformer, util
from rapidfuzz import fuzz

from src.normalizer import Normalizer
from src.config import MATCH_SEMANTIC, MATCH_LOW_CONFIDENCE

logger = logging.getLogger(__name__)

class MatcherEngine:
    def __init__(self):
        logger.info("Initializing NLP Model: all-MiniLM-L6-v2")
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
    @staticmethod
    def _parse_duration_to_ms(duration_str) -> int:
        """Parse ytmusicapi duration string like '3:45' or '1:02:30' to milliseconds."""
        if not duration_str:
            return 0
        if isinstance(duration_str, (int, float)):
            return int(duration_str) * 1000
        parts = str(duration_str).split(':')
        try:
            if len(parts) == 3:
                return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
            elif len(parts) == 2:
                return (int(parts[0]) * 60 + int(parts[1])) * 1000
            else:
                return int(parts[0]) * 1000
        except (ValueError, IndexError):
            return 0

    def evaluate_candidates(self, spotify_song: Dict[str, Any], yt_candidates: List[Dict]) -> Tuple[Optional[str], Optional[float], str]:
        """
        Evaluate YT candidates against the spotify track.
        Returns: yt_video_id, similarity_score, match_status
        """
        if not yt_candidates:
            return None, None, 'UNMATCHED'
            
        # 1. Filter candidates by Duration and Version Compatibility
        valid_candidates = []
        s_duration = spotify_song['duration_ms']
        s_flags = spotify_song['version_flags']
        s_artist = spotify_song['primary_artist'].lower()
        s_title_norm = spotify_song['normalized_title']
        
        # Duration tolerance: 5% or 8 seconds, whichever is smaller
        duration_tolerance = min(8000.0, s_duration * 0.05) if s_duration > 0 else 8000.0
        
        for cand in yt_candidates:
            # ytmusicapi returns duration as string like '3:45', or 'duration_seconds' as int
            c_duration = cand.get('duration_seconds', 0)
            if isinstance(c_duration, int) and c_duration > 0:
                c_duration = c_duration * 1000
            else:
                c_duration = self._parse_duration_to_ms(cand.get('duration', ''))
            
            # If candidate gives no duration, we skip duration check (it happens sometimes)
            if c_duration > 0 and abs(c_duration - s_duration) > duration_tolerance:
                continue

            c_title = cand.get('title', '')
            c_artist = cand['artists'][0]['name'].lower() if cand.get('artists') else ''
            
            # Version compatibility check
            if not Normalizer.is_version_compatible(s_flags, c_title):
                continue
                
            # Artist Validation: Spotify Primary Artist must appear in YT Artist field OR title
            if s_artist not in c_artist and s_artist not in c_title.lower():
                continue
                
            valid_candidates.append(cand)
            
        if not valid_candidates:
            return None, None, 'UNMATCHED'
            
        if len(valid_candidates) == 1:
            return valid_candidates[0]['videoId'], 1.0, 'EXACT'
            
        # 2. NLP Semantic Matching (Fallback) when multiple candidates remain
        best_candidate = None
        best_score = -1.0
        
        s_embed_text = f"{s_title_norm} {s_artist}"
        s_embedding = self.model.encode(s_embed_text, convert_to_tensor=True)
        
        for cand in valid_candidates:
            c_artist = cand['artists'][0]['name'] if cand.get('artists') else ''
            c_title = Normalizer.normalize_text(cand.get('title', ''))
            
            c_embed_text = f"{c_title} {c_artist}"
            c_embedding = self.model.encode(c_embed_text, convert_to_tensor=True)
            
            score = util.cos_sim(s_embedding, c_embedding).item()
            
            if score > best_score:
                best_score = score
                best_candidate = cand
                
        # 3. Apply Decision Thresholds
        status = 'UNMATCHED'
        if best_score >= MATCH_SEMANTIC:
            status = 'SEMANTIC'
        elif best_score >= MATCH_LOW_CONFIDENCE:
            status = 'LOW_CONFIDENCE'
            
        return best_candidate['videoId'] if best_candidate else None, best_score, status
