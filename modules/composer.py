import os
import shutil
import random
import subprocess
import ffmpeg
from PIL import Image, ImageDraw, ImageFont


class Composer:

    def __init__(self):
        self.temp_dir      = os.path.join(os.getcwd(), "assets", "temp")
        self.final_dir     = os.path.join(os.getcwd(), "assets", "final")
        self.bg_music_path = "bgmusic.mp3"
        self.font_path     = self._resolve_font()

        os.makedirs(self.temp_dir,  exist_ok=True)
        os.makedirs(self.final_dir, exist_ok=True)

        if self.font_path:
            print(f"✅ Font: {self.font_path}")
        else:
            print("⚠️  No font — PIL default")

    # ─────────────────────────────────────────────────────────────────
    # FONT
    # ─────────────────────────────────────────────────────────────────

    def _resolve_font(self):
        for p in [
            os.path.join(os.getcwd(), "assets", "fonts", "NotoSans-Bold.ttf"),
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/noto/NotoSansDevanagari-Bold.ttf",
        ]:
            if os.path.exists(p) and os.path.getsize(p) > 10_000:
                return p
        return None

    def _pil_font(self, size):
        if self.font_path:
            try:
                return ImageFont.truetype(self.font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    # ─────────────────────────────────────────────────────────────────
    # UTILITIES
    # ─────────────────────────────────────────────────────────────────

    def get_duration(self, filepath):
        try:
            return float(ffmpeg.probe(filepath)["format"]["duration"])
        except Exception:
            return 0.0

    def _run_cmd(self, cmd, label):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"   ⚠️ {label}:\n{r.stderr[-250:]}")
            return False
        return True

    # ─────────────────────────────────────────────────────────────────
    # INTRO CLIP — 2 seconds, same design as thumbnail
    # ─────────────────────────────────────────────────────────────────

    def _make_intro_clip(self, intro_frame_path, part_num):
        """
        Convert intro still image → 2 second video clip.
        This plays at the very start of every Short.
        """
        out = os.path.join(self.temp_dir, f"intro_{part_num}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", intro_frame_path,
            "-t", "2.0",
            "-vf", "scale=1080:1920,fps=25",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast",
            "-an",
            out,
        ]
        ok = self._run_cmd(cmd, "Intro clip")
        return out if ok else None

    # ─────────────────────────────────────────────────────────────────
    # SUBTITLE — voice-synced SRT
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _srt_ts(seconds):
        seconds  = max(0.0, seconds)
        total_ms = int(round(seconds * 1000))
        ms = total_ms % 1000
        s  = (total_ms // 1000) % 60
        m  = (total_ms // 60000) % 60
        h  = total_ms // 3600000
        return f"{h:02}:{m:02}:{s:02},{ms:03}"

    def _make_synced_srt(self, text, audio_dur, scene_id):
        """
        Build SRT timed to actual voice duration.
        Groups words into short lines (4-5 words), timing proportional to word count.
        SRT offset = +2 seconds because video starts with 2-sec intro.
        """
        words = text.split()
        if not words:
            return None

        # Group into lines of max 5 words
        lines, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= 5:
                lines.append(" ".join(cur))
                cur = []
        if cur:
            lines.append(" ".join(cur))

        if not lines:
            return None

        total_words  = len(words)
        srt_path     = os.path.join(self.temp_dir, f"sub_{scene_id}.srt")
        current_time = 2.0   # ← offset for 2-sec intro at start

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, line in enumerate(lines):
                lw       = len(line.split())
                line_dur = max((lw / total_words) * audio_dur, 0.8)
                start    = current_time
                end      = current_time + line_dur - 0.05
                f.write(f"{i+1}\n{self._srt_ts(start)} --> {self._srt_ts(end)}\n{line}\n\n")
                current_time += line_dur

        return srt_path

    def _burn_subtitles(self, src, srt_path, dst):
        if not self.font_path:
            shutil.copy2(src, dst)
            return False

        safe_srt  = srt_path.replace("\\", "/")
        safe_font = self.font_path.replace("\\", "/")
        if len(safe_srt) >= 2 and safe_srt[1] == ":":
            safe_srt = safe_srt[0] + "\\:" + safe_srt[2:]

        style = (
            f"fontfile={safe_font},"
            "FontSize=22,"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H80000000,"
            "Bold=1,"
            "Outline=3,"
            "Shadow=1,"
            "Alignment=2,"
            "MarginV=120,"
            "MarginL=40,"
            "MarginR=40"
        )
        cmd = [
            "ffmpeg", "-y", "-i", src,
            "-vf", f"subtitles='{safe_srt}':force_style='{style}'",
            "-c:v", "libx264", "-c:a", "copy",
            "-pix_fmt", "yuv420p", "-preset", "fast", dst,
        ]
        ok = self._run_cmd(cmd, "Subtitles")
        if not ok:
            shutil.copy2(src, dst)
        return ok

    # ─────────────────────────────────────────────────────────────────
    # PIL BADGE — top bar on each image
    # ─────────────────────────────────────────────────────────────────

    def _burn_badge_on_image(self, img_path, out_path, top_text, part_num, total_parts):
        """
        Burn top badge onto image:
        - Dark bar at top with movie name
        - Small yellow PART XX box in top-right corner
        """
        img  = Image.open(img_path).convert("RGB")
        W, H = img.size
        draw = ImageDraw.Draw(img, "RGBA")

        # Dark top bar
        draw.rectangle([(0,0),(W,82)], fill=(0,0,0,215))

        # Movie/series name on left
        mf   = self._pil_font(26)
        mb   = draw.textbbox((0,0), top_text, font=mf)
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((20+dx, 24+dy), top_text, font=mf, fill=(0,0,0,255))
        draw.text((20, 24), top_text, font=mf, fill=(255,255,255,255))

        # Yellow PART box — top right
        part_str = f"PART {part_num}"
        pf       = self._pil_font(22)
        pb       = draw.textbbox((0,0), part_str, font=pf)
        pw, ph   = pb[2]-pb[0], pb[3]-pb[1]
        bx       = W - pw - 36
        by       = 16
        # Yellow box
        draw.rounded_rectangle(
            [bx-10, by-6, bx+pw+10, by+ph+6],
            radius=8,
            fill=(255, 210, 0, 255)
        )
        # Dark text on yellow
        draw.text((bx, by), part_str, font=pf, fill=(20,20,20))

        img.save(out_path, "JPEG", quality=92)
        return out_path

    # ─────────────────────────────────────────────────────────────────
    # IMAGE → VIDEO KEN BURNS
    # ─────────────────────────────────────────────────────────────────

    def _image_to_video_kenburns(self, img_path, duration, out_path, zoom_dir="in"):
        fps    = 25
        frames = int(duration * fps)
        z_expr = "min(zoom+0.0003,1.08)" if zoom_dir == "in" else "max(zoom-0.0003,1.0)"
        vf = (
            f"scale=1200:2133,"
            f"zoompan=z='{z_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s=1080x1920:fps={fps},"
            f"setpts=PTS-STARTPTS,fps={fps}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_path,
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "fast", out_path,
        ]
        return self._run_cmd(cmd, "KenBurns")

    def _clip_to_portrait(self, clip_path, duration, out_path):
        cmd = [
            "ffmpeg", "-y", "-i", clip_path,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=25",
            "-t", str(duration), "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "fast", out_path,
        ]
        return self._run_cmd(cmd, "Clip→Portrait")

    # ─────────────────────────────────────────────────────────────────
    # BUILD VISUAL SEQUENCE
    # ─────────────────────────────────────────────────────────────────

    def _build_visual_sequence(self, image_paths, mood_clips,
                                total_dur, part_num, movie_name, total_parts):
        short_movie = movie_name[:22]

        # Interleave images + mood clips
        all_visuals = []
        mood_idx    = 0
        for i, img in enumerate(image_paths):
            all_visuals.append(("image", img))
            if (i+1) % 3 == 0 and mood_idx < len(mood_clips):
                all_visuals.append(("clip", mood_clips[mood_idx]))
                mood_idx += 1

        n            = max(len(all_visuals), 1)
        dur_per_slot = max(3.5, min(total_dur / n, 8.0))
        segments     = []

        for idx, (vtype, vpath) in enumerate(all_visuals):
            seg = os.path.join(self.temp_dir, f"seg_{part_num}_{idx+1}.mp4")

            if vtype == "image":
                overlay = os.path.join(self.temp_dir, f"ov_{part_num}_{idx+1}.jpg")
                self._burn_badge_on_image(
                    vpath, overlay, short_movie, part_num, total_parts
                )
                ok = self._image_to_video_kenburns(
                    overlay, dur_per_slot, seg,
                    zoom_dir="in" if idx % 2 == 0 else "out"
                )
            else:
                ok = self._clip_to_portrait(vpath, dur_per_slot, seg)

            if ok and os.path.exists(seg):
                segments.append(seg)

        if not segments:
            return None

        if len(segments) == 1:
            return segments[0]

        # Simple concat
        list_file = os.path.join(self.temp_dir, f"list_{part_num}.txt")
        with open(list_file, "w") as f:
            for p in segments:
                f.write(f"file '{p}'\n")
        out = os.path.join(self.temp_dir, f"visual_{part_num}.mp4")
        ok  = self._run_cmd([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file,
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-preset", "fast", out,
        ], "Concat")
        return out if ok else segments[0]

    # ─────────────────────────────────────────────────────────────────
    # PROCESS SCENE
    # ─────────────────────────────────────────────────────────────────

    def process_scene(self, scene, image_paths, mood_clips,
                      intro_frame_path=None, is_first=False):
        part_num    = scene.get("part_number", 1)
        total_parts = scene.get("total_parts", 100)
        movie_name  = scene.get("movie", "Movie")
        audio_path  = scene.get("audio_path")
        total_dur   = scene.get("duration", 0)
        script_text = scene.get("text", "")

        if not audio_path or not os.path.exists(audio_path):
            print(f"   ⚠️ Audio missing Part {part_num}")
            return None
        if not image_paths:
            print(f"   ⚠️ No images Part {part_num}")
            return None

        nosub_path  = os.path.join(self.temp_dir, f"nosub_{part_num}.mp4")
        subbed_path = os.path.join(self.temp_dir, f"subbed_{part_num}.mp4")
        final_path  = os.path.join(self.temp_dir, f"scene_{part_num}.mp4")

        # ── Step 1: Build visual (images + clips) ────────────────────
        visual = self._build_visual_sequence(
            image_paths, mood_clips, total_dur,
            part_num, movie_name, total_parts
        )
        if not visual:
            print(f"   ❌ Visual failed Part {part_num}")
            return None

        # ── Step 2: Prepend 2-sec intro clip ─────────────────────────
        if intro_frame_path and os.path.exists(intro_frame_path):
            intro_clip = self._make_intro_clip(intro_frame_path, part_num)
            if intro_clip:
                combined_list = os.path.join(
                    self.temp_dir, f"combined_list_{part_num}.txt"
                )
                combined_vid  = os.path.join(
                    self.temp_dir, f"combined_{part_num}.mp4"
                )
                with open(combined_list, "w") as f:
                    f.write(f"file '{intro_clip}'\n")
                    f.write(f"file '{visual}'\n")
                ok = self._run_cmd([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", combined_list,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-preset", "fast", combined_vid,
                ], "Prepend intro")
                if ok:
                    visual = combined_vid

        # ── Step 3: Mix audio (voice + bg music) ─────────────────────
        try:
            voice = ffmpeg.input(audio_path)
            vis   = ffmpeg.input(visual)

            if os.path.exists(self.bg_music_path):
                bg = (
                    ffmpeg.input(self.bg_music_path, stream_loop=-1)
                    .filter("volume", 0.10)
                    .filter("atrim", duration=total_dur + 3)
                )
                audio_out = ffmpeg.filter(
                    [voice, bg], "amix", inputs=2, duration="first"
                )
            else:
                audio_out = voice

            (
                ffmpeg.output(
                    vis.video, audio_out, nosub_path,
                    vcodec="libx264", acodec="aac",
                    pix_fmt="yuv420p", preset="medium",
                    movflags="faststart",
                    **{"avoid_negative_ts": "make_zero", "shortest": None}
                ).run(overwrite_output=True, quiet=True)
            )
        except Exception as e:
            print(f"   ❌ Audio mix failed: {e}")
            return None

        # ── Step 4: Synced subtitles (offset +2s for intro) ──────────
        actual_dur = self.get_duration(nosub_path)
        srt = self._make_synced_srt(script_text, actual_dur - 2.0, part_num)
        if srt:
            ok = self._burn_subtitles(nosub_path, srt, subbed_path)
            current = subbed_path if ok else nosub_path
        else:
            current = nosub_path

        if current != final_path:
            shutil.copy2(current, final_path)

        print(f"   ✅ Part {part_num} done ({total_dur:.1f}s + 2s intro)")
        return final_path

    # ─────────────────────────────────────────────────────────────────
    # RENDER ALL
    # ─────────────────────────────────────────────────────────────────

    def render_all_scenes(self, script_data, image_paths_list,
                           mood_clips_list, intro_frame_path=None):
        rendered = []
        for i, scene in enumerate(script_data):
            imgs  = image_paths_list[i] if i < len(image_paths_list) else []
            moods = mood_clips_list[i]  if i < len(mood_clips_list)  else []
            path  = self.process_scene(
                scene, imgs, moods,
                intro_frame_path=intro_frame_path,
                is_first=(i == 0)
            )
            if path:
                rendered.append(path)
        return rendered

    # ─────────────────────────────────────────────────────────────────
    # FINAL OUTPUT
    # ─────────────────────────────────────────────────────────────────

    def concatenate_with_transitions(
        self, video_paths,
        output_filename="final_short.mp4",
        channel_name="@MovieStoryteller",
    ):
        print("🎬 Finalizing...")
        output_path = os.path.join(self.final_dir, output_filename)
        if os.path.exists(output_path):
            try: os.remove(output_path)
            except Exception: pass

        if not video_paths:
            return None

        if len(video_paths) == 1:
            shutil.copy2(video_paths[0], output_path)
            print(f"✅ FINAL: {output_path}")
            return output_path

        inp         = ffmpeg.input(video_paths[0])
        v_stream    = inp.video
        a_stream    = inp.audio
        current_dur = self.get_duration(video_paths[0])

        for i in range(1, len(video_paths)):
            nxt      = ffmpeg.input(video_paths[i])
            next_dur = self.get_duration(video_paths[i])
            trans    = 0.5
            offset   = max(current_dur - trans, 0.1)
            v_stream = ffmpeg.filter(
                [v_stream, nxt.video], "xfade",
                transition="fade", duration=trans, offset=offset,
            )
            a_stream = ffmpeg.filter(
                [a_stream, nxt.audio], "acrossfade", d=trans,
            )
            current_dur += next_dur - trans

        try:
            (
                ffmpeg.output(
                    v_stream, a_stream, output_path,
                    vcodec="libx264", acodec="aac",
                    pix_fmt="yuv420p", preset="medium",
                    movflags="faststart",
                ).run(overwrite_output=True, quiet=False)
            )
        except Exception as e:
            print(f"❌ Final stitch error: {e}")
            return None

        print(f"✅ FINAL: {output_path}")
        return output_path
