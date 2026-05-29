from scripts.ocr.extract import extract_text_from_image, OcrResult


def test_no_engine_flags_vision():
    result = extract_text_from_image("img.png")
    assert isinstance(result, OcrResult)
    assert result.needs_vision is True
    assert result.text == ""
    assert result.confidence == 0.0


def test_confident_engine_returns_text():
    engine = lambda path: ("什么是 RAG？", 0.95)
    result = extract_text_from_image("img.png", engine=engine)
    assert result.needs_vision is False
    assert result.text == "什么是 RAG？"
    assert result.confidence == 0.95


def test_low_confidence_flags_vision_but_keeps_hint():
    engine = lambda path: ("blurry guess", 0.30)
    result = extract_text_from_image("img.png", engine=engine, min_confidence=0.6)
    assert result.needs_vision is True
    assert result.text == "blurry guess"


def test_empty_text_flags_vision_even_if_confident():
    engine = lambda path: ("", 0.99)
    result = extract_text_from_image("img.png", engine=engine)
    assert result.needs_vision is True
