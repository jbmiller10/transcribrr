"""
Script to convert SVG icon to ICO file for Windows installer.
"""

import os
import sys
from PIL import Image
import cairosvg
from io import BytesIO
import tempfile

def svg_to_ico(svg_path, output_path, sizes=[16, 24, 32, 48, 64, 128, 256]):
    """
    Convert SVG to ICO file with multiple sizes.
    
    Args:
        svg_path: Path to the SVG file
        output_path: Path to save the ICO file
        sizes: List of icon sizes to include
    """
    print(f"Converting {svg_path} to {output_path}")
    
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmpdirname:
        # Create temporary PNG files for each size
        png_files = []
        for size in sizes:
            png_path = os.path.join(tmpdirname, f"icon_{size}.png")
            
            # Use cairosvg to convert SVG to PNG
            cairosvg.svg2png(url=svg_path, write_to=png_path, output_width=size, output_height=size)
            png_files.append((png_path, size))
            
        # Create ICO file
        images = []
        for png_path, size in png_files:
            img = Image.open(png_path)
            # Ensure image is correct size and has transparency
            img = img.resize((size, size), Image.LANCZOS)
            images.append(img)
        
        # Save as ICO
        images[0].save(
            output_path,
            format='ICO',
            sizes=[(img.width, img.height) for img in images],
            append_images=images[1:]
        )
        
        print(f"ICO file created successfully at {output_path}")

if __name__ == "__main__":
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    svg_path = os.path.join(script_dir, "icons", "app", "app_icon.svg")
    ico_path = os.path.join(script_dir, "icons", "app", "app_icon.ico")
    
    # Convert
    svg_to_ico(svg_path, ico_path)