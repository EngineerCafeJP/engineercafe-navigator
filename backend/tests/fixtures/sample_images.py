"""Synthetic test image generators."""

import numpy as np


def create_blank_image(width: int = 100, height: int = 100, channels: int = 3) -> np.ndarray:
    """Create a blank black image.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        channels: Number of color channels (3 for RGB, 1 for grayscale)

    Returns:
        Numpy array of shape (height, width, channels) with dtype uint8

    Examples:
        >>> img = create_blank_image(100, 100, 3)
        >>> assert img.shape == (100, 100, 3)
        >>> assert img.dtype == np.uint8
        >>> assert img.max() == 0  # All black
    """
    return np.zeros((height, width, channels), dtype=np.uint8)


def create_white_image(width: int = 100, height: int = 100) -> np.ndarray:
    """Create a blank white image.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Numpy array of shape (height, width, 3) with all pixels white (255)

    Examples:
        >>> img = create_white_image(100, 100)
        >>> assert img.shape == (100, 100, 3)
        >>> assert img.min() == 255  # All white
    """
    return np.ones((height, width, 3), dtype=np.uint8) * 255


def create_wide_image(width: int = 1920, height: int = 1080) -> np.ndarray:
    """Create a wide image that will trigger resizing (>640px).

    This is useful for testing image preprocessing logic that resizes
    images larger than 640px width.

    Args:
        width: Image width in pixels (default: 1920)
        height: Image height in pixels (default: 1080)

    Returns:
        Numpy array of shape (height, width, 3)

    Examples:
        >>> img = create_wide_image()
        >>> assert img.shape[1] == 1920  # Width
        >>> assert img.shape[0] == 1080  # Height
    """
    return np.zeros((height, width, 3), dtype=np.uint8)


def create_exact_640_image() -> np.ndarray:
    """Create an image exactly 640px wide (boundary test).

    This tests the edge case where an image is exactly at the resize threshold.

    Returns:
        Numpy array of shape (480, 640, 3)

    Examples:
        >>> img = create_exact_640_image()
        >>> assert img.shape == (480, 640, 3)
        >>> assert img.shape[1] == 640  # Exactly 640px wide
    """
    return np.zeros((480, 640, 3), dtype=np.uint8)


def create_qr_like_image() -> np.ndarray:
    """Create a synthetic image with QR-code-like pattern (for mocked detection).

    Creates a simple black and white pattern that resembles a QR code.
    This is useful for testing QR detection logic with mocked detectors.

    Returns:
        Numpy array of shape (200, 200, 3) with simple black/white pattern

    Examples:
        >>> img = create_qr_like_image()
        >>> assert img.shape == (200, 200, 3)
        >>> # Has both black and white regions
        >>> assert img.min() == 0 and img.max() == 255
    """
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    # Simple pattern: white square in center
    img[50:150, 50:150] = 255
    return img


def create_gradient_image(width: int = 100, height: int = 100) -> np.ndarray:
    """Create an image with horizontal gradient from black to white.

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Numpy array with gradient pattern

    Examples:
        >>> img = create_gradient_image(100, 100)
        >>> assert img[0, 0, 0] < img[0, 99, 0]  # Left darker than right
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for x in range(width):
        intensity = int((x / width) * 255)
        img[:, x] = intensity
    return img


def create_checkerboard_image(
    width: int = 100,
    height: int = 100,
    square_size: int = 10,
) -> np.ndarray:
    """Create a checkerboard pattern image.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        square_size: Size of each checkerboard square

    Returns:
        Numpy array with checkerboard pattern

    Examples:
        >>> img = create_checkerboard_image(100, 100, 10)
        >>> assert img.shape == (100, 100, 3)
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(0, height, square_size):
        for x in range(0, width, square_size):
            if ((y // square_size) + (x // square_size)) % 2 == 0:
                y_end = min(y + square_size, height)
                x_end = min(x + square_size, width)
                img[y:y_end, x:x_end] = 255
    return img


def create_colored_image(
    width: int = 100,
    height: int = 100,
    color: tuple = (255, 0, 0),
) -> np.ndarray:
    """Create a solid color image.

    Args:
        width: Image width in pixels
        height: Image height in pixels
        color: RGB color tuple (R, G, B) where each value is 0-255

    Returns:
        Numpy array filled with specified color

    Examples:
        >>> img = create_colored_image(100, 100, color=(255, 0, 0))  # Red
        >>> assert img[0, 0, 0] == 255  # R channel
        >>> assert img[0, 0, 1] == 0    # G channel
        >>> assert img[0, 0, 2] == 0    # B channel
    """
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, :] = color
    return img


def create_text_like_image() -> np.ndarray:
    """Create an image with text-like patterns (for OCR testing).

    Creates simple horizontal lines that resemble text lines.

    Returns:
        Numpy array with text-like patterns

    Examples:
        >>> img = create_text_like_image()
        >>> assert img.shape == (200, 300, 3)
    """
    img = np.ones((200, 300, 3), dtype=np.uint8) * 255  # White background

    # Create horizontal lines that look like text
    line_positions = [50, 80, 110, 140]
    for y in line_positions:
        img[y : y + 5, 20:280] = 0  # Black line

    return img


def create_small_image(width: int = 32, height: int = 32) -> np.ndarray:
    """Create a very small image (for boundary testing).

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Numpy array of small size

    Examples:
        >>> img = create_small_image(32, 32)
        >>> assert img.shape == (32, 32, 3)
    """
    return np.zeros((height, width, 3), dtype=np.uint8)


def create_portrait_image(width: int = 480, height: int = 640) -> np.ndarray:
    """Create a portrait-oriented image (height > width).

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Numpy array in portrait orientation

    Examples:
        >>> img = create_portrait_image()
        >>> assert img.shape[0] > img.shape[1]  # Height > Width
    """
    return np.zeros((height, width, 3), dtype=np.uint8)


def create_grayscale_image(width: int = 100, height: int = 100) -> np.ndarray:
    """Create a grayscale image (single channel).

    Args:
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Numpy array with single channel (grayscale)

    Examples:
        >>> img = create_grayscale_image(100, 100)
        >>> assert img.shape == (100, 100)  # No channel dimension
        >>> assert img.dtype == np.uint8
    """
    return np.zeros((height, width), dtype=np.uint8)
