import os
import asyncio
import subprocess
import edge_tts
from mutagen.mp3 import MP3

# ── Voice profiles for each character tag ────────────────────────────
# Edge TTS Hindi voices available:
#   hi-IN-MadhurNeural  — male, deep, natural
#   hi-IN-SwaraNeural   — female, warm, expressive

VOICE_PROFILES = {
    "NARRATOR": {
        "voice":  "hi-IN-MadhurNeural",
        "rate":   "+10%",
        "pitch":  "-4Hz",
        "volume": "+8%",
        "label":  "Narrator",
    },
    "HERO": {
        "voice":  "hi-IN-MadhurNeural",
        "rate":   "+20%",
        "pitch":  "+2Hz",
        "volume": "+10%",
        "label":  "Hero",
    },
    "VILLAIN": {
        "voice":  "hi-IN-MadhurNeural",
        "rate":   "-8%",
        "pitch":  "-10Hz",
        "volume": "+12%",
        "label":  "Villain",
    },
    "FEMALE": {
        "voice":  "hi-IN-SwaraNeural",
        "rate":   "+8%",
        "pitch":  "+0Hz",
        "volume": "+8%",
        "label":  "Female",
    },
    "CHILD": {
        "voice":  "hi-IN-SwaraNeural",
        "rate":   "+25%",
        "pitch":  "+6Hz",
        "volume": "+8%",
        "label":  "Child",
    },
    "ELDER": {
        "voice":  "hi-IN-MadhurNeural",
        "rate":   "-15%",
        "pitch":  "-6Hz",
        "volume": "+6%",
        "label":  "Elder",
    },
    "SIDEKICK": {
        "voice":  "hi-IN-MadhurNeural",
        "rate":   "+18%",
        "pitch":  "+4Hz",
        "volume": "+10%",
        "label":  "Sidekick",
    },
}

DEFAULT_PROFILE = VOICE_PROFILES["NARRATOR"]


class AudioEngine:

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

    async def _generate_line(self, text, tag, filename, retries=3):
        profile = VOICE_PROFILES.get(tag.upper(), DEFAULT_PROFILE)
        output_path = os.path.join(self.output_dir, filename)

        for attempt in range(retries):
            try:
                communicate = edge_tts.Communicate(
                    text=text,
                    voice=profile["voice"],
                    rate=profile["rate"],
                    pitch=profile["pitch"],
                    volume=profile["volume"],
                )
                await communicate.save(output_path)
                return output_path
            except Exception as e:
                print(f"      Audio error [{tag}] attempt {attempt+1}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise e

    def get_audio_duration(self, file_path):
        try:
            return MP3(file_path).info.length
        except Exception:
            return 0.0

    def _merge_clips(self, clip_paths, output_path):
        list_file = output_path.replace(".mp3", "_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-acodec", "libmp3lame", "-q:a", "2",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            os.remove(list_file)
        except Exception:
            pass

        if result.returncode != 0:
            print(f"   Merge failed:\n{result.stderr[-200:]}")
            return False
        return True

    async def process_scene(self, scene):
        scene_id     = scene.get("id", 1)
        script_lines = scene.get("script_lines", [])

        if not script_lines and scene.get("text"):
            script_lines = [{"tag": "NARRATOR", "text": scene["text"]}]

        if not script_lines:
            print(f"   Scene {scene_id}: no script lines")
            return scene

        print(f"   Scene {scene_id} — {len(script_lines)} lines")

        clip_paths   = []
        char_timings = []
        current_time = 0.0

        for i, line in enumerate(script_lines):
            tag        = line.get("tag", "NARRATOR").upper()
            voice_type = line.get("voice_type", tag).upper()   # resolved by brain.py
            text       = line.get("text", "").strip()
            if not text:
                continue

            profile  = VOICE_PROFILES.get(voice_type, DEFAULT_PROFILE)
            filename = f"line_{scene_id}_{i:03d}_{tag}.mp3"

            try:
                path = await self._generate_line(text, tag, filename)
                dur  = self.get_audio_duration(path)
                clip_paths.append(path)
                char_timings.append({
                    "tag":   tag,
                    "label": profile["label"],
                    "text":  text,
                    "start": current_time,
                    "end":   current_time + dur,
                })
                current_time += dur
                print(f"      [{tag} → {profile['label']}] ({dur:.1f}s): {text[:50]}{'...' if len(text)>50 else ''}")
                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"      Skipping line {i} [{tag}]: {e}")
                continue

        if not clip_paths:
            print(f"   Scene {scene_id}: no clips generated")
            return scene

        if len(clip_paths) == 1:
            final_path = clip_paths[0]
        else:
            final_path = os.path.join(self.output_dir, f"voice_{scene_id}.mp3")
            ok = self._merge_clips(clip_paths, final_path)
            if not ok:
                final_path = clip_paths[0]

        total_dur = self.get_audio_duration(final_path)
        scene["audio_path"]   = final_path
        scene["duration"]     = total_dur
        scene["char_timings"] = char_timings

        tags_used = list({t["tag"] for t in char_timings})
        print(f"   Scene {scene_id}: {total_dur:.1f}s | voices used: {tags_used}")
        return scene

    async def process_script(self, script_data):
        print(f"Multi-Voice Audio Engine — {len(script_data)} scene(s)...")
        for i, scene in enumerate(script_data):
            try:
                script_data[i] = await self.process_scene(scene)
            except Exception as e:
                print(f"   Scene {scene.get('id','?')} failed: {e}")
                continue
        return script_data