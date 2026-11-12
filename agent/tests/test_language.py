"""Language detection unit tests."""

from interview.language import (
    detect_script_language,
    explicit_language_switch_request,
    get_profile,
    native_script_reminder,
)
from interview.prompts import spoken_style


def test_tamil_detection():
    text = "நான் மூன்று வருடங்கள் நர்ஸாக வேலை செய்தேன்"
    assert detect_script_language(text) == "ta-IN"


def test_telugu_detection():
    text = "నేను ఐసీయూ వార్డులో పని చేశాను"
    assert detect_script_language(text) == "te-IN"


def test_speaker_map():
    assert get_profile("ml-IN").tts_speaker == "pooja"
    assert get_profile("hi-IN").stt_mode == "codemix"
    assert get_profile("gu-IN").label == "Gujarati"


def test_gujarati_opening_seed():
    from interview.prompts import opening_seed
    assert "નમસ્તે" in opening_seed("gu-IN")
    assert "નમસ્તે" in opening_seed("gu-IN", elevenlabs=True)
    assert "[warmly]" in opening_seed("gu-IN", elevenlabs=True)
    assert "नमस्ते" not in opening_seed("gu-IN")


def test_english_job_words_are_not_a_language_switch_request():
    assert not explicit_language_switch_request("I did GNM in 2019 in ICU")
    assert not explicit_language_switch_request("हाँ, comfortable हूँ diaper care में")
    assert explicit_language_switch_request("please speak in English")
    assert explicit_language_switch_request("हिंदी में बोलिए")


def test_pinned_voice_ignores_language_map():
    from config import Settings
    from providers.elevenlabs_voices import pinned_elevenlabs_voice_id

    s = Settings(
        elevenlabs_voice_id="fallback",
        elevenlabs_voice_id_local="fallback",
        elevenlabs_voice_by_lang="hi-IN:hindi-voice,en-IN:english-voice",
    )
    assert pinned_elevenlabs_voice_id("join-sujata", "en-IN", s) == "join-sujata"
    assert pinned_elevenlabs_voice_id("join-sujata", "hi-IN", s) == "join-sujata"
    assert pinned_elevenlabs_voice_id("", "hi-IN", s) == "hindi-voice"


def test_elevenlabs_voice_is_sujata_for_every_language():
    from config import Settings
    from providers.elevenlabs_voices import elevenlabs_voice_for

    sujata = "4mCfn38CsM9hGLvDrPxv"
    s = Settings(
        elevenlabs_voice_id=sujata,
        elevenlabs_voice_id_local=sujata,
        elevenlabs_voice_by_lang="",
    )
    assert elevenlabs_voice_for("en-IN", s) == sujata
    assert elevenlabs_voice_for("hi-IN", s) == sujata
    assert elevenlabs_voice_for("gu-IN", s) == sujata
    assert elevenlabs_voice_for("mr-IN", s) == sujata


def test_odia_codes_and_per_language_voice():
    from config import Settings
    from providers.elevenlabs_voices import elevenlabs_language, elevenlabs_voice_for, scribe_language_hints

    assert elevenlabs_language("od-IN") == "or"
    assert elevenlabs_language("hi-IN") == "hi"
    assert elevenlabs_language("en-IN") == "en"
    assert scribe_language_hints("od-IN") == ("or", ["en", "hi"])
    assert scribe_language_hints("en-IN") == ("en", [])
    assert scribe_language_hints("hi-IN") == ("hi", ["en"])
    assert scribe_language_hints("te-IN") == ("te", ["en", "hi"])
    assert scribe_language_hints("pa-IN") == ("pa", ["en", "hi"])

    s = Settings(
        elevenlabs_voice_id="fallback",
        elevenlabs_voice_id_local="fallback",
        elevenlabs_voice_by_lang="hi-IN:hindi-voice,od-IN:odia-voice",
    )
    assert elevenlabs_voice_for("hi-IN", s) == "hindi-voice"
    assert elevenlabs_voice_for("od-IN", s) == "odia-voice"
    assert elevenlabs_voice_for("or", s) == "odia-voice"
    assert elevenlabs_voice_for("te-IN", s) == "fallback"


def test_english_call_does_not_teach_hindi_gender():
    english = spoken_style("en-IN").lower()
    assert "kar raha hoon" in english
    assert "रहा हूँ" not in spoken_style("en-IN")
    reminder = native_script_reminder("en-IN").lower()
    assert "kar raha hoon" in reminder
    assert "english only" in reminder or "english" in reminder
    hindi = spoken_style("hi-IN", candidate_gender="male")
    assert "कर रहे हैं" in hindi
    assert "Candidate gender is MALE" in hindi
    woman_voice = spoken_style("hi-IN", candidate_gender="male", speaker_gender="female")
    assert "voice speaking these words is a woman" in woman_voice
    assert "बोल रही हूँ" in woman_voice
    assert "voice speaking these words is a man" not in woman_voice
    female = spoken_style("hi-IN", candidate_gender="female")
    assert "कर रही हैं" in female
    assert "Candidate gender is FEMALE" in female
    assert "Candidate gender is MALE" not in female
    assert "अभी आप कहाँ काम कर रहे हैं?" not in female
    neutral = spoken_style("hi-IN")
    assert "not provided" in neutral.lower()
    assert "Candidate gender is MALE" not in neutral
    assert "insulin" in hindi
    assert "potassium chloride" in hindi
    for code in ("hi-IN", "mr-IN", "ta-IN", "te-IN"):
        reminder_lang = native_script_reminder(code)
        assert "insulin" in reminder_lang
        assert "potassium chloride" in reminder_lang
        assert "local script" in reminder_lang
        assert "Latin letters — that switches the voice" not in reminder_lang
