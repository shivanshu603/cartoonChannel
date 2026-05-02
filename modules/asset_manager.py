import os
import requests
import random
from dotenv import load_dotenv

load_dotenv()


class AssetManager:
    """
    Downloads 2-3 short mood-matched video clips from Pexels
    to mix between AI images for visual variety.
    """

    def __init__(self):
        self.api_key   = os.getenv("PEXELS_API_KEY", "")
        self.base_url  = "https://api.pexels.com/videos/search"
        self.headers   = {"Authorization": self.api_key}
        self.asset_dir = os.path.join(os.getcwd(), "assets", "video_clips")
        os.makedirs(self.asset_dir, exist_ok=True)

    def _clean_query(self, raw):
        bad = {
            "cinematic","asmr","satisfying","mysterious","dramatic","epic",
            "footage","clip","video","stock","style","mood",
        }
        words   = raw.lower().split()
        cleaned = [w for w in words if w not in bad and len(w) > 2 and w.isascii()]
        return " ".join(cleaned[:4]) if cleaned else None

    def search_clip(self, query, duration_min=3):
        clean = self._clean_query(query)
        if not clean:
            return None

        word_list = clean.split()
        # Try progressively shorter queries
        attempts = [" ".join(word_list[:n]) for n in range(len(word_list), 0, -1)]

        for q in attempts:
            try:
                resp = requests.get(
                    self.base_url,
                    headers=self.headers,
                    params={"query": q, "per_page": 10, "orientation": "portrait"},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                videos = resp.json().get("videos", [])
                valid  = [v for v in videos if v.get("duration", 0) >= duration_min
                          and v.get("height", 0) > v.get("width", 1)]
                if not valid:
                    valid = videos
                if not valid:
                    continue

                chosen = random.choice(valid)
                files  = chosen.get("video_files", [])
                port   = [f for f in files if f.get("height", 0) > f.get("width", 1)]
                if not port:
                    port = files
                port.sort(key=lambda f: f.get("width", 0) * f.get("height", 0), reverse=True)
                best = next((f for f in port if f.get("width", 9999) <= 1080), port[0])
                print(f"      ✅ Pexels clip: '{q}' → {best.get('width')}x{best.get('height')}")
                return best["link"]

            except Exception as e:
                print(f"      ⚠️ Pexels error for '{q}': {e}")
                continue

        return None

    def download_clip(self, url, filename):
        save_path = os.path.join(self.asset_dir, filename)
        if os.path.exists(save_path) and os.path.getsize(save_path) > 10_000:
            return save_path
        try:
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
            return save_path
        except Exception as e:
            print(f"      ❌ Download failed: {e}")
            return None

    def get_mood_clips(self, scene):
        """
        Download 2 mood-matched clips per scene using pexels_mood queries.
        Returns list of local file paths (may be empty if Pexels key missing).
        """
        if not self.api_key:
            print("   ⚠️ No PEXELS_API_KEY — skipping mood clips")
            return []

        part_num    = scene.get("part_number", 1)
        mood_queries = scene.get("pexels_moods", [])

        if not mood_queries:
            return []

        print(f"   🎥 Fetching {len(mood_queries)} mood clips for Part {part_num}...")
        paths = []

        for i, query in enumerate(mood_queries[:2]):  # max 2 clips
            url  = self.search_clip(query)
            if url:
                path = self.download_clip(url, f"mood_{part_num}_{i+1}.mp4")
                if path:
                    paths.append(path)

        return paths
