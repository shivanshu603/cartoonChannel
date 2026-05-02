import os
import time
import requests
import urllib.parse
from PIL import Image
from io import BytesIO


class ImageGenerator:
    """
    Generates 6-8 AI images per scene via Pollinations.ai (free).
    Each image represents a different moment/shot in the scene.
    """

    def __init__(self):
        self.output_dir = os.path.join(os.getcwd(), "assets", "scene_images")
        os.makedirs(self.output_dir, exist_ok=True)
        self.base_url   = "https://image.pollinations.ai/prompt/"

    def generate_image(self, prompt, filename, width=1080, height=1920, retries=3):
        output_path = os.path.join(self.output_dir, filename)

        if os.path.exists(output_path) and os.path.getsize(output_path) > 5000:
            print(f"      📦 Cached: {filename}")
            return output_path

        enhanced = (
            f"{prompt}, "
            "cinematic lighting, ultra detailed, dramatic composition, "
            "movie scene, 8k quality, professional photography, "
            "Disney Pixar 3D animated style, soft warm golden lighting, "
            "big expressive eyes, smooth textures, Pixar movie render quality, ultra detailed, 8k"
        )

        encoded = urllib.parse.quote(enhanced)

        url = (
            f"{self.base_url}{encoded}"
            f"?width={width}&height={height}&nologo=true&enhance=true"
        )

        for attempt in range(retries):
            try:
                print(f"      🎨 [{filename}] attempt {attempt+1}")
                resp = requests.get(url, timeout=90)

                if resp.status_code == 200 and len(resp.content) > 5000:
                    img = Image.open(BytesIO(resp.content)).convert("RGB")

                    if img.size != (width, height):
                        img = img.resize((width, height), Image.LANCZOS)

                    img.save(output_path, "JPEG", quality=92)

                    print(f"      ✅ Saved ({os.path.getsize(output_path)//1024} KB): {filename}")
                    return output_path
                else:
                    print(f"      ⚠️ Bad response {resp.status_code}")
                    time.sleep(4)

            except Exception as e:
                print(f"      ⚠️ Attempt {attempt+1} error: {e}")
                time.sleep(4)

        print(f"      ❌ Failed: {filename}")
        return None

    def get_images_for_scene(self, scene):
        """
        Generate 6-8 images for a scene.
        Uses image_prompts list from brain.py (6-8 different shots).
        Returns list of local file paths.
        """
        part_num     = scene.get("part_number", 1)
        image_prompts = scene.get("image_prompts", [])

        # Fallback to old single prompts if list not present
        if not image_prompts:
            p1 = scene.get("image_prompt_1", "")
            p2 = scene.get("image_prompt_2", "")
            if p1:
                image_prompts = [p1, p2] if p2 else [p1]

        if not image_prompts:
            print(f"   ⚠️ No image prompts for Part {part_num}")
            return []

        print(f"   🖼️  Generating {len(image_prompts)} images for Part {part_num}...")

        paths = []
        for i, prompt in enumerate(image_prompts):
            filename = f"part_{part_num}_shot_{i+1}.jpg"
            path     = self.generate_image(prompt, filename)
            if path:
                paths.append(path)
            time.sleep(2)  # Rate limit buffer

        print(f"   ✅ {len(paths)}/{len(image_prompts)} images ready for Part {part_num}")
        return paths
