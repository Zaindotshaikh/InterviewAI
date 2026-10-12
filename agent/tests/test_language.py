"""Language detection unit tests."""

from interview.language import detect_script_language, get_profile


def test_tamil_detection():
    text = "நான் மூன்று வருடங்கள் நர்ஸாக வேலை செய்தேன்"
    assert detect_script_language(text) == "ta-IN"


def test_telugu_detection():
    text = "నేను ఐసీయూ వార్డులో పని చేశాను"
    assert detect_script_language(text) == "te-IN"


def test_speaker_map():
    assert get_profile("ml-IN").tts_speaker == "pooja"
    assert get_profile("hi-IN").stt_mode == "codemix"
