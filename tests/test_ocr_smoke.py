"""Prueba rápida del OCR local de Windows sobre una oración en inglés con chunks."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ocr_windows import run_windows_ocr  # noqa: E402


def main() -> None:
    img = Image.new("RGB", (900, 140), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("segoeui.ttf", 28)
    except OSError:
        font = ImageFont.load_default()

    sample = "Had I known you would end up taking it for granted."
    draw.text((24, 48), sample, fill=(15, 23, 42), font=font)

    result = run_windows_ocr(img)
    print(f"Idioma OCR usado: {result.language_tag}")
    print(f"Texto detectado:  {result.full_text!r}")
    print(f"Palabras ({len(result.words)}):")
    for w in result.words:
        print(f"  - {w.text!r:12s} @ ({w.x:.1f}, {w.y:.1f}, {w.width:.1f}x{w.height:.1f})")

    assert len(result.words) >= 8, "Se esperaban al menos 8 palabras detectadas"
    print("OK: OCR local funcionando correctamente.")


if __name__ == "__main__":
    main()
