"""Store the mobile digits the candidate said.

Digits written in the transcript are copied as-is (any script). When they speak
number-words — any language, mix, or grouping — the hearing (LLM) supplies the
digits. This module does not translate number-words itself.
"""

from __future__ import annotations

import re


def _script_digits(start: int) -> str:
    return "".join(chr(start + i) for i in range(10))


# Digit glyphs for 0-9 only — not names of numbers.
_DIGIT_CHARS = str.maketrans(
    _script_digits(0x0966)  # Devanagari
    + _script_digits(0x09E6)  # Bengali
    + _script_digits(0x0A66)  # Gurmukhi
    + _script_digits(0x0AE6)  # Gujarati
    + _script_digits(0x0B66)  # Odia
    + "௦௧௨௩௪௫௬௭௮௯"  # Tamil
    + _script_digits(0x0C66)  # Telugu
    + _script_digits(0x0CE6)  # Kannada
    + _script_digits(0x0D66),  # Malayalam
    "0123456789" * 9,
)


def _as_digits(text: str) -> str:
    return str(text or "").translate(_DIGIT_CHARS)


def has_spoken_words(text: str) -> bool:
    """True when the sentence has words, not only digits."""
    without_digits = re.sub(r"\d+", " ", _as_digits(text))
    return bool(re.search(r"[^\W\d_]", without_digits, flags=re.UNICODE))


def _bare_yes_no(text: str) -> bool:
    """A yes or no, with no number in it."""
    if parse_spoken_phone(text):
        return False
    from interview.indic_phrases import CONFIRM_NO_RE, CONFIRM_YES_RE

    tokens = [t for t in re.split(r"[^\w]+", _as_digits(text).lower(), flags=re.UNICODE) if t]
    if len(tokens) > 3:
        return False
    return bool(CONFIRM_YES_RE.search(text) or CONFIRM_NO_RE.search(text))


def digit_chunks(text: str) -> list[str]:
    """Digit groups written in the transcript, in order."""
    return re.findall(r"\d+", _as_digits(text))


_PHRASE_SPLIT = re.compile(r"[.।!?॥？]+")


def _drop_repeated_phrase(text: str) -> str:
    """STT often finalizes the same phrase twice: '911, 2323. 911, 2323.'"""
    parts = [p.strip(" ,;:") for p in _PHRASE_SPLIT.split(text or "") if p.strip(" ,;:")]
    if len(parts) < 2:
        return text
    keys = ["".join(digit_chunks(p)) for p in parts]
    if keys[0] and all(k == keys[0] for k in keys):
        return parts[0]
    return text


def parse_spoken_phone(text: str) -> str:
    """Digits written in the transcript. Words are left for the hearing."""
    return "".join(digit_chunks(_drop_repeated_phrase(text)))


def _literal_number(text: str) -> str:
    """Join digit groups when the transcript is digits-only."""
    phrase = _drop_repeated_phrase(text)
    return trunk_prefix("".join(digit_chunks(phrase)))


def _long_digit_run(text: str) -> str:
    """One clear mobile-length run written in a wordy sentence; never scrap digits."""
    phrase = _drop_repeated_phrase(text)
    long = [trunk_prefix(c) for c in digit_chunks(phrase) if len(trunk_prefix(c)) >= 8]
    return long[0] if len(long) == 1 else ""


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[^\W\d_]+", _as_digits(text), flags=re.UNICODE)


def _hearing_plausible(text: str, heard: str) -> bool:
    """Reject a full mobile invented from a short non-number phrase.

    Shorter hearings (groups like 'char sau sattar' → 470) are always kept.
    A 10-digit hearing needs enough spoken tokens that they could have said it
    (roughly one token per two digits — pairs or larger groups).
    """
    if len(heard) < 10:
        return True
    words = _word_tokens(text)
    return len(words) >= 3 and len(heard) <= 2 * len(words)


def store_phone(text: str, heard: str = "") -> str:
    """The digits to store from this utterance.

    Digits-only speech → those digits. A long digit run already in the
    transcript wins over the hearing. Number-words (any language or mix) →
    `heard`. Short digit scraps in a wordy sentence are ignored.
    """
    if _bare_yes_no(text):
        return ""
    if not has_spoken_words(text):
        return _literal_number(text)
    written = _long_digit_run(text)
    if written:
        return written
    heard_digits = trunk_prefix(re.sub(r"\D", "", heard or ""))
    if heard_digits and len(heard_digits) <= 13 and _hearing_plausible(text, heard_digits):
        return heard_digits
    return ""


def trunk_prefix(digits: str) -> str:
    """Drop India country / trunk prefixes only when the length makes that clear.

    A real 10-digit mobile may start with 91 (e.g. 9123456789) — never strip those.
    Country code is removed only for 91 + 10 national digits (12), 091… (13), or 0091….
    """
    d = re.sub(r"\D", "", str(digits or ""))
    if d.startswith("0091") and len(d) >= 14:
        d = d[4:]
    elif d.startswith("091") and len(d) == 13:
        d = d[3:]
    elif d.startswith("91") and len(d) == 12:
        d = d[2:]
    if d.startswith("0") and len(d) == 11:
        d = d[1:]
    return d


def _lang(language: str) -> str:
    code = (language or "hi-IN").split("-")[0].lower()
    return "or" if code == "od" else code


def phone_ask_line(language: str) -> str:
    """One sentence. The mobile ask never shares a turn with another question."""
    return {
        "en": "What is your mobile number?",
        "hi": "आपका मोबाइल नंबर क्या है?",
        "mr": "तुमचा मोबाइल नंबर काय आहे?",
        "gu": "તમારો મોબાઇલ નંબર શું છે?",
        "te": "మీ మొబైల్ నంబర్ ఏమిటి?",
        "ta": "உங்க மொபைல் நம்பர் என்ன?",
        "kn": "ನಿಮ್ಮ ಮೊಬೈಲ್ ನಂಬರ್ ಏನು?",
        "ml": "നിങ്ങളുടെ മൊബൈൽ നമ്പർ എന്താണ്?",
        "bn": "আপনার মোবাইল নম্বর কত?",
        "pa": "ਤੁਹਾਡਾ ਮੋਬਾਈਲ ਨੰਬਰ ਕੀ ਹੈ?",
        "or": "ଆପଣଙ୍କ ମୋବାଇଲ୍ ନମ୍ବର କଣ?",
    }.get(_lang(language), "आपका मोबाइल नंबर क्या है?")


def phone_confirm_line(language: str, shown: str) -> str:
    """Read the digits back. Nothing else — no name, no next question."""
    return {
        "en": "I heard {d}. Is that correct?",
        "hi": "मैंने सुना {d}. क्या यह सही है?",
        "mr": "मला ऐकलं {d}. हे बरोबर आहे का?",
        "gu": "મેં સાંભળ્યું {d}. શું આ સાચું છે?",
        "te": "నేను విన్నాను {d}. ఇది సరియైనదేనా?",
        "ta": "நான் கேட்டது {d}. இது சரியா?",
        "kn": "ನಾನು ಕೇಳಿದ್ದು {d}. ಇದು ಸರಿಯಾ?",
        "ml": "ഞാൻ കേട്ടത് {d}. ഇത് ശരിയാണോ?",
        "bn": "আমি শুনেছি {d}. এটা ঠিক আছে?",
        "pa": "ਮੈਂ ਸੁਣਿਆ {d}. ਕੀ ਇਹ ਠੀਕ ਹੈ?",
        "or": "ମୁଁ ଶୁଣିଲି {d}. ଏହା ଠିକ୍ କି?",
    }.get(_lang(language), "मैंने सुना {d}. क्या यह सही है?").format(d=shown)


def body_confirm_line(language: str, height_phrase: str, weight_kg: int | str) -> str:
    """One read-back for height and weight. height_phrase keeps the candidate's unit."""
    h, w = str(height_phrase), str(weight_kg)
    return {
        "en": f"I heard height {h} and weight {w} kilograms. Is that correct?",
        "hi": f"मैंने सुना कद {h} और वजन {w} किलो. क्या यह सही है?",
        "mr": f"मला ऐकलं उंची {h} आणि वजन {w} किलो. हे बरोबर आहे का?",
        "gu": f"મેં સાંભળ્યું ઊંચાઈ {h} અને વજન {w} કિલો. શું આ સાચું છે?",
        "te": f"నేను విన్నాను ఎత్తు {h} మరియు బరువు {w} కిలోలు. ఇది సరియైనదేనా?",
        "ta": f"நான் கேட்டது உயரம் {h} மற்றும் எடை {w} கிலோ. இது சரியா?",
        "kn": f"ನಾನು ಕೇಳಿದ್ದು ಎತ್ತರ {h} ಮತ್ತು ತೂಕ {w} ಕೆಜಿ. ಇದು ಸರಿಯಾ?",
        "ml": f"ഞാൻ കേട്ടത് ഉയരം {h} കൂടാതെ ഭാരം {w} കിലോ. ഇത് ശരിയാണോ?",
        "bn": f"আমি শুনেছি উচ্চতা {h} এবং ওজন {w} কেজি. এটা ঠিক আছে?",
        "pa": f"ਮੈਂ ਸੁਣਿਆ ਕੱਦ {h} ਅਤੇ ਭਾਰ {w} ਕਿਲੋ. ਕੀ ਇਹ ਠੀਕ ਹੈ?",
        "or": f"ମୁଁ ଶୁଣିଲି ଉଚ୍ଚତା {h} ଏବଂ ଓଜନ {w} କିଲୋ. ଏହା ଠିକ୍ କି?",
    }.get(_lang(language), f"मैंने सुना कद {h} और वजन {w} किलो. क्या यह सही है?")


def phone_invalid_line(language: str, shown: str) -> str:
    return {
        "en": "{d} is not a complete mobile number. Please say the number again.",
        "hi": "{d} पूरा मोबाइल नंबर नहीं है. नंबर फिर से बोलिए.",
        "mr": "{d} पूर्ण मोबाइल नंबर नाही. नंबर परत सांगा.",
        "gu": "{d} પૂરો મોબાઇલ નંબર નથી. નંબર ફરી બોલો.",
        "te": "{d} పూర్తి మొబైల్ నంబర్ కాదు. నంబర్ మళ్ళీ చెప్పండి.",
        "ta": "{d} முழு மொபைல் நம்பர் இல்லை. நம்பரை மறுபடியும் சொல்லுங்க.",
        "kn": "{d} ಪೂರ್ತಿ ಮೊಬೈಲ್ ನಂಬರ್ ಅಲ್ಲ. ನಂಬರ್ ಮತ್ತೆ ಹೇಳಿ.",
        "ml": "{d} പൂർണ്ണ മൊബൈൽ നമ്പർ അല്ല. നമ്പർ വീണ്ടും പറയൂ.",
        "bn": "{d} পুরো মোবাইল নম্বর নয়. নম্বর আবার বলুন.",
        "pa": "{d} ਪੂਰਾ ਮੋਬਾਈਲ ਨੰਬਰ ਨਹੀਂ. ਨੰਬਰ ਦੁਬਾਰਾ ਬੋਲੋ.",
        "or": "{d} ପୂରା ମୋବାଇଲ୍ ନମ୍ବର ନୁହେଁ. ନମ୍ବର ଆଉଥରେ କୁହନ୍ତୁ.",
    }.get(_lang(language), "{d} पूरा मोबाइल नंबर नहीं है. नंबर फिर से बोलिए.").format(d=shown)


def phone_again_line(language: str) -> str:
    return {
        "en": "Please say the mobile number once more.",
        "hi": "मोबाइल नंबर एक बार फिर से बोलिए.",
        "mr": "मोबाइल नंबर एकदा परत सांगा.",
        "gu": "મોબાઇલ નંબર એક વાર ફરી બોલો.",
        "te": "మొబైల్ నంబర్ ఒకసారి మళ్ళీ చెప్పండి.",
        "ta": "மொபைல் நம்பரை ஒரு தடவை மறுபடியும் சொல்லுங்க.",
        "kn": "ಮೊಬೈಲ್ ನಂಬರ್ ಒಮ್ಮೆ ಮತ್ತೆ ಹೇಳಿ.",
        "ml": "മൊബൈൽ നമ്പർ ഒരിക്കൽ കൂടി പറയൂ.",
        "bn": "মোবাইল নম্বর আরেকবার বলুন.",
        "pa": "ਮੋਬਾਈਲ ਨੰਬਰ ਇੱਕ ਵਾਰ ਫਿਰ ਬੋਲੋ.",
        "or": "ମୋବାଇଲ୍ ନମ୍ବର ଥରେ ଆଉ କୁହନ୍ତୁ.",
    }.get(_lang(language), "मोबाइल नंबर एक बार फिर से बोलिए.")


def valid_indian_mobile(digits: str) -> bool:
    number = trunk_prefix(digits)
    return len(number) == 10 and number[0] in "6789"
