"""Turn what the candidate said into the digits to store.

Digit characters are copied as spoken. Words, in any language or grouping, are
not looked up in a spelling list. The hearing of that sentence is passed in
and stored when it is the number they said.
"""

from __future__ import annotations

import re


def _script_digits(start: int) -> str:
    return "".join(chr(start + i) for i in range(10))


# Digit characters only. These are the glyphs for 0-9, not names of numbers.
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

_LAST = re.compile(
    r"\b(last|end|ending|akhiri|aakhri|aakhiri|आखिरी|आखरी|अंत)\b",
    re.IGNORECASE,
)
_FIRST = re.compile(
    r"(first|start|starting|pehla|pehli|shuru|शुरुआत|शुरु|शुरू|पहले)",
    re.IGNORECASE,
)
_NEG = re.compile(
    r"(nahi|nahin|naahi|not|wrong|galat|गलत|नहीं|नही|नाही|काय नाही)",
    re.IGNORECASE,
)


def _as_digits(text: str) -> str:
    return str(text or "").translate(_DIGIT_CHARS)


def has_spoken_words(text: str) -> bool:
    """True when the sentence has words the digit walk cannot read on its own."""
    if _english_number_phrase(text) is not None:
        return False
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


# English groups only: "eighty-seven" is 87, "eight seven" is 8 then 7.
# Other languages stay with the hearing of the sentence.
_EN_ONES = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_EN_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_EN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_EN_SKIP = {"and", "uh", "um"}


def _english_number_phrase(text: str) -> str | None:
    """Digits when the phrase is only English number words. None if any other word is in it."""
    tokens = re.findall(r"[a-z0-9]+", _as_digits(text).lower().replace("-", " "))
    if not tokens:
        return None
    out: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in _EN_SKIP:
            i += 1
            continue
        if tok.isdigit():
            out.append(tok)
            i += 1
            continue
        if tok in ("double", "triple") and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            digit = _EN_ONES.get(nxt)
            if digit is None and nxt.isdigit() and len(nxt) == 1:
                digit = int(nxt)
            if digit is None:
                return None
            out.append(str(digit) * (2 if tok == "double" else 3))
            i += 2
            continue
        if tok in _EN_TENS:
            value = _EN_TENS[tok]
            if i + 1 < len(tokens) and tokens[i + 1] in _EN_ONES and _EN_ONES[tokens[i + 1]] != 0:
                value += _EN_ONES[tokens[i + 1]]
                i += 2
            else:
                i += 1
            out.append(str(value))
            continue
        if tok in _EN_TEENS or tok in _EN_ONES:
            out.append(str(_EN_TEENS[tok] if tok in _EN_TEENS else _EN_ONES[tok]))
            i += 1
            continue
        return None
    return "".join(out)


def digit_chunks(text: str) -> list[str]:
    """Digit groups written in the transcript, in order. Words are left untouched."""
    return re.findall(r"\d+", _as_digits(text))


_PHRASE_SPLIT = re.compile(r"[.।!?॥？]+")


def _drop_repeated_phrase(text: str) -> str:
    """STT often finalizes the same phrase twice: '911, 2323. 911, 2323.'

    That must stay one number. Two different groups ('98765. 43210') are kept.
    """
    parts = [p.strip(" ,;:") for p in _PHRASE_SPLIT.split(text or "") if p.strip(" ,;:")]
    if len(parts) < 2:
        return text
    keys = ["".join(digit_chunks(p)) for p in parts]
    if keys[0] and all(k == keys[0] for k in keys):
        return parts[0]
    return text


def parse_spoken_phone(text: str) -> str:
    """Digits written in the transcript, including English groups like eighty-seven."""
    phrase = _drop_repeated_phrase(text)
    folded = _english_number_phrase(phrase)
    if folded is not None:
        return folded
    return "".join(digit_chunks(phrase))


def heard_phone(text: str, heard: str = "") -> str:
    """The digits to store from this utterance.

    A sentence that is only digits is stored as those digits. When they used
    words, `heard` is the reading of what they said, in any language or grouping.
    A yes or no is not a number. A reading cannot replace a digits-only sentence.
    """
    literal = trunk_prefix(parse_spoken_phone(text))
    heard_digits = trunk_prefix(re.sub(r"\D", "", heard or ""))
    if len(heard_digits) > 13:
        heard_digits = ""
    if has_spoken_words(text) and heard_digits and not _bare_yes_no(text):
        return heard_digits
    return literal


def trunk_prefix(digits: str) -> str:
    if digits.startswith("0091"):
        digits = digits[4:]
    elif digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    return digits


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


def _splice(prev: str, old: str, new: str) -> str:
    if old and old in prev and new:
        return prev.replace(old, new, 1)
    return prev


def correct_phone(previous: str, text: str) -> str:
    """Apply a correction onto the number already read back.

    A full restatement replaces it. Two groups replace only the group that is
    not already in the number, whichever is said first. 'last four 3549' and
    '3549 last' both rewrite the end. A bare denial with no digits returns empty.
    """
    prev = trunk_prefix(re.sub(r"\D", "", str(previous or "")))
    chunks = digit_chunks(text)
    if not chunks:
        return ""
    flat = trunk_prefix("".join(chunks))
    if any(len(trunk_prefix(c)) >= 10 for c in chunks) or len(flat) >= 10:
        long = next((trunk_prefix(c) for c in chunks if len(trunk_prefix(c)) >= 10), flat)
        return long
    if flat == prev:
        return prev

    usable = [c for c in chunks if len(c) >= 2]
    neg = _NEG.search(text or "")
    if neg and prev:
        left, right = digit_chunks(text[: neg.start()]), digit_chunks(text[neg.end() :])
        left = [c for c in left if len(c) >= 2]
        right = [c for c in right if len(c) >= 2]
        if len(left) == 1 and len(right) == 1:
            if left[0] in prev:
                return _splice(prev, left[0], right[0])
            if right[0] in prev and left[0] not in prev:
                return _splice(prev, right[0], left[0])
        if left and not right and len(left) >= 2 and left[-1] in prev:
            return _splice(prev, left[-1], left[-2])
        if len(usable) == 1 and usable[0] != prev:
            only = usable[0]
            # "नहीं, नंबर है 9112323550" replaces the whole number.
            # "start में 911, बाकी सही है" is one piece — keep the rest and splice below.
            if len(only) >= 10 or len(only) >= len(prev):
                return only

    present = [c for c in usable if c in prev]
    absent = [c for c in usable if c not in prev]
    if len(present) >= 1 and len(absent) == 1 and prev:
        return _splice(prev, max(present, key=len), absent[0])
    if len(absent) == 1 and prev and not present:
        new = absent[0]
        if _LAST.search(text) and len(new) < len(prev):
            return prev[: len(prev) - len(new)] + new
        if _FIRST.search(text) and len(new) < len(prev):
            return new + prev[len(new) :]
        # One or two stray digits ("28") are not a correction of this number.
        if len(new) >= 3:
            best_at, best_score = 0, -1
            for at in range(0, len(prev) - len(new) + 1):
                window = prev[at : at + len(new)]
                score = sum(a == b for a, b in zip(window, new))
                if score > best_score:
                    best_score, best_at = score, at
            if best_score >= max(1, len(new) - 1):
                return prev[:best_at] + new + prev[best_at + len(new) :]
    if present and not absent:
        return prev
    if prev and len(flat) < len(prev):
        if neg:
            return flat
        # Still dictating a short number: "9112323" then "540". A one- or two-digit
        # reply ("28") is the next answer, not more of this number.
        if len(prev) < 10 and len(flat) >= 3 and flat not in prev and len(prev) + len(flat) <= 13:
            return prev + flat
        return prev
    return flat
