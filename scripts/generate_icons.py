import os
import sys
import django
from PIL import Image

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hotel_project.settings')
django.setup()

from django.conf import settings

def generate_icons():
    logo_path = os.path.join(settings.BASE_DIR, 'rental', 'static', 'rental', 'images', 'panesar-logo.png')
    static_images_dir = os.path.join(settings.BASE_DIR, 'rental', 'static', 'rental', 'images')
    
    if not os.path.exists(logo_path):
        print(f"Error: Logo not found at {logo_path}")
        return

    try:
        with Image.open(logo_path) as img:
            # 1. Create favicon.ico (16x16, 32x32, 48x48)
            favicon_path = os.path.join(static_images_dir, 'favicon.ico')
            img.save(favicon_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
            print(f"✓ Created favicon.ico at {favicon_path}")

            # 2. Create apple-touch-icon.png (180x180)
            apple_touch_path = os.path.join(static_images_dir, 'apple-touch-icon.png')
            img_rgba = img.convert("RGBA")
            # Usually apple-touch-icon is square, we'll pad or crop. 
            # For simplicity, we'll resize to square.
            size = max(img_rgba.size)
            new_img = Image.new("RGBA", (size, size), (255, 255, 255, 0))
            new_img.paste(img_rgba, ((size - img_rgba.size[0]) // 2, (size - img_rgba.size[1]) // 2))
            apple_icon = new_img.resize((180, 180), Image.Resampling.LANCZOS)
            apple_icon.save(apple_touch_path, "PNG")
            print(f"✓ Created apple-touch-icon.png at {apple_touch_path}")

    except Exception as e:
        print(f"Error generating icons: {e}")

if __name__ == '__main__':
    generate_icons()
