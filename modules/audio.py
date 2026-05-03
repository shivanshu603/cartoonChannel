import os
import asyncio
import subprocess
import edge_tts
from mutagen.mp3 import MP3

# ─────────────────────────────────────────────────────────────────────
# VOICE POOL
# Each entry: (voice_name, gender_hint)
# All of these can speak Hindi text — they give very different character feels.
#
# MALE pool  (4 distinct voices):
#   hi-IN-MadhurNeural   → rich, deep, authoritative Hindi
#   ur-PK-AsadNeural     → Urdu male — smoother, slightly softer feel
#   en-IN-PrabhatNeural  → Indian English male — crisper, modern feel
#   en-IN-AaravNeural    → younger Indian male — lighter voice
#
# FEMALE pool (4 distinct voices):
#   hi-IN-SwaraNeural              → warm, natural Hindi female
#   ur-PK-UzmaNeural               → Urdu female — soft, melodic
#   en-IN-NeerjaNeural             → Indian English female — clear, confident
#   en-IN-NeerjaExpressiveNeural   → expressive Indian female — emotional range
# ─────────────────────────────────────────────────────────────────────

MALE_VOICES = [
    "hi-IN-MadhurNeural",    # slot 0 — deep Hindi
    "ur-PK-AsadNeural",      # slot 1 — smooth Urdu
    "en-IN-PrabhatNeural",   # slot 2 — crisp Indian English
    "en-IN-AaravNeural",     # slot 3 — lighter young male
]

FEMALE_VOICES = [
    "hi-IN-SwaraNeural",               # slot 0 — warm Hindi
    "ur-PK-UzmaNeural",                # slot 1 — melodic Urdu
    "en-IN-NeerjaNeural",              # slot 2 — confident Indian English
    "en-IN-NeerjaExpressiveNeural",    # slot 3 — expressive Indian
]

# ─────────────────────────────────────────────────────────────────────
# FEEL PRESETS — control speed + pitch per voice role
# Applied on top of whichever voice is chosen
# ─────────────────────────────────────────────────────────────────────

FEEL_PRESETS = {
    "NARRATOR": {"rate": "+8%",  "pitch": "-3Hz",  "volume": "+8%"},
    "HERO":     {"rate": "+18%", "pitch": "+2Hz",  "volume": "+10%"},
    "VILLAIN":  {"rate": "-10%", "pitch": "-12Hz", "volume": "+12%"},
    "ELDER":    {"rate": "-12%", "pitch": "-6Hz",  "volume": "+6%"},
    "CHILD":    {"rate": "+28%", "pitch": "+8Hz",  "volume": "+8%"},
    "SIDEKICK": {"rate": "+20%", "pitch": "+4Hz",  "volume": "+10%"},
    "FEMALE":   {"rate": "+8%",  "pitch": "+0Hz",  "volume": "+8%"},
    "DEFAULT":  {"rate": "+8%",  "pitch": "+0Hz",  "volume": "+8%"},
}

# ─────────────────────────────────────────────────────────────────────
# CHARACTER → VOICE SLOT ASSIGNMENT
# We assign voice slots based on character order of appearance.
# Slot is stored in character_profiles so it stays consistent across parts.
# ─────────────────────────────────────────────────────────────────────

# NARRATOR always uses slot 0 of its gender pool
NARRATOR_VOICE = MALE_VOICES[0]   # hi-IN-MadhurNeural


def _assign_voice_slot(char_profiles: dict, char_name: str, gender: str) -> int:
    """
    Assign a voice slot to a new character.
    Each gender pool has 4 slots. Characters get assigned sequentially
    (skipping slot 0 for males since that's NARRATOR).
    Returns slot index 0-3.
    """
    pool_size = len(MALE_VOICES)   # same size for both pools

    # Slot 0 male = NARRATOR — skip for male characters
    used_slots = set()
    for name, data in char_profiles.items():
        if name == "NARRATOR":
            continue
        cg = data.get("gender", "male").lower()
        if cg == gender.lower():
            slot = data.get("voice_slot")
            if slot is not None:
                used_slots.add(slot)

    start = 1 if gender.lower() == "male" else 0
    for slot in range(start, pool_size):
        if slot not in used_slots:
            return slot
    # All slots taken — cycle back (slot 1 for male, slot 0 for female)
    return start


def _resolve_profile(gender: str, voice_type: str, voice_slot: int) -> dict:
    """
    Build final TTS call params from gender + role + assigned slot.
    """
    pool   = FEMALE_VOICES if gender.lower() == "female" else MALE_VOICES
    slot   = max(0, min(voice_slot, len(pool) - 1))
    voice  = pool[slot]
    preset = FEEL_PRESETS.get(voice_type.upper(), FEEL_PRESETS["DEFAULT"])
    return {"voice": voice, **preset}


# ─────────────────────────────────────────────────────────────────────

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
        char_profiles = scene.get("character_profiles", {})

        # Backward compat
        if not script_lines and scene.get("text"):
            script_lines = [{"tag": "NARRATOR", "voice_type": "NARRATOR",
                              "gender": "male", "text": scene["text"]}]
        if not script_lines:
            print(f"   Scene {scene_id}: no lines")
            return scene

        # ── Assign voice slots to any new characters ──────────────────
        for name, data in char_profiles.items():
            if name == "NARRATOR":
                continue
            if "voice_slot" not in data:
                gender = data.get("gender", "male").lower()
                slot   = _assign_voice_slot(char_profiles, name, gender)
                data["voice_slot"] = slot

        print(f"   Scene {scene_id} — {len(script_lines)} lines")
        # Print voice assignments for debug
        for name, data in char_profiles.items():
            if name == "NARRATOR":
                continue
            g    = data.get("gender", "male")
            vt   = data.get("voice",  "HERO")
            slot = data.get("voice_slot", 0)
            pool = FEMALE_VOICES if g == "female" else MALE_VOICES
            vname = pool[min(slot, len(pool)-1)]
            print(f"      {name}: {g} | {vt} | slot {slot} → {vname.split('-')[2][:12]}")

        clip_paths   = []
        char_timings = []
        current_time = 0.0

        for i, line in enumerate(script_lines):
            tag        = str(line.get("tag", "NARRATOR")).upper().strip()
            voice_type = str(line.get("voice_type", "DEFAULT")).upper().strip()
            text       = str(line.get("text", "")).strip()
            if not text:
                continue

            # Resolve voice
            if tag == "NARRATOR":
                profile = {
                    "voice":  NARRATOR_VOICE,
                    **FEEL_PRESETS["NARRATOR"]
                }
            else:
                cp     = char_profiles.get(tag, {})
                gender = cp.get("gender", "male").lower()
                slot   = cp.get("voice_slot", 1)
                profile = _resolve_profile(gender, voice_type, slot)

            filename = f"line_{scene_id}_{i:03d}_{tag}.mp3"

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
                vshort = profile["voice"].split("-")[2][:10]
                print(f"      [{tag}|{vshort}] ({dur:.1f}s): {text[:45]}{'...' if len(text)>45 else ''}")
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

        scene["audio_path"]   = final_path
        scene["duration"]     = self.get_audio_duration(final_path)
        scene["char_timings"] = char_timings
        scene["character_profiles"] = char_profiles   # save updated slots back

        print(f"   ✅ {scene['duration']:.1f}s | {len(char_timings)} lines")
        return scene

    async def process_script(self, script_data):
        print(f"🎙️ Multi-Voice Audio Engine — {len(script_data)} scene(s)...")
        for i, scene in enumerate(script_data):
            try:
                script_data[i] = await self.process_scene(scene)
            except Exception as e:
                print(f"   Scene {i} failed: {e}")
        return script_data
