import json
from pathlib import Path
from src.db import Database
from src.config import BASE_DIR

def generate_reports(db: Database):
    """
    Generate the matched.json, unmatched.json, and summary.txt files 
    based on the state of the database.
    """
    with db.conn:
        cursor = db.conn.cursor()
        
        # 1. Generate matched.json
        cursor.execute("SELECT * FROM songs WHERE match_status != 'UNMATCHED' AND yt_video_id IS NOT NULL")
        matched = [dict(row) for row in cursor.fetchall()]
        with open(BASE_DIR / 'output' / 'matched.json', 'w', encoding='utf-8') as f:
            json.dump(matched, f, indent=4)

        # 2. Generate unmatched.json
        cursor.execute("SELECT * FROM songs WHERE match_status = 'UNMATCHED' AND yt_video_id IS NULL")
        unmatched = [dict(row) for row in cursor.fetchall()]
        with open(BASE_DIR / 'output' / 'unmatched.json', 'w', encoding='utf-8') as f:
            json.dump(unmatched, f, indent=4)
            
        # 3. Generate summary.txt
        total_songs = len(matched) + len(unmatched)
        
        exact = sum(1 for m in matched if m['match_status'] == 'EXACT')
        semantic = sum(1 for m in matched if m['match_status'] == 'SEMANTIC')
        low_conf = sum(1 for m in matched if m['match_status'] == 'LOW_CONFIDENCE')
        
        avg_score = 0.0
        scores = [m['similarity_score'] for m in matched if m['similarity_score'] is not None and m['similarity_score'] > 0]
        if scores:
            avg_score = sum(scores) / len(scores)

        summary_data = [
            "=" * 40,
            " Spotify -> YT Music Migration Summary ",
            "=" * 40,
            f"Total Tracks Evaluated : {total_songs}",
            f"Total Matched          : {len(matched)}",
            f"Total Unmatched        : {len(unmatched)}",
            "-" * 40,
            "Match Breakdown:",
            f"  EXACT Matches        : {exact}",
            f"  SEMANTIC Matches     : {semantic}",
            f"  LOW_CONFIDENCE       : {low_conf}",
            "-" * 40,
            f"Average Semantic Score: {avg_score:.4f}",
            "=" * 40
        ]
        
        with open(BASE_DIR / 'output' / 'summary.txt', 'w', encoding='utf-8') as f:
            f.write("\n".join(summary_data))
            
        print("\n" + "\n".join(summary_data))
        
        # Update migration_meta stats
        with db.conn:
            db.conn.execute("INSERT OR REPLACE INTO migration_meta (key, value) VALUES (?, ?)", 
                          ("total_songs", str(total_songs)))
            db.conn.execute("INSERT OR REPLACE INTO migration_meta (key, value) VALUES (?, ?)", 
                          ("total_matched", str(len(matched))))
            db.conn.execute("INSERT OR REPLACE INTO migration_meta (key, value) VALUES (?, ?)", 
                          ("total_unmatched", str(len(unmatched))))
