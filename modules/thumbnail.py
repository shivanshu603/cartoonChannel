import os
import re
import requests
import urllib.parse
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from io import BytesIO

W, H = 1080, 1920


class ThumbnailGenerator:

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "thumbnails")
        self.fonts_dir  = os.path.join(os.getcwd(), "assets", "fonts")
        os.makedirs(self.output_dir, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────
    # FONT
    # ─────────────────────────────────────────────────────────────────

    def _font(self, size):
        candidates = [
            os.path.join(self.fonts_dir, "NotoSans-Bold.ttf"),
            "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
            "/usr/share/fonts/noto/NotoSansDevanagari-Bold.ttf",
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, size)
                except Exception:
                    continue
        return ImageFont.load_default()

    # ─────────────────────────────────────────────────────────────────
    # BACKGROUND
    # ─────────────────────────────────────────────────────────────────

    def _get_ai_bg(self, prompt):
        """Fetch AI image from Pollinations for background."""
        try:
            enhanced = f"{prompt}, Disney Pixar 3D animated style, dramatic lighting, movie poster"
            url = (
                f"https://image.pollinations.ai/prompt/"
                f"{urllib.parse.quote(enhanced)}"
                f"?width={W}&height={H}&nologo=true&model=flux"
            )
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 5000:
                return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            print(f"   ⚠️ AI bg failed: {e}")
        return None

    def _make_dark_bg(self, bg_image_path=None, ai_prompt=None):
        """
        Create darkened background:
        1. Try provided local image first (fastest)
        2. Try AI generation from prompt
        3. Fallback to dark gradient
        """
        img = None

        # Option 1: Use local image
        if bg_image_path and os.path.exists(bg_image_path):
            try:
                img = Image.open(bg_image_path).convert("RGB")
            except Exception:
                pass

        # Option 2: AI generated
        if img is None and ai_prompt:
            img = self._get_ai_bg(ai_prompt)

        if img:
            # Resize + crop to portrait
            ratio = img.width / img.height
            if ratio > W / H:
                nw, nh = int(H * ratio), H
            else:
                nw, nh = W, int(W / ratio)
            img = img.resize((nw, nh), Image.LANCZOS)
            l   = (nw - W) // 2
            t   = (nh - H) // 2
            img = img.crop((l, t, l + W, t + H))
            # Darken so text is always readable
            img = ImageEnhance.Brightness(img).enhance(0.45)
            img = img.filter(ImageFilter.GaussianBlur(1))
            return img

        # Option 3: Dark gradient fallback
        img  = Image.new("RGB", (W, H))
        draw = ImageDraw.Draw(img)
        for y in range(H):
            r = int(10 + (y / H) * 20)
            b = int(40 + (y / H) * 80)
            draw.line([(0, y), (W, y)], fill=(r, 0, b))
        return img

    # ─────────────────────────────────────────────────────────────────
    # TEXT HELPER
    # ─────────────────────────────────────────────────────────────────

    def _draw_outlined(self, draw, text, font, x, y,
                       fill=(255, 255, 255), outline=(0, 0, 0), ow=5):
        for dx in range(-ow, ow + 1):
            for dy in range(-ow, ow + 1):
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
        draw.text((x, y), text, font=font, fill=fill)

    def _centered_text(self, draw, text, font, y, fill=(255,255,255), outline=(0,0,0), ow=5):
        bb = draw.textbbox((0, 0), text, font=font)
        x  = (W - (bb[2] - bb[0])) // 2
        self._draw_outlined(draw, text, font, x, y, fill, outline, ow)
        return bb[3] - bb[1]  # return height

    # ─────────────────────────────────────────────────────────────────
    # MAIN CARD DESIGN
    # ─────────────────────────────────────────────────────────────────

    def _build_card(self, bg, movie_name, part_number, total_parts, channel_name, scene_title=""):
        """
        Card layout:
        ┌────────────────────────────────────┐
        │  🎬  STORY NAME  (top bar)         │
        │  [scene_title if provided]         │
        │                                    │
        │         [background image]         │
        │                                    │
        │   ┌──────────────────────────┐     │
        │   │    PART  30  / 100       │ ← YELLOW BOX (big)
        │   └──────────────────────────┘     │
        │                                    │
        │       STORY NAME (mid overlay)     │
        │                                    │
        │  @ChannelName  (bottom bar)        │
        └────────────────────────────────────┘
        """
        img  = bg.copy()
        draw = ImageDraw.Draw(img, "RGBA")

        # ── Dark gradient overlays ────────────────────────────────────
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for y in range(H):
            if y < 320:
                alpha = int(210 * (1 - y / 320))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
            elif y > H - 420:
                alpha = int(210 * ((y - (H - 420)) / 420))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
        od.rectangle([(0, 320), (W, H - 300)], fill=(0, 0, 0, 110))
        img  = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")

        # ── TOP BAR: Story name (2 lines if long) ────────────────────
        bar_h = 130
        draw.rectangle([(0, 0), (W, bar_h)], fill=(0, 0, 0, 235))

        # Split movie name into 2 lines if > 22 chars
        words = movie_name.split()
        if len(movie_name) <= 22 or len(words) <= 2:
            name_lines = [movie_name]
        else:
            mid = len(words) // 2
            name_lines = [" ".join(words[:mid]), " ".join(words[mid:])]

        nf       = self._font(32 if len(name_lines) == 1 else 28)
        line_h   = 36
        total_th = len(name_lines) * line_h
        start_y  = (bar_h - total_th) // 2 + 4

        for li, nl in enumerate(name_lines):
            disp = f"🎬  {nl}" if li == 0 else f"    {nl}"
            nb   = draw.textbbox((0, 0), disp, font=nf)
            nx   = (W - (nb[2] - nb[0])) // 2
            ny   = start_y + li * line_h
            for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
                draw.text((nx+dx, ny+dy), disp, font=nf, fill=(0,0,0,255))
            draw.text((nx, ny), disp, font=nf, fill=(255, 255, 255, 255))

        # ── SCENE TITLE below top bar (if provided) ──────────────────
        if scene_title:
            sf  = self._font(26)
            sb  = draw.textbbox((0, 0), scene_title, font=sf)
            sx  = (W - (sb[2] - sb[0])) // 2
            sy  = bar_h + 18
            for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
                draw.text((sx+dx, sy+dy), scene_title, font=sf, fill=(0,0,0,200))
            draw.text((sx, sy), scene_title, font=sf, fill=(255, 220, 80, 255))

        # ── CENTRE: PART XX / TOTAL in YELLOW BOX ────────────────────
        part_str  = f"PART  {part_number}"
        of_str    = f"of {total_parts}"

        pf  = self._font(110)
        pb  = draw.textbbox((0, 0), part_str, font=pf)
        pw  = pb[2] - pb[0]
        ph  = pb[3] - pb[1]

        pad_x, pad_y = 55, 30
        box_w = pw + pad_x * 2
        box_h = ph + pad_y * 2 + 44   # extra room for "of N" inside box
        box_x = (W - box_w) // 2
        box_y = (H - box_h) // 2 - 60

        # Shadow
        draw.rounded_rectangle(
            [box_x+8, box_y+10, box_x+box_w+8, box_y+box_h+10],
            radius=28, fill=(0, 0, 0, 130)
        )
        # Yellow box
        draw.rounded_rectangle(
            [box_x, box_y, box_x+box_w, box_y+box_h],
            radius=28, fill=(255, 210, 0, 255)
        )

        # "PART XX" text
        tx = box_x + pad_x
        ty = box_y + pad_y
        for dx, dy in [(-3,0),(3,0),(0,-3),(0,3)]:
            draw.text((tx+dx, ty+dy), part_str, font=pf, fill=(80, 60, 0, 180))
        draw.text((tx, ty), part_str, font=pf, fill=(20, 15, 0, 255))

        # "of N" inside box, below PART number
        of_f = self._font(38)
        of_b = draw.textbbox((0, 0), of_str, font=of_f)
        of_x = (W - (of_b[2] - of_b[0])) // 2
        of_y = ty + ph + 6
        draw.text((of_x, of_y), of_str, font=of_f, fill=(80, 60, 0, 220))

        # ── STORY NAME BELOW BOX (white, readable) ───────────────────
        short_name = movie_name if len(movie_name) <= 28 else movie_name[:26] + "…"
        snf = self._font(30)
        snb = draw.textbbox((0, 0), short_name, font=snf)
        snx = (W - (snb[2] - snb[0])) // 2
        sny = box_y + box_h + 28
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2)]:
            draw.text((snx+dx, sny+dy), short_name, font=snf, fill=(0,0,0,200))
        draw.text((snx, sny), short_name, font=snf, fill=(255, 255, 255, 240))

        # ── BOTTOM BAR: Channel name ──────────────────────────────────
        if channel_name:
            bot_h = 90
            draw.rectangle([(0, H - bot_h), (W, H)], fill=(0, 0, 0, 235))
            cf  = self._font(38)
            cb  = draw.textbbox((0, 0), channel_name, font=cf)
            cx  = (W - (cb[2] - cb[0])) // 2
            cy  = H - bot_h + (bot_h - (cb[3] - cb[1])) // 2
            draw.text((cx, cy), channel_name, font=cf, fill=(200, 200, 200, 255))

        return img

    # ─────────────────────────────────────────────────────────────────
    # THUMBNAIL
    # ─────────────────────────────────────────────────────────────────

    def generate_thumbnail(
        self, title="", script_text="", short_number=1,
        image_prompt=None, movie_name="Movie", part_number=1,
        total_parts=100, channel_name="@MovieStoryteller",
        bg_image_path=None, scene_title="",
    ):
        print(f"🖼️  Thumbnail: {movie_name} Part {part_number}...")

        bg  = self._make_dark_bg(bg_image_path, image_prompt)
        img = self._build_card(bg, movie_name, part_number, total_parts, channel_name, scene_title)

        out = os.path.join(self.output_dir, f"thumbnail_{short_number}.png")
        img.save(out, "PNG", optimize=True)
        print(f"✅ Thumbnail saved → thumbnail_{short_number}.png")
        return out

    def generate_intro_frame(
        self, movie_name="Movie", part_number=1, total_parts=100,
        channel_name="@MovieStoryteller", bg_image_path=None,
        short_number=1, scene_title="",
    ):
        print(f"🎬 Intro frame: {movie_name} Part {part_number}...")

        bg  = self._make_dark_bg(bg_image_path, ai_prompt=None)
        img = self._build_card(bg, movie_name, part_number, total_parts, channel_name, scene_title)

        out = os.path.join(self.output_dir, f"intro_frame_{short_number}.png")
        img.save(out, "PNG", optimize=True)
        print(f"✅ Intro frame saved → intro_frame_{short_number}.png")
        return out