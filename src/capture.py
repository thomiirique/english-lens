"""Captura de pantalla y generación de fondo desenfocado para el overlay."""

from __future__ import annotations

from dataclasses import dataclass

import mss
from PIL import Image, ImageEnhance, ImageFilter


@dataclass
class ScreenCapture:
    """Contiene la captura original, su versión desenfocada y la geometría del monitor."""

    original: Image.Image
    blurred: Image.Image
    left: int
    top: int
    width: int
    height: int


def capture_monitor_at(cursor_x: int, cursor_y: int, blur_radius: int = 14) -> ScreenCapture:
    """Captura el monitor donde está ubicado el cursor y genera su versión desenfocada."""
    with mss.mss() as sct:
        monitors = sct.monitors[1:]  # Índice 0 es el escritorio virtual combinado
        target = monitors[0]
        for mon in monitors:
            if (
                mon["left"] <= cursor_x < mon["left"] + mon["width"]
                and mon["top"] <= cursor_y < mon["top"] + mon["height"]
            ):
                target = mon
                break

        raw = sct.grab(target)
        original = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Desenfoque rápido (downscale -> blur -> upscale) para que sea instantáneo incluso en 4K
    scale = 2
    small = original.resize(
        (max(1, original.width // scale), max(1, original.height // scale)),
        Image.Resampling.BILINEAR,
    )
    blurred_small = small.filter(ImageFilter.GaussianBlur(radius=max(1, blur_radius // scale)))
    blurred = blurred_small.resize(original.size, Image.Resampling.BILINEAR)
    blurred = ImageEnhance.Brightness(blurred).enhance(0.58)

    return ScreenCapture(
        original=original,
        blurred=blurred,
        left=target["left"],
        top=target["top"],
        width=target["width"],
        height=target["height"],
    )
