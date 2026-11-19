"""OCR local gratuito usando el motor nativo de Windows 11 (Windows.Media.Ocr).

Devuelve tanto el texto completo como las coordenadas exactas (bounding boxes)
de cada palabra para poder hacer clic palabra por palabra sobre la captura.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass
class OcrWord:
    """Palabra detectada por OCR con su rectángulo en píxeles relativos al recorte."""

    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass
class OcrResult:
    """Resultado completo del OCR local."""

    full_text: str
    words: list[OcrWord]
    language_tag: str


_POWERSHELL_OCR_SCRIPT = r"""
param([string]$ImagePath)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and
    $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await-WinRT($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

$langs = [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages
$selectedLang = $langs | Where-Object { $_.LanguageTag -like "en-*" } | Select-Object -First 1
if (-not $selectedLang) {
    $selectedLang = $langs | Select-Object -First 1
}
if (-not $selectedLang) {
    throw "No hay idiomas de OCR disponibles en Windows."
}

$ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($selectedLang)
if (-not $ocrEngine) {
    throw "No se pudo inicializar OcrEngine para $($selectedLang.LanguageTag)."
}

$file = Await-WinRT ([Windows.Storage.StorageFile]::GetFileFromPathAsync($ImagePath)) ([Windows.Storage.StorageFile])
$stream = Await-WinRT ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$ocrResult = Await-WinRT ($ocrEngine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

$wordsList = @()
foreach ($line in $ocrResult.Lines) {
    foreach ($word in $line.Words) {
        $rect = $word.BoundingRect
        $wordsList += [PSCustomObject]@{
            text   = $word.Text
            x      = [double]$rect.X
            y      = [double]$rect.Y
            width  = [double]$rect.Width
            height = [double]$rect.Height
        }
    }
}

$linesText = ($ocrResult.Lines | ForEach-Object { $_.Text }) -join "`n"

$output = [PSCustomObject]@{
    language_tag = $selectedLang.LanguageTag
    full_text    = $linesText
    words        = $wordsList
}

$output | ConvertTo-Json -Depth 4 -Compress
"""


def run_windows_ocr(crop_image: Image.Image) -> OcrResult:
    """Ejecuta Windows.Media.Ocr sobre un recorte PIL y devuelve palabras + bounding boxes."""
    # Escalamos recortes chicos 2x para mejorar la precisión del OCR en fuentes pequeñas
    scale = 2.0 if min(crop_image.width, crop_image.height) < 350 else 1.0
    if scale > 1.0:
        img_to_ocr = crop_image.resize(
            (int(crop_image.width * scale), int(crop_image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    else:
        img_to_ocr = crop_image

    with tempfile.TemporaryDirectory(prefix="english_lens_ocr_") as tmpdir:
        img_path = Path(tmpdir) / "crop.png"
        ps_path = Path(tmpdir) / "ocr.ps1"
        img_to_ocr.save(img_path, format="PNG")
        ps_path.write_text(_POWERSHELL_OCR_SCRIPT, encoding="utf-8")

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps_path),
                "-ImagePath",
                str(img_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            creationflags=creationflags,
            timeout=15,
        )

    if proc.returncode != 0:
        raise RuntimeError(f"Error en Windows OCR: {proc.stderr.strip() or proc.stdout.strip()}")

    raw_json = proc.stdout.strip()
    if not raw_json:
        return OcrResult(full_text="", words=[], language_tag="unknown")

    data = json.loads(raw_json)
    raw_words = data.get("words") or []
    if isinstance(raw_words, dict):
        # ConvertTo-Json en PowerShell 5.1 serializa listas de 1 elemento como objeto
        raw_words = [raw_words]

    words = [
        OcrWord(
            text=str(item["text"]),
            x=float(item["x"]) / scale,
            y=float(item["y"]) / scale,
            width=float(item["width"]) / scale,
            height=float(item["height"]) / scale,
        )
        for item in raw_words
    ]

    return OcrResult(
        full_text=str(data.get("full_text") or "").strip(),
        words=words,
        language_tag=str(data.get("language_tag") or "unknown"),
    )
