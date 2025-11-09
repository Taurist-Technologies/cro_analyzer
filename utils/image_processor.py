"""
Image processing utilities for CRO Analyzer.

This module contains functions for resizing and compressing screenshots
to comply with Claude's API limits.
"""

import base64
from PIL import Image
import io


def resize_screenshot_if_needed(
    screenshot_bytes: bytes, max_dimension: int = 7500, max_file_size: int = 5_242_880
) -> str:
    """
    Resize and compress screenshot to comply with Claude's limits:
    - 8000px maximum dimension
    - 5 MB maximum file size

    Uses JPEG compression with quality reduction until under max_file_size.
    Returns base64 encoded string of the processed image.

    Args:
        screenshot_bytes: Original screenshot bytes
        max_dimension: Maximum width/height in pixels (default 7500)
        max_file_size: Maximum file size in bytes (default 5MB = 5,242,880 bytes)

    Returns:
        Base64-encoded string of the processed image
    """
    # Open image from bytes
    image = Image.open(io.BytesIO(screenshot_bytes))
    width, height = image.size

    # Step 1: Resize dimensions if needed
    if width > max_dimension or height > max_dimension:
        # Calculate new dimensions maintaining aspect ratio
        if width > height:
            new_width = max_dimension
            new_height = int(height * (max_dimension / width))
        else:
            new_height = max_dimension
            new_width = int(width * (max_dimension / height))

        # Resize image
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Convert RGBA to RGB if necessary (JPEG doesn't support transparency)
    if image.mode == "RGBA":
        rgb_image = Image.new("RGB", image.size, (255, 255, 255))
        rgb_image.paste(image, mask=image.split()[3])  # Use alpha channel as mask
        image = rgb_image
    elif image.mode != "RGB":
        image = image.convert("RGB")

    # Step 2: Compress to stay under file size limit
    quality = 95
    buffer = io.BytesIO()

    while quality > 20:  # Don't go below 20% quality
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, optimize=True)
        file_size = buffer.tell()

        if file_size <= max_file_size:
            break

        # If still too large, reduce quality
        quality -= 10

    # Step 3: If still too large after max compression, reduce dimensions further
    if buffer.tell() > max_file_size:
        scale_factor = 0.8
        while buffer.tell() > max_file_size and scale_factor > 0.3:
            new_width = int(image.width * scale_factor)
            new_height = int(image.height * scale_factor)
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            resized.save(buffer, format="JPEG", quality=75, optimize=True)

            if buffer.tell() <= max_file_size:
                break

            scale_factor -= 0.1

    screenshot_bytes = buffer.getvalue()

    # Return base64 encoded string
    return base64.b64encode(screenshot_bytes).decode("utf-8")
