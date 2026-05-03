import os
import asyncio
import subprocess
import edge_tts
from mutagen.mp3 import MP3

# ── Voice feel presets — applied on top of gender-based voice ────────
# gender is determined per-character by brain.py
# feel controls rate/pitch/volume only

FEEL_PRESETS = {
    "NARRATOR": {"rate": "+8%",  "pitch": "-3Hz",  "volume": "+8%"},
    "HERO":     {"rate": "+18%", "pitch": "+2Hz",  "volume": "+10%"},
    "VILLAIN":  {"rate": "-10%", "pitch": "-12Hz", "volume": "+12%"},
    "ELDER":    {"rate": "-12%", "pitch": "-6Hz",  "volume": "+6%"},
    "CHILD":    {"rate": "+28%", "pitch": "+8Hz",  "volume": "+8%"},
    "SIDEKICK": {"rate": "+20%", "pitch": "+4Hz",  "volume": "+10%"},
    "FEMALE":   {"rate": "+8%",  "pitch": "+0Hz",  "volume": "+8%"},
    # default fallback
    "DEFAULT":  {"rate": "+8%",  "pitch": "+0Hz",  "volume": "+8%"},
}

MALE_VOICE   = "hi-IN-MadhurNeural"
FEMALE_VOICE = "hi-IN-SwaraNeural"


def _resolve_profile(gender: str, feel: str) -> dict:
    """
    gender: 'male' | 'female'  (from brain's character_profiles)
    feel:   any key in FEEL_PRESETS  (HERO, VILLAIN, CHILD, etc.)
    Returns full TTS profile dict.
    """
    voice   = FEMALE_VOICE if gender.lower() == "female" else MALE_VOICE
    preset  = FEEL_PRESETS.get(feel.upper(), FEEL_PRESETS["DEFAULT"])
    return {"voice": voice, **preset}


class AudioEngine:

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Generate one TTS clip ────────────────────────────────────────

    async def _generate_clip(self, text, profile, filename, retries=3):
        output_path = os.path.join(self.output_dir, filename)
        for attempt in range(retries):
            try:
                comm = edge_tts.Communicate(
                    text=text,
                    voice=profile["voice"],
                    rate=profile["rate"],
                    pitch=profile["pitch"],
                    volume=profile["volume"],
                )
                await comm.save(output_path)
                return output_path
            except Exception as e:
                print(f"      TTS error attempt {attempt+1}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2)
                else:
                    raise

    def get_audio_duration(self, path):
        try:
            return MP3(path).info.length
        except Exception:
            return 0.0

    def _merge_clips(self, clip_paths, output_path):
        list_file = output_path.replace(".mp3", "_list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for p in clip_paths:
                f.write(f"file '{p}'\n")
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-acodec", "libmp3lame", "-q:a", "2",
            output_path,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        try:
            os.remove(list_file)
        except Exception:
            pass
        if r.returncode != 0:
            print(f"   Merge failed: {r.stderr[-200:]}")
            return False
        return True

    # ── Process one scene ────────────────────────────────────────────

    async def process_scene(self, scene):
        scene_id      = scene.get("id", 1)
        script_lines  = scene.get("script_lines", [])
        char_profiles = scene.get("character_profiles", {})

        # Backward compat: plain text scene
        if not script_lines and scene.get("text"):
            script_lines = [{"tag": "NARRATOR", "voice_type": "NARRATOR",
                              "gender": "male", "text": scene["text"]}]

        if not script_lines:
            print(f"   Scene {scene_id}: no lines")
            return scene

        print(f"   Scene {scene_id} — {len(script_lines)} lines")

        clip_paths   = []
        char_timings = []
        current_time = 0.0

        for i, line in enumerate(script_lines):
            tag        = str(line.get("tag", "NARRATOR")).upper().strip()
            voice_type = str(line.get("voice_type", "DEFAULT")).upper().strip()
            text       = str(line.get("text", "")).strip()
            if not text:
                continue

            # Resolve gender: check saved character_profiles first
            if tag == "NARRATOR":
                gender = "male"
            else:
                cp     = char_profiles.get(tag, {})
                gender = str(cp.get("gender", line.get("gender", "male"))).lower().strip()

            profile  = _resolve_profile(gender, voice_type)
            filename = f"line_{scene_id}_{i:03d}_{tag}.mp3"

            try:
                path = await self._generate_clip(text, profile, filename)
                dur  = self.get_audio_duration(path)
                clip_paths.append(path)
                char_timings.append({
                    "tag":    tag,
                    "gender": gender,
                    "feel":   voice_type,
                    "voice":  profile["voice"],
                    "text":   text,
                    "start":  current_time,
                    "end":    current_time + dur,
                })
                current_time += dur
                print(f"      [{tag}|{gender}|{voice_type}] {profile['voice'].split('-')[2][:6]} ({dur:.1f}s): {text[:45]}{'...' if len(text)>45 else ''}")
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"      Skipping [{tag}]: {e}")

        if not clip_paths:
            print(f"   Scene {scene_id}: no clips generated")
            return scene

        if len(clip_paths) == 1:
            final_path = clip_paths[0]
        else:
            final_path = os.path.join(self.output_dir, f"voice_{scene_id}.mp3")
            if not self._merge_clips(clip_paths, final_path):
                final_path = clip_paths[0]

        total_dur = self.get_audio_duration(final_path)
        scene["audio_path"]   = final_path
        scene["duration"]     = total_dur
        scene["char_timings"] = char_timings
        print(f"   ✅ {total_dur:.1f}s | {len(char_timings)} lines | voices: { {t['tag']:t['voice'].split('-')[2][:6] for t in char_timings} }")
        return scene

    async def process_script(self, script_data):
        print(f"🎙️ Audio Engine — {len(script_data)} scene(s)...")
        for i, scene in enumerate(script_data):
            try:
                script_data[i] = await self.process_scene(scene)
            except Exception as e:
                print(f"   Scene {i} failed: {e}")
        return script_data
