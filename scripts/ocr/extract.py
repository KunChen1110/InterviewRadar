from collections.abc import Callable
from dataclasses import dataclass

OcrEngine = Callable[[str], tuple[str, float]]


@dataclass
class OcrResult:
    text: str
    confidence: float
    needs_vision: bool


def extract_text_from_image(
    path: str, engine: OcrEngine | None = None, min_confidence: float = 0.6
) -> OcrResult:
    if engine is None:
        return OcrResult(text="", confidence=0.0, needs_vision=True)
    text, confidence = engine(path)
    needs_vision = confidence < min_confidence or not text.strip()
    return OcrResult(text=text, confidence=confidence, needs_vision=needs_vision)
