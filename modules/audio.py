import os
import asyncio
import subprocess
import edge_tts
from mutagen.mp3 import MP3

# ─────────────────────────────────────────────────────────────────────
# VOICE STRATEGY
#
# Only hi-IN voices are 100% reliable for Hindi text.
# We use pitch + rate manipulation to create distinct character voices.
#
# NARRATOR : Madhur  — base settings (deep, authoritative)
# MALE chars: Madhur  — varied pitch/rate per role
# FEMALE chars: Swara — varied pitch/rate per role
# ─────────────────────────────────────────────────────────────────────

MALE_VOICE   = "hi-IN-MadhurNeural"
FEMALE_VOICE = "hi-IN-SwaraNeural"

# Each voice_type has distinct pitch + rate so characters sound different
# even when using same base voice
FEEL_PRESETS = {
    # role          rate      pitch     volume
    "NARRATOR": {"rate": "+5%",  "pitch": "-4Hz",  "volume": "+5%"},   # deep, measured
    "HERO":     {"rate": "+22%", "pitch": "+4Hz",  "volume": "+12%"},  # fast, bright, energetic
    "VILLAIN":  {"rate": "-15%", "pitch": "-14Hz", "volume": "+15%"},  # very slow, very deep
    "ELDER":    {"rate": "-18%", "pitch": "-8Hz",  "volume": "+5%"},   # slow, wise, calm
    "CHILD":    {"rate": "+30%", "pitch": "+12Hz", "volume": "+10%"},  # very fast, high pitch
    "SIDEKICK": {"rate": "+25%", "pitch": "+6Hz",  "volume": "+12%"},  # fast, cheerful
    "FEMALE":   {"rate": "+10%", "pitch": "+2Hz",  "volume": "+8%"},   # natural female
    "DEFAULT":  {"rate": "+5%",  "pitch": "+0Hz",  "volume": "+8%"},
}


def _canonical(name: str) -> str:
    """Normalize character name: uppercase, underscores→spaces, strip."""
    return name.upper().strip().replace("_", " ")


def _resolve_profile(gender: str, voice_type: str) -> dict:
    voice  = FEMALE_VOICE if gender.lower() == "female" else MALE_VOICE
    preset = FEEL_PRESETS.get(voice_type.upper(), FEEL_PRESETS["DEFAULT"])
    return {"voice": voice, **preset}


class AudioEngine:

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "audio_clips")
        os.makedirs(self.output_dir, exist_ok=True)

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

    async def process_scene(self, scene):
        scene_id      = scene.get("id", 1)
        script_lines  = scene.get("script_lines", [])

        # Normalize ALL character profile keys to canonical form
        raw_profiles  = scene.get("character_profiles", {})
        char_profiles = {_canonical(k): v for k, v in raw_profiles.items()}
        scene["character_profiles"] = char_profiles

        # Backward compat
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
            # Normalize tag to canonical form too
            raw_tag    = str(line.get("tag", "NARRATOR")).upper().strip()
            tag        = _canonical(raw_tag)
            voice_type = str(line.get("voice_type", "DEFAULT")).upper().strip()
            text       = str(line.get("text", "")).strip()
            if not text:
                continue

            if tag == "NARRATOR":
                profile = {"voice": MALE_VOICE, **FEEL_PRESETS["NARRATOR"]}
            else:
                cp      = char_profiles.get(tag, {})
                gender  = str(cp.get("gender", "male")).lower().strip()
                profile = _resolve_profile(gender, voice_type)

            # Safe filename — replace spaces with underscores
            safe_tag = tag.replace(" ", "_")[:20]
            filename = f"line_{scene_id}_{i:03d}_{safe_tag}.mp3"

            try:
                path = await self._generate_clip(text, profile, filename)
                dur  = self.get_audio_duration(path)
                clip_paths.append(path)
                char_timings.append({
                    "tag":   tag,
                    "voice": profile["voice"],
                    "feel":  voice_type,
                    "text":  text,
                    "start": current_time,
                    "end":   current_time + dur,
                })
                current_time += dur
                vshort = profile["voice"].split("-")[2][:8]
                feel_s = f"{profile['pitch']},{profile['rate']}"
                print(f"      [{tag}|{vshort}|{feel_s}] ({dur:.1f}s): {text[:40]}{'...' if len(text)>40 else ''}")
                await asyncio.sleep(0.4)
            except Exception as e:
                print(f"      Skipping [{tag}]: {e}")

        if not clip_paths:
            return scene

        if len(clip_paths) == 1:
            final_path = clip_paths[0]
        else:
            final_path = os.path.join(self.output_dir, f"voice_{scene_id}.mp3")
            if not self._merge_clips(clip_paths, final_path):
                final_path = clip_paths[0]

        scene["audio_path"]        = final_path
        scene["duration"]          = self.get_audio_duration(final_path)
        scene["char_timings"]      = char_timings
        scene["character_profiles"] = char_profiles

        print(f"   ✅ {scene['duration']:.1f}s | {len(char_timings)} lines")
        return scene

    async def process_script(self, script_data):
        print(f"🎙️ Audio Engine — {len(script_data)} scene(s)...")
        for i, scene in enumerate(script_data):
            try:
                script_data[i] = await self.process_scene(scene)
            except Exception as e:
                print(f"   Scene {i} failed: {e}")
        return script_data
