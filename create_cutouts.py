"""
Run this ONCE on your laptop to create perfect transparent bottle cutouts.
Requires: pip install rembg Pillow

Usage: python create_cutouts.py

This will create:
  static/photos/bottle-cutout-sb-pro.png  (Small Batch - Black Label)
  static/photos/bottle-cutout-sgl-pro.png (Single Barrel - Gold Label)

Then commit those PNGs to the repo. The app will use them automatically.
"""

import os
import sys

try:
    from rembg import remove
    from PIL import Image
except ImportError:
    print("Install dependencies first:")
    print("  pip install rembg Pillow")
    sys.exit(1)

# Source photos (light background originals)
BOTTLES = {
    'sb': {
        'name': 'Small Batch (Black Label)',
        'sources': [
            'static/photos/gallery/Black_Front_LightBG_V1.png',
        ],
        'output': 'static/photos/bottle-cutout-sb-pro.png',
    },
    'sgl': {
        'name': 'Single Barrel (Gold Label)',
        'sources': [
            'static/photos/gallery/Golden_Front_57_LightBG_V1.png',
            'static/photos/gallery/Golden_Front_58_LightBG_V1.png',
        ],
        'output': 'static/photos/bottle-cutout-sgl-pro.png',
    },
}

def create_cutout(source_path, output_path, name):
    print(f"\n{'='*50}")
    print(f"Processing: {name}")
    print(f"Source: {source_path}")
    
    if not os.path.exists(source_path):
        print(f"  ERROR: Source not found: {source_path}")
        return False
    
    img = Image.open(source_path).convert('RGBA')
    print(f"  Original size: {img.size}")
    
    # rembg AI background removal
    print(f"  Running rembg (this takes 10-20 seconds first time)...")
    cutout = remove(img)
    
    # Trim transparent edges
    bbox = cutout.getbbox()
    if bbox:
        cutout = cutout.crop(bbox)
        print(f"  Trimmed to: {cutout.size}")
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cutout.save(output_path)
    print(f"  Saved: {output_path}")
    print(f"  File size: {os.path.getsize(output_path) / 1024:.0f} KB")
    return True


def main():
    print("Forbidden Bourbon — Professional Cutout Generator")
    print("=" * 50)
    
    success_count = 0
    for key, config in BOTTLES.items():
        # Try each source until one works
        done = False
        for src in config['sources']:
            if os.path.exists(src):
                if create_cutout(src, config['output'], config['name']):
                    success_count += 1
                    done = True
                break
        if not done:
            print(f"\n  SKIPPED {config['name']}: No source photo found")
            print(f"  Looked for: {config['sources']}")
    
    print(f"\n{'='*50}")
    print(f"Done! Created {success_count} cutout(s)")
    if success_count > 0:
        print(f"\nNext steps:")
        print(f"  git add static/photos/bottle-cutout-*-pro.png")
        print(f"  git commit -m 'Add professional bottle cutouts'")
        print(f"  git push")


if __name__ == '__main__':
    main()
