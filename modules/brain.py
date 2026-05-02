import os
import json
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MOVIES_FILE            = "movies_list.json"
STORY_STATE_FILE       = "story_state.json"
PARTS_PER_MOVIE        = 100
AUTO_EXPAND_THRESHOLD  = 5

# ── Disney Pixar style suffix — added to EVERY image prompt ──────────
PIXAR_STYLE = (
    "Disney Pixar 3D animated style, "
    "soft warm golden rim lighting, "
    "big expressive eyes, "
    "smooth rounded textures, "
    "vibrant rich colors, "
    "Pixar movie render quality, "
    "cinematic depth of field, "
    "ultra detailed, 8k"
)

# ── Character visual descriptions — so every prompt has consistent look
CHARACTER_LOOKS = {
    "harry potter": "young boy with round glasses, lightning bolt scar on forehead, messy black hair, Hogwarts robes",
    "dumbledore": "very old wizard with long silver beard and hair, half-moon spectacles, purple robes, kind wise eyes",
    "hermione": "young girl with bushy brown hair, smart curious eyes, Hogwarts robes, holding book or wand",
    "ron": "tall red-haired freckled boy, surprised expression, Hogwarts robes",
    "voldemort": "pale bald man with no nose, red serpent eyes, black flowing robes, terrifying expression",
    "snape": "pale man with greasy black hair, hooked nose, black robes, stern cold expression",
    "hagrid": "enormous friendly giant man with wild bushy black beard, kind brown eyes, heavy fur coat",
    "dobby": "small elf with huge green eyes, bat-like ears, wearing pillowcase, innocent expression",
    "gandalf": "old wizard with long grey beard and robes, pointed hat, glowing staff",
    "frodo": "small hobbit with curly brown hair, big feet, wide innocent eyes, carrying ring",
    "aragorn": "rugged dark-haired man with beard, ranger clothing, noble determined expression",
    "iron man": "man in red gold high-tech armor suit, glowing arc reactor chest, confident pose",
    "batman": "dark caped hero in black armor, cowl with pointy ears, serious expression",
    "simba": "young lion cub with big golden eyes, fluffy mane starting, curious expression",
}


class ContentBrain:

    def __init__(self):
        self.movies_data = self._load_movies()
        self.state       = self._load_state()

    # ─────────────────────────────────────────────────────────────────
    # MOVIES LIST
    # ─────────────────────────────────────────────────────────────────

    def _load_movies(self):
        if os.path.exists(MOVIES_FILE):
            with open(MOVIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"movies": [], "parts_per_movie": PARTS_PER_MOVIE,
                "current_movie_index": 0, "auto_expand": True}

    def _save_movies(self):
        with open(MOVIES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.movies_data, f, indent=2, ensure_ascii=False)

    def _remaining_movies(self):
        return len(self.movies_data["movies"]) - self.movies_data.get("current_movie_index", 0)

    def _auto_expand_movies(self):
        if not self.movies_data.get("auto_expand", True):
            return
        existing     = self.movies_data["movies"]
        completed    = self.state.get("completed_movies", [])
        done_str     = ", ".join((completed or existing)[-10:])
        existing_str = ", ".join(existing)
        print(f"🤖 Auto-expanding movie list ({len(existing)} currently)...")

        prompt = f"""
You are a YouTube content planner for a Hindi movie/story storytelling channel.
Already covered: {done_str}
Full existing list (NO repeats allowed): {existing_str}

Generate exactly 30 NEW story/movie titles for the queue.
Mix these categories for maximum variety:
- Hollywood blockbusters (Marvel, DC, Star Wars, Disney, Pixar, DreamWorks)
- Bollywood hits (action, drama, thriller)
- South Indian hits (dubbed in Hindi — RRR, KGF, Pushpa, Bahubali style)
- Anime feature films (Naruto movies, Dragon Ball, One Piece, Demon Slayer)
- Classic fairy tales & mythology (Greek, Norse, Hindu mythology stories)
- Famous book/novel stories (famous novels with rich characters)
- Video game stories (popular game lore — Zelda, God of War, etc.)
- Historical epics (famous historical figures/battles with dramatic story)

Rules:
- All must have rich plot with clear hero/villain/supporting characters
- NO TV series episodes — only complete movie/story arcs
- NO repeats from existing list
- Mix at least 3-4 categories above

Return ONLY a JSON array of 30 strings: ["Title 1", ..., "Title 30"]
"""
        for model_name in ["gemini-2.5-flash", "gemini-2.5-flash-lite" , "gemini-1.5-flash" , "gemini-1.5-flash-8b" , "gemini-1.5-pro" , ]:
            try:
                resp     = client.models.generate_content(
                    model=model_name, contents=prompt,
                    config={"response_mime_type": "application/json"}
                )
                clean    = resp.text.strip().replace("```json","").replace("```","").strip()
                new_list = json.loads(clean)
                if not isinstance(new_list, list):
                    continue
                existing_lower = [m.lower().strip() for m in existing]
                added = []
                for title in new_list:
                    if isinstance(title, str) and title.lower().strip() not in existing_lower:
                        self.movies_data["movies"].append(title)
                        added.append(title)
                self._save_movies()
                print(f"   ✅ Added {len(added)} new movies")
                for m in added:
                    print(f"      • {m}")
                return
            except Exception as e:
                print(f"   ⚠️ Expand failed ({model_name}): {e}")

    # ─────────────────────────────────────────────────────────────────
    # STORY STATE
    # ─────────────────────────────────────────────────────────────────

    def _load_state(self):
        if os.path.exists(STORY_STATE_FILE):
            with open(STORY_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        first = self.movies_data["movies"][0] if self.movies_data["movies"] else "Harry Potter and the Sorcerer's Stone"
        return {
            "current_movie": first, "current_movie_index": 0,
            "current_part": 0, "total_parts": PARTS_PER_MOVIE,
            "story_so_far": "", "last_scene_ending": "",
            "characters_introduced": [], "key_events_covered": [],
            "completed_movies": []
        }

    def _save_state(self):
        with open(STORY_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def _advance_to_next_movie(self):
        completed = self.state.get("completed_movies", [])
        if self.state["current_movie"] not in completed:
            completed.append(self.state["current_movie"])
        self.state["completed_movies"] = completed
        print(f"🎉 '{self.state['current_movie']}' complete!")

        if self._remaining_movies() <= AUTO_EXPAND_THRESHOLD:
            self._auto_expand_movies()

        next_idx = self.state["current_movie_index"] + 1
        movies   = self.movies_data["movies"]
        if next_idx >= len(movies):
            print("🔁 All movies done — restarting!")
            next_idx = 0
            self.state["completed_movies"] = []

        next_movie = movies[next_idx]
        print(f"🎬 Next movie: '{next_movie}'")
        self.state.update({
            "current_movie": next_movie, "current_movie_index": next_idx,
            "current_part": 0, "story_so_far": "", "last_scene_ending": "",
            "characters_introduced": [], "key_events_covered": [],
        })
        self.movies_data["current_movie_index"] = next_idx
        self._save_state()
        self._save_movies()

    # ─────────────────────────────────────────────────────────────────
    # CHARACTER LOOK HELPER
    # ─────────────────────────────────────────────────────────────────

    def _get_char_descriptions(self, character_names):
        """
        Build a string of character visual descriptions for the prompt.
        Helps Gemini write consistent Disney Pixar style image prompts.
        """
        descs = []
        for name in character_names[:4]:  # max 4 chars
            key = name.lower().strip()
            for known_key, look in CHARACTER_LOOKS.items():
                if known_key in key or key in known_key:
                    descs.append(f"{name}: {look}")
                    break
        return "\n".join(descs) if descs else "Use visually descriptive character appearances"

    # ─────────────────────────────────────────────────────────────────
    # SCRIPT GENERATION
    # ─────────────────────────────────────────────────────────────────

    def generate_script(self):
        if self._remaining_movies() <= AUTO_EXPAND_THRESHOLD:
            self._auto_expand_movies()
        if self.state["current_part"] >= PARTS_PER_MOVIE:
            self._advance_to_next_movie()

        self.state["current_part"] += 1
        part_number  = self.state["current_part"]
        movie_name   = self.state["current_movie"]
        story_so_far = self.state.get("story_so_far", "")
        last_ending  = self.state.get("last_scene_ending", "")
        chars        = self.state.get("characters_introduced", [])
        events       = self.state.get("key_events_covered", [])
        progress_pct = (part_number / PARTS_PER_MOVIE) * 100

        chars_str    = ", ".join(chars[-10:]) if chars else "None yet"
        events_str   = ", ".join(events[-8:]) if events else "None yet"
        char_descs   = self._get_char_descriptions(chars[-6:])

        story_context = ""
        if story_so_far:
            story_context = f"\nSTORY SO FAR:\n{story_so_far[-600:]}\n\nLAST SCENE:\n{last_ending}\n"

        if part_number == 1:
            part_instr = "PART 1 — Introduction. Set the world, introduce protagonist vividly. End with hook for Part 2."
        elif part_number == PARTS_PER_MOVIE:
            movies    = self.movies_data["movies"]
            nxt       = movies[(self.state["current_movie_index"] + 1) % len(movies)]
            part_instr = f"PART {PARTS_PER_MOVIE} — GRAND FINALE. Resolve all threads. Final line MUST say: \"Yeh thi '{movie_name}' ki poori kahani... Ab shuru hogi '{nxt}' ki kahani — subscribe karo!\""
        else:
            part_instr = f"PART {part_number}/{PARTS_PER_MOVIE} ({progress_pct:.0f}% done). Continue EXACTLY from last scene. End on cliffhanger."

        prompt = f"""
You are a master Hindi storyteller making a {PARTS_PER_MOVIE}-part Hindi YouTube Shorts series with MULTIPLE CHARACTER VOICES.

MOVIE/STORY: {movie_name}
PART: {part_number}/{PARTS_PER_MOVIE}
CHARACTERS SO FAR: {chars_str}
EVENTS COVERED: {events_str}
{story_context}
INSTRUCTION: {part_instr}

━━━ SCRIPT FORMAT — MOST IMPORTANT ━━━

Write the script as a mix of NARRATOR lines and CHARACTER dialogue lines.

TAG RULES:
- [NARRATOR] — Main storyteller (ALWAYS use this exact tag)
- For ALL other characters — use the CHARACTER'S ACTUAL NAME as the tag
  Examples: [HARRY], [VOLDEMORT], [HERMIONE], [SIMBA], [MUFASA], [FRODO]
- Use ONLY character names that actually appear in "{movie_name}"
- Assign voice types based on character role:
    Main hero/protagonist → fast, energetic voice
    Villain/antagonist    → slow, deep, menacing voice
    Female characters     → warm, expressive female voice
    Old/wise characters   → slow, calm, deep voice
    Child characters      → fast, high-pitched, excited voice
    Sidekick/funny        → cheerful, bouncy voice

Also return a "character_voices" map in JSON telling the system which voice type each character uses.
Voice type options: HERO, VILLAIN, FEMALE, CHILD, ELDER, SIDEKICK

SCRIPT RULES:
- NARRATOR lines describe action, emotions, scene transitions
- CHARACTER lines are actual spoken dialogue (no quotes)
- Mix 4-6 NARRATOR lines with 4-8 CHARACTER dialogue lines
- Total 50-60 seconds when read aloud (~130 words)
- Passionate Hinglish — Hindi mostly, thoda dramatic English
- End on cliffhanger (except final part)
- NARRATOR must be first and last line always

EXAMPLE for Harry Potter:
[NARRATOR] Hogwarts ki raat thi, andhere mein kuch hil raha tha...
[HARRY] Kaun hai wahan? Darr nahi lagta mujhe!
[NARRATOR] Tabhi ek bhaari awaaz aayi...
[VOLDEMORT] Hahaha... tum bahut bhaage ho chhote ladke. Ab kahan jaoge?
[HARRY] Main nahi rukunga! Mere doston ki raksha karunga!
[NARRATOR] Aur woh daud pada andheron mein... agli baar kya hoga?

character_voices for above example:
{{"HARRY": "HERO", "VOLDEMORT": "VILLAIN", "HERMIONE": "FEMALE", "DUMBLEDORE": "ELDER"}}

━━━ IMAGE PROMPT RULES — MOST IMPORTANT ━━━

Generate exactly 7 image_prompts.
Each is a DIFFERENT visual shot/moment from this scene.

STYLE REQUIREMENT — ALL images MUST be in this EXACT style:
"{PIXAR_STYLE}"

This style MUST appear at the END of every single image prompt.
Without this, images will look bad. Do NOT forget it.

CHARACTER APPEARANCES to use consistently:
{char_descs}

For each prompt:
1. Describe WHO is in scene (use exact character look from above)
2. Describe WHAT they are doing
3. Describe WHERE (setting, background, atmosphere)
4. Describe LIGHTING and MOOD
5. End with the EXACT style string above

EXAMPLE of a CORRECT image prompt:
"Harry Potter young boy with round glasses lightning bolt scar messy black hair Hogwarts robes, sitting at wooden desk reading glowing letter with shocked expression, cozy bedroom with brick walls candlelight, warm orange glow casting soft shadows, {PIXAR_STYLE}"

━━━ PEXELS MOOD CLIPS ━━━
Generate 2 pexels_moods — 3-4 word English search terms for real atmosphere clips.
Examples: "castle fog night", "candles dark room", "forest moonlight mist"

Return ONLY valid JSON:
[
  {{
    "id": 1,
    "movie": "{movie_name}",
    "part_number": {part_number},
    "total_parts": {PARTS_PER_MOVIE},
    "title": "{movie_name} | Part {part_number} — [catchy Hindi scene name]",
    "scene_title": "[3-5 word dramatic Hindi scene name, e.g. 'Andheron Ka Raaz']",
    "script_lines": [
      {{"tag": "NARRATOR", "text": "Jungle ki raat thi..."}},
      {{"tag": "HARRY",    "text": "Main nahi darta!"}},
      {{"tag": "NARRATOR", "text": "Tabhi ek awaaz aayi..."}}
    ],
    "character_voices": {{
      "HARRY": "HERO",
      "VOLDEMORT": "VILLAIN",
      "HERMIONE": "FEMALE",
      "DUMBLEDORE": "ELDER"
    }},
    "hook_text": "Part {part_number}: [5 dramatic Hindi words]",
    "image_prompts": [
      "[Shot 1 full detailed prompt ending with Pixar style]",
      "[Shot 2 full detailed prompt ending with Pixar style]",
      "[Shot 3 full detailed prompt ending with Pixar style]",
      "[Shot 4 full detailed prompt ending with Pixar style]",
      "[Shot 5 full detailed prompt ending with Pixar style]",
      "[Shot 6 full detailed prompt ending with Pixar style]",
      "[Shot 7 full detailed prompt ending with Pixar style]"
    ],
    "pexels_moods": ["3-4 word mood 1", "3-4 word mood 2"],
    "new_characters": ["new character names only in this part"],
    "new_events": ["2-3 key plot points from this part"],
    "story_summary": "2-3 sentence complete story summary up to this part",
    "scene_ending": "Exact last moment of this part for Part {part_number + 1} continuity"
  }}
]

IMPORTANT:
- script_lines "tag" must be NARRATOR or the CHARACTER'S ACTUAL NAME (all caps)
- character_voices maps each character name → voice type (HERO/VILLAIN/FEMALE/CHILD/ELDER/SIDEKICK)
- scene_title is a short dramatic Hindi name for THIS specific scene
- "text" must NOT contain the tag prefix — just clean dialogue
"""

        models = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash"]

        for model_name in models:
            for attempt in range(3):
                try:
                    print(f"   🔄 {model_name} (attempt {attempt+1})")
                    response = client.models.generate_content(
                        model=model_name, contents=prompt,
                        config={"response_mime_type": "application/json"}
                    )
                    clean  = response.text.strip().replace("```json","").replace("```","").strip()
                    result = json.loads(clean)
                    if isinstance(result, dict):
                        result = [result]

                    scene = result[0]

                    # Validate image prompts have Pixar style
                    prompts_list = scene.get("image_prompts", [])
                    fixed = []
                    for p in prompts_list:
                        if "Pixar" not in p and "pixar" not in p:
                            p = p.rstrip(" ,") + f", {PIXAR_STYLE}"
                        fixed.append(p)
                    scene["image_prompts"] = fixed

                    # Validate / normalise script_lines
                    VOICE_TYPES = {"NARRATOR","HERO","VILLAIN","FEMALE","CHILD","ELDER","SIDEKICK"}
                    # character_voices: {"HARRY": "HERO", "VOLDEMORT": "VILLAIN", ...}
                    char_voices = scene.get("character_voices", {})
                    # Normalize keys to uppercase
                    char_voices = {k.upper().strip(): v.upper().strip() for k, v in char_voices.items()}
                    scene["character_voices"] = char_voices

                    raw_lines = scene.get("script_lines", [])
                    clean_lines = []
                    for ln in raw_lines:
                        if not isinstance(ln, dict):
                            continue
                        tag  = str(ln.get("tag", "NARRATOR")).upper().strip()
                        txt  = str(ln.get("text", "")).strip()
                        if not txt:
                            continue
                        # NARRATOR stays as-is; other tags are character names
                        # Resolve voice type for audio engine
                        if tag == "NARRATOR":
                            voice_type = "NARRATOR"
                        elif tag in VOICE_TYPES:
                            voice_type = tag   # old-style fallback
                        else:
                            # tag is a character name like "HARRY"
                            voice_type = char_voices.get(tag, "HERO")
                        clean_lines.append({
                            "tag":        tag,
                            "voice_type": voice_type,
                            "text":       txt,
                        })

                    # Fallback: old-style plain "text" field
                    if not clean_lines and scene.get("text"):
                        clean_lines = [{"tag": "NARRATOR", "voice_type": "NARRATOR", "text": scene["text"]}]
                    scene["script_lines"] = clean_lines
                    # Build plain text for subtitles / backward compat
                    scene["text"] = " ".join(ln["text"] for ln in clean_lines)

                    result[0] = scene

                    tags_used = list({ln["tag"] for ln in clean_lines})
                    print(f"   ✅ Part {part_number} | {len(fixed)} images | moods: {scene.get('pexels_moods',[])} | chars: {tags_used}")

                    # Update story state
                    for c in scene.get("new_characters", []):
                        if c not in self.state["characters_introduced"]:
                            self.state["characters_introduced"].append(c)
                    self.state["key_events_covered"].extend(scene.get("new_events", []))
                    self.state["key_events_covered"] = self.state["key_events_covered"][-30:]
                    if scene.get("story_summary"):
                        self.state["story_so_far"]      = scene["story_summary"]
                    if scene.get("scene_ending"):
                        self.state["last_scene_ending"] = scene["scene_ending"]
                    self._save_state()
                    return result

                except Exception as e:
                    err = str(e)
                    print(f"   ❌ {model_name}: {err[:150]}")
                    if "503" in err or "high demand" in err:
                        time.sleep(10)
                        continue
                    else:
                        break

        self.state["current_part"] -= 1
        self._save_state()
        print("❌ All models failed.")
        return None


if __name__ == "__main__":
    brain = ContentBrain()
    out   = brain.generate_script()
    if out:
        with open("latest_script.json", "w", encoding="utf-8") as f:
            json.dump(out, f, indent=4, ensure_ascii=False)
        print("✅ latest_script.json saved")