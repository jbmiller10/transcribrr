"""
Script to convert SVG icon to ICO file for Windows installer.
"""

import os
from PIL import Image
import cairosvg
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
            
        # Load the generated PNG files and keep them paired with their size
        images = []  # type: list[tuple[int, Image.Image]]
        for png_path, size in png_files:
            img = Image.open(png_path).convert("RGBA")
            # Ensure the image is exactly the desired size
            if img.size != (size, size):
                img = img.resize((size, size), Image.LANCZOS)
            images.append((size, img))

        # Sort images by descending size so that the *largest* image is written first.
        # Some tools (including Inno Setup) expect the first image in the ICO file to
        # be 256×256 or 128×128.  If the first image is only 16×16 the resource
        # section can be considered malformed and the compiler will abort with
        # “Icon file is invalid”.
        images.sort(key=lambda t: t[0], reverse=True)

        # Pillow wants the list of sizes separately and the list of supplementary
        # images (excluding the first one).
        # For the ICO format Pillow will automatically resample the *first* image
        # to all sizes provided via the `sizes` argument.  Supplying additional
        # images through `append_images` does not work for ICO files and leads to
        # corrupted output.  Therefore we write the largest (first) image only and
        # let Pillow derive the other resolutions.

        largest_img = images[0][1]  # images are sorted desc by size
        size_list = [(size, size) for size, _ in images]

        largest_img.save(
            output_path,
            format="ICO",
            sizes=size_list,
        )
        
        print(f"ICO file created successfully at {output_path}")

if __name__ == "__main__":
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    svg_path = os.path.join(script_dir, "icons", "app", "app_icon.svg")
    ico_path = os.path.join(script_dir, "icons", "app", "app_icon.ico")
    
    # Convert
    svg_to_ico(svg_path, ico_path)