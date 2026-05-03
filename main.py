import asyncio
import time
import os
import shutil
import json
from modules.brain import ContentBrain
from modules.image_generator import ImageGenerator
from modules.asset_manager import AssetManager
from modules.audio import AudioEngine
from modules.composer import Composer
from modules.thumbnail import ThumbnailGenerator
from modules.uploader import YouTubeUploader

CHANNEL_NAME = os.getenv("CHANNEL_NAME", "@MovieStoryteller")


def clean_cache():
    print("🧹 Cleaning temp files...")
    for folder in [
        os.path.join(os.getcwd(), "assets", "audio_clips"),
        os.path.join(os.getcwd(), "assets", "temp"),
        os.path.join(os.getcwd(), "assets", "scene_images"),
        os.path.join(os.getcwd(), "assets", "video_clips"),
    ]:
        if not os.path.exists(folder):
            continue
        for f in os.listdir(folder):
            fp = os.path.join(folder, f)
            try:
                os.unlink(fp) if os.path.isfile(fp) else shutil.rmtree(fp)
            except Exception:
                pass
    print("✅ Cache cleared")


async def create_one_short(short_number):
    # ── 1. BRAIN ─────────────────────────────────────────────────────
    brain = ContentBrain()
    try:
        script_data = brain.generate_script()
        if not script_data:
            print("❌ Script generation failed")
            return False
    except Exception as e:
        print(f"❌ Brain Error: {e}")
        return False

    scene       = script_data[0]
    movie_name  = scene.get("movie", "Movie")
    part_number = scene.get("part_number", 1)
    total_parts = scene.get("total_parts", 100)
    scene_title = scene.get("scene_title", "")
    print(f"\n🎬 {movie_name} — Part {part_number}/{total_parts} | {scene_title}")

    # ── 2. AUDIO ─────────────────────────────────────────────────────
    audio_engine = AudioEngine()
    try:
        script_data = await audio_engine.process_script(script_data)
    except Exception as e:
        print(f"❌ Audio Error: {e}")
        return False

    # Persist voice_slot assignments back into brain state
    # so same character keeps same voice in future parts
    try:
        updated_profiles = script_data[0].get("character_profiles", {})
        if updated_profiles:
            brain.state.setdefault("character_profiles", {})
            for cname, cdata in updated_profiles.items():
                if cname in brain.state["character_profiles"]:
                    brain.state["character_profiles"][cname]["voice_slot"] = \
                        cdata.get("voice_slot", brain.state["character_profiles"][cname].get("voice_slot"))
            brain._save_state()
    except Exception:
        pass

    # ── 3. AI IMAGES (6-8 per scene) ─────────────────────────────────
    image_gen        = ImageGenerator()
    image_paths_list = []
    for s in script_data:
        paths = image_gen.get_images_for_scene(s)
        image_paths_list.append(paths)

    # ── 4. PEXELS MOOD CLIPS (2 per scene) ───────────────────────────
    asset_manager   = AssetManager()
    mood_clips_list = []
    for s in script_data:
        clips = asset_manager.get_mood_clips(s)
        mood_clips_list.append(clips)

    # ── 5. COMPOSE ───────────────────────────────────────────────────
    composer = Composer()

    # Generate intro frame (same design as thumbnail)
    # Use first AI image as background if available
    first_img = (image_paths_list[0][0]
                 if image_paths_list and image_paths_list[0] else None)
    thumb_gen_early = ThumbnailGenerator()
    intro_frame = thumb_gen_early.generate_intro_frame(
        movie_name    = movie_name,
        part_number   = part_number,
        total_parts   = total_parts,
        channel_name  = CHANNEL_NAME,
        bg_image_path = first_img,
        short_number  = short_number,
        scene_title   = scene_title,
    )

    scene_paths = composer.render_all_scenes(
        script_data, image_paths_list, mood_clips_list,
        intro_frame_path=intro_frame,
    )

    if not scene_paths:
        print("❌ No scenes rendered")
        return False

    final_video = composer.concatenate_with_transitions(
        scene_paths, channel_name=CHANNEL_NAME,
    )
    clean_cache()

    if not final_video:
        print("❌ Final video failed")
        return False

    # ── 6. THUMBNAIL ─────────────────────────────────────────────────
    thumb_gen      = ThumbnailGenerator()
    thumbnail_path = thumb_gen.generate_thumbnail(
        title        = scene.get("title", f"{movie_name} Part {part_number}"),
        script_text  = scene.get("text", ""),
        short_number = short_number,
        image_prompt = (scene.get("image_prompts") or [""])[0],
        movie_name   = movie_name,
        part_number  = part_number,
        total_parts  = total_parts,
        channel_name = CHANNEL_NAME,
        scene_title  = scene_title,
    )

    # ── 7. UPLOAD ─────────────────────────────────────────────────────
    print("📤 Uploading to YouTube...")
    try:
        uploader    = YouTubeUploader()
        title       = f"{movie_name} | Part {part_number} | Hindi Story | {CHANNEL_NAME}"[:100]
        script_text = scene.get("text", "")

        description = f"""🎬 {movie_name} — Part {part_number} of {total_parts}

{script_text[:300]}...

📺 Poori movie series dekhne ke liye channel subscribe karo!
🔔 Bell icon dabao — koi part miss mat karo!

#{movie_name.replace(' ','')} #HindiStory #Part{part_number} #Shorts #MovieSummary #HindiKahani"""

        tags = [
            movie_name, f"Part {part_number}", "hindi movie story",
            "movie summary hindi", "hindi shorts", "movie storyteller",
            "hindi kahani", "shorts", "movie series hindi"
        ]

        video_id = uploader.upload(
            video_path     = "assets/final/final_short.mp4",
            title          = title,
            description    = description,
            thumbnail_path = thumbnail_path,
            tags           = tags,
            privacy        = "public",
        )

        if video_id:
            print(f"✅ UPLOADED: https://youtu.be/{video_id}")
            return True
        else:
            print("❌ Upload failed")
            return False

    except Exception as e:
        print(f"❌ Upload Error: {e}")
        return False


async def main():
    state = {}
    if os.path.exists("story_state.json"):
        with open("story_state.json") as f:
            state = json.load(f)

    print(f"🎬 MOVIE STORYTELLER BOT")
    print(f"📽️  Current: {state.get('current_movie','Starting...')} | Part {state.get('current_part',0)}")
    print(f"🎥 Mode: 7 AI Images + Pexels Mood Clips + Fast Cuts\n")

    short_count = 0
    start_time  = time.time()

    while True:
        short_count += 1
        print(f"\n🔄 === Short #{short_count} ===\n")

        success = await create_one_short(short_number=short_count)

        if success:
            print(f"✅ Short #{short_count} done!")
        else:
            print(f"⚠️  Short #{short_count} had issues. Continuing...")

        print("⏳ Waiting 12 minutes...\n")
        await asyncio.sleep(720)

        if time.time() - start_time > 19800:
            print("⏹️  Max runtime. Stopping.")
            break


if __name__ == "__main__":
    asyncio.run(main())
