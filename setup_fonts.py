"""
Run this ONCE before starting the bot:
    python setup_fonts.py

Downloads NotoSansDevanagari-Bold.ttf into assets/fonts/
so Hindi subtitles render correctly instead of □□□ boxes.
"""

import os
import urllib.request

FONT_DIR  = os.path.join(os.getcwd(), "assets", "fonts")
FONT_PATH = os.path.join(FONT_DIR, "NotoSans-Bold.ttf")

# Direct download from Google Fonts GitHub (stable URL)
FONT_URL = (
    "https://github.com/google/fonts/raw/main/ofl/notosans/static/NotoSans-Bold.ttf"
)

def download_font():
    os.makedirs(FONT_DIR, exist_ok=True)

    if os.path.exists(FONT_PATH) and os.path.getsize(FONT_PATH) > 10_000:
        print(f"✅ Font already present: {FONT_PATH}")
        return

    print(f"⬇️  Downloading NotoSans-Bold.ttf ...")
    try:
        urllib.request.urlretrieve(FONT_URL, FONT_PATH)
        size_kb = os.path.getsize(FONT_PATH) // 1024
        print(f"✅ Font downloaded ({size_kb} KB) → {FONT_PATH}")
    except Exception as e:
        print(f"❌ Download failed: {e}")
        print("   Manual fix: download NotoSans-Bold.ttf and place it in assets/fonts/")

if __name__ == "__main__":
    download_font()