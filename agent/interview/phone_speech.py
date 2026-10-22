"""Turn a spoken mobile number into digits.

Candidates mix languages, say pairs (chappan baawan = 56 52), and use hundreds or
thousands. This walks the utterance left to right and concatenates those groups.
"""

from __future__ import annotations

import re

_DIGIT_CHARS = str.maketrans("०१२३४५६७८९", "0123456789")

# Single digits. Ambiguous English words (do, be, so) are listed separately.
_UNITS: dict[str, int] = {}
for _word, _n in (
    ("zero", 0), ("oh", 0), ("shunya", 0), ("shoonya", 0), ("sunna", 0), ("sonne", 0),
    ("sifar", 0), ("poojyam", 0), ("shunno", 0), ("शून्य", 0), ("सुन्ना", 0),
    ("one", 1), ("ek", 1), ("ikk", 1), ("okati", 1), ("ondu", 1), ("onnu", 1), ("onru", 1),
    ("eka", 1), ("एक", 1), ("ఒకటి", 1),
    ("two", 2), ("don", 2), ("rendu", 2), ("eradu", 2), ("randu", 2), ("irandu", 2),
    ("dui", 2), ("दो", 2), ("दोन", 2),
    ("three", 3), ("teen", 3), ("tin", 3), ("tinn", 3), ("tini", 3), ("moodu", 3),
    ("mooru", 3), ("moonnu", 3), ("moondru", 3), ("tran", 3), ("तीन", 3), ("तीनि", 3),
    ("four", 4), ("char", 4), ("chaar", 4), ("chari", 4), ("naalugu", 4), ("naalku", 4),
    ("naalu", 4), ("naangu", 4), ("चार", 4),
    ("five", 5), ("paanch", 5), ("panch", 5), ("paach", 5), ("pancha", 5), ("panj", 5),
    ("aidu", 5), ("ainthu", 5), ("anchu", 5), ("पाँच", 5), ("पांच", 5), ("पाच", 5),
    ("six", 6), ("chhe", 6), ("che", 6), ("chhah", 6), ("chha", 6), ("choy", 6), ("saha", 6),
    ("aaru", 6), ("छह", 6), ("छे", 6),
    ("seven", 7), ("saat", 7), ("sat", 7), ("satt", 7), ("sata", 7), ("edu", 7), ("elu", 7),
    ("ezhu", 7), ("सात", 7),
    ("eight", 8), ("aath", 8), ("aat", 8), ("ath", 8), ("atha", 8), ("enimidi", 8),
    ("entu", 8), ("ettu", 8), ("आठ", 8),
    ("nine", 9), ("nau", 9), ("nao", 9), ("nav", 9), ("naa", 9), ("noy", 9),
    ("tommidi", 9), ("ombhattu", 9), ("onpathu", 9), ("नौ", 9),
):
    _UNITS[_word] = _n

# "do" / "be" are 2 in Hindi and Gujarati, and ordinary English words. Use them
# only once the utterance already has another number.
_AMBIGUOUS_UNITS = {"do": 2, "be": 2}

# Two-digit words, value 10-99. Longest keys win because matching is by token.
_TEENS: dict[str, int] = {}
for _word, _n in (
    ("ten", 10), ("das", 10), ("दस", 10),
    ("eleven", 11), ("gyarah", 11), ("gyara", 11), ("ग्यारह", 11),
    ("twelve", 12), ("barah", 12), ("bara", 12), ("बारह", 12),
    ("thirteen", 13), ("terah", 13), ("tera", 13), ("तेरह", 13),
    ("fourteen", 14), ("chaudah", 14), ("चौदह", 14),
    ("fifteen", 15), ("pandrah", 15), ("pandra", 15), ("पंद्रह", 15), ("पन्द्रह", 15),
    ("sixteen", 16), ("solah", 16), ("सोलह", 16),
    ("seventeen", 17), ("satrah", 17), ("सत्रह", 17),
    ("eighteen", 18), ("atharah", 18), ("athara", 18), ("अठारह", 18),
    ("nineteen", 19), ("unnis", 19), ("उन्नीस", 19),
    ("twenty", 20), ("bees", 20), ("बीस", 20),
    ("thirty", 30), ("tees", 30), ("तीस", 30),
    ("forty", 40), ("chalees", 40), ("chalis", 40), ("चालीस", 40),
    ("fifty", 50), ("pachaas", 50), ("pachas", 50), ("पचास", 50),
    ("sixty", 60), ("saath", 60), ("sath", 60), ("साठ", 60),
    ("seventy", 70), ("sattar", 70), ("सत्तर", 70),
    ("eighty", 80), ("assi", 80), ("अस्सी", 80),
    ("ninety", 90), ("nabbe", 90), ("nabbay", 90), ("नब्बे", 90),
    ("ikkees", 21), ("ikkis", 21), ("इक्कीस", 21),
    ("baais", 22), ("baees", 22), ("बाईस", 22),
    ("teis", 23), ("तेईस", 23),
    ("chaubees", 24), ("चौबीस", 24),
    ("pachees", 25), ("pachchees", 25), ("पच्चीस", 25),
    ("chhabees", 26), ("छब्बीस", 26),
    ("sattaees", 27), ("सत्ताईस", 27),
    ("athaees", 28), ("atthais", 28), ("अट्ठाईस", 28),
    ("unatees", 29), ("untees", 29), ("उनतीस", 29),
    ("ikatees", 31), ("ikattis", 31), ("इकतीस", 31),
    ("battees", 32), ("battis", 32), ("बत्तीस", 32),
    ("taintees", 33), ("तैंतीस", 33),
    ("chauntees", 34), ("चौंतीस", 34),
    ("paintees", 35), ("paintis", 35), ("पैंतीस", 35),
    ("chhattees", 36), ("छत्तीस", 36),
    ("saintees", 37), ("सैंतीस", 37),
    ("adtees", 38), ("artees", 38), ("अड़तीस", 38),
    ("untalis", 39), ("untaalees", 39), ("उनतालीस", 39),
    ("iktalis", 41), ("इकतालीस", 41),
    ("bayalis", 42), ("bayaalees", 42), ("बयालीस", 42),
    ("taintalis", 43), ("तैंतालीस", 43),
    ("chauvalis", 44), ("चवालीस", 44),
    ("paintalis", 45), ("पैंतालीस", 45),
    ("chhiyalis", 46), ("छियालीस", 46),
    ("saintalis", 47), ("सैंतालीस", 47),
    ("adtalis", 48), ("अड़तालीस", 48),
    ("unchaas", 49), ("उनचास", 49),
    ("ikyavan", 51), ("ikyaavan", 51), ("इक्यावन", 51),
    ("baawan", 52), ("bawan", 52), ("बावन", 52), ("बावन", 52),
    ("tirpan", 53), ("tirapan", 53), ("तिरपन", 53),
    ("chauwan", 54), ("चौवन", 54),
    ("pachpan", 55), ("pachapan", 55), ("पचपन", 55),
    ("chappan", 56), ("chhappan", 56), ("छप्पन", 56),
    ("sattawan", 57), ("सत्तावन", 57),
    ("athawan", 58), ("अठावन", 58),
    ("unsath", 59), ("उनसठ", 59),
    ("iksath", 61), ("इकसठ", 61),
    ("basath", 62), ("बासठ", 62),
    ("tirsath", 63), ("tirsathh", 63), ("तिरसठ", 63),
    ("chausath", 64), ("चौंसठ", 64),
    ("painsath", 65), ("पैंसठ", 65),
    ("chhiyasath", 66), ("छियासठ", 66),
    ("sarsath", 67), ("सड़सठ", 67),
    ("adsath", 68), ("अड़सठ", 68),
    ("unhattar", 69), ("उनहत्तर", 69),
    ("ikhattar", 71), ("इकहत्तर", 71),
    ("bahattar", 72), ("बहत्तर", 72),
    ("tihattar", 73), ("तिहत्तर", 73),
    ("chauhattar", 74), ("चौहत्तर", 74),
    ("pachhattar", 75), ("पचहत्तर", 75),
    ("chhihattar", 76), ("छिहत्तर", 76),
    ("satattar", 77), ("सतहत्तर", 77),
    ("athattar", 78), ("अठहत्तर", 78),
    ("unasi", 79), ("उन्यासी", 79),
    ("ikyasi", 81), ("इक्यासी", 81),
    ("bayasi", 82), ("बयासी", 82),
    ("tirasi", 83), ("तिरासी", 83),
    ("chaurasi", 84), ("चौरासी", 84),
    ("pachasi", 85), ("पचासी", 85),
    ("chhiyasi", 86), ("छियासी", 86),
    ("sataasi", 87), ("sataasi", 87), ("सतासी", 87),
    ("athasi", 88), ("अठासी", 88),
    ("navasi", 89), ("नवासी", 89),
    ("ikyanve", 91), ("इक्यानवे", 91),
    ("baanve", 92), ("बानवे", 92),
    ("tiranve", 93), ("तिरानवे", 93),
    ("chauranve", 94), ("चौरानवे", 94),
    ("pachanve", 95), ("पचानवे", 95),
    ("chhiyanve", 96), ("छियानवे", 96),
    ("sattanve", 97), ("सत्तानवे", 97),
    ("athanve", 98), ("अट्ठानवे", 98),
    ("ninyanve", 99), ("ninyanave", 99), ("निन्यानवे", 99),
):
    _TEENS[_word] = _n

_TENS_ONLY = {10, 20, 30, 40, 50, 60, 70, 80, 90}

_HUNDRED = {"hundred", "sau", "sau", "so", "sho", "shambhar", "nooru", "nooru", "वन्दा", "सौ", "शंभर"}
_THOUSAND = {"thousand", "hazar", "hazaar", "hajar", "aayiram", "saavira", "veyyi", "हजार", "हज़ार", "आयरम"}
_DOUBLE = {"double", "dubble", "dabal", "डबल"}
_TRIPLE = {"triple", "tribble", "तिब्बल"}

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


def _tokens(text: str) -> list[str]:
    cleaned = str(text or "").translate(_DIGIT_CHARS).lower()
    cleaned = cleaned.replace("।", " ").replace(",", " ").replace("-", " ")
    return [tok for tok in re.split(r"[^\w\u0900-\u0fff]+", cleaned) if tok]


def _unit(token: str, *, allow_do: bool) -> int | None:
    if token in _UNITS:
        return _UNITS[token]
    if allow_do and token in _AMBIGUOUS_UNITS:
        return _AMBIGUOUS_UNITS[token]
    if token.isdigit() and len(token) == 1:
        return int(token)
    return None


def _is_tens_word(token: str) -> bool:
    return _TEENS.get(token) in _TENS_ONLY


def _small(tokens: list[str], i: int, *, allow_do: bool) -> tuple[int, int] | None:
    """One number below 100, and the index after it."""
    if i >= len(tokens):
        return None
    tok = tokens[i]
    if tok.isdigit() and 1 < len(tok) <= 2:
        return int(tok), i + 1
    if _is_tens_word(tok):
        base = _TEENS[tok]
        nxt = _unit(tokens[i + 1], allow_do=allow_do) if i + 1 < len(tokens) else None
        if nxt is not None and 1 <= nxt <= 9:
            return base + nxt, i + 2
        return base, i + 1
    if tok in _TEENS:
        return _TEENS[tok], i + 1
    unit = _unit(tok, allow_do=allow_do)
    if unit is not None:
        return unit, i + 1
    return None


def _compound(tokens: list[str], i: int, *, allow_do: bool) -> tuple[str, int] | None:
    """A hundreds or thousands phrase. None when the next word is not a magnitude."""
    head = _small(tokens, i, allow_do=allow_do)
    if head is None:
        return None
    value, j = head
    if j >= len(tokens) or value > 99 or tokens[j] not in _HUNDRED | _THOUSAND:
        return None
    mag = tokens[j]
    k = j + 1
    if mag in _THOUSAND:
        total = value * 1000
        if k < len(tokens):
            hung = _small(tokens, k, allow_do=allow_do)
            if hung and hung[1] < len(tokens) and tokens[hung[1]] in _HUNDRED and hung[0] < 10:
                after = _small(tokens, hung[1] + 1, allow_do=allow_do)
                if after and after[0] < 100:
                    total += hung[0] * 100 + after[0]
                    k = after[1]
                else:
                    total += hung[0] * 100
                    k = hung[1] + 1
            elif hung and hung[0] < 1000:
                total += hung[0]
                k = hung[1]
        return str(total), k
    total = value * 100
    rest = _small(tokens, k, allow_do=allow_do)
    if rest and rest[0] < 100 and tokens[k] not in _HUNDRED | _THOUSAND:
        total += rest[0]
        k = rest[1]
    return str(total), k


def digit_chunks(text: str) -> list[str]:
    """Digit groups in spoken order. 'chappan baawan' → ['56', '52']."""
    tokens = _tokens(text)
    numberish = sum(
        1
        for tok in tokens
        if tok.isdigit() or tok in _UNITS or tok in _TEENS or tok in _HUNDRED or tok in _THOUSAND
    )
    allow_do = numberish >= 2 or any(tok.isdigit() for tok in tokens)
    chunks: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        repeat = 2 if tok in _DOUBLE else 3 if tok in _TRIPLE else 0
        if repeat and i + 1 < len(tokens):
            unit = _unit(tokens[i + 1], allow_do=True)
            if unit is not None:
                chunks.append(str(unit) * repeat)
                i += 2
                continue
        compound = _compound(tokens, i, allow_do=allow_do)
        if compound is not None:
            chunks.append(compound[0])
            i = compound[1]
            continue
        if tok.isdigit() and len(tok) > 2:
            chunks.append(tok)
            i += 1
            continue
        small = _small(tokens, i, allow_do=allow_do)
        if small is None:
            i += 1
            continue
        value, nxt = small
        if value >= 10:
            chunks.append(f"{value:02d}")
        else:
            chunks.append(str(value))
        i = nxt
    return [c for c in chunks if c]


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
    return "".join(digit_chunks(_drop_repeated_phrase(text)))


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
