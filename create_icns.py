#!/usr/bin/env python3
import os
import subprocess
import tempfile
import shutil
from PIL import Image
from cairosvg import svg2png

def create_icns_from_svg(svg_path, output_icns_path):
    """
    Convert SVG to ICNS file for macOS app icon
    """
    # Create a temporary directory
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Create iconset directory
        iconset_dir = os.path.join(tmp_dir, "app.iconset")
        os.makedirs(iconset_dir, exist_ok=True)
        
        # Define sizes for macOS icon set
        icon_sizes = [16, 32, 64, 128, 256, 512, 1024]
        
        # Generate PNG files at different sizes
        for size in icon_sizes:
            # Regular size
            png_path = os.path.join(iconset_dir, f"icon_{size}x{size}.png")
            svg2png(url=svg_path, write_to=png_path, output_width=size, output_height=size)
            
            # 2x (Retina) size - except for 1024 which doesn't have a 2x variant
            if size < 512:
                png_path_2x = os.path.join(iconset_dir, f"icon_{size}x{size}@2x.png")
                svg2png(url=svg_path, write_to=png_path_2x, output_width=size*2, output_height=size*2)
        
        # Use iconutil to create ICNS file (macOS only)
        subprocess.run(["iconutil", "-c", "icns", iconset_dir, "-o", output_icns_path], check=True)
        
        print(f"Successfully created {output_icns_path}")

if __name__ == "__main__":
    # Get paths
    svg_path = os.path.join("icons", "app", "app_icon.svg")
    output_dir = os.path.join("icons", "app")
    icns_path = os.path.join(output_dir, "app_icon.icns")
    
    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)
    
    # Create ICNS file
    create_icns_from_svg(svg_path, icns_path)