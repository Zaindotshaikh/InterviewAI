"""Deterministic pre-TTS output guard (Phase 2 P2-08).

Intercepts assistant text before TTS synthesis. Drops or replaces unauthorized figures
(salary/CTC/amounts), selection or job offer promises, redundant slot asks, and enforces
single-question limit on probe/screening moves.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("interview-v2.output_guard")

# 1. Salary / compensation figures: currency symbol, lakh, CTC, salary words near numbers
_SALARY_PATTERNS = [
    re.compile(r"(?:₹|rs\.?|inr|rupees?|रुपये|पगार|वेतन|सैलरी)\s*\d+", re.I),
    re.compile(r"\b\d+\s*(?:lakh|lac|k|thousand|per\s*month|प्रति\s*माह|महीना|लाख|हजार)\b", re.I),
    re.compile(r"\b(?:ctc|package|salary|stipend)\s*(?:is|of|around|upto|up\s*to)?\s*[:\s]?\s*(?:₹|rs\.?|inr)?\s*\d+", re.I),
    re.compile(r"\b\d+\s*(?:to|-)\s*\d+\s*(?:lakh|lac|k|thousand|rupees?|rs)\b", re.I),
]

# 2. Offer / selection commitments
_OFFER_PATTERNS = [
    re.compile(r"\b(?:you\s*(?:are|have\s*been)\s*(?:selected|hired)|congratulations,?.*selected)\b", re.I),
    re.compile(r"\b(?:job\s*offer|we\s*will\s*offer\s*you|confirm\s*ho\s*gaya|selection\s*ho\s*gaya)\b", re.I),
    re.compile(r"\b(?:aapka\s*selection|aap\s*select\s*ho\s*gaye|selection\s*pakka)\b", re.I),
    re.compile(r"(?:पक्का\s*सिलेक्शन|सिलेक्शन\s*पक्का|आपका\s*सिलेक्शन|हम\s*नौकरी\s*दे\s*रहे\s*हैं|सिलेक्शन\s*हो\s*गया|नोकरी\s*मिळाली|निवड\s*झाली)"),
    re.compile(r"\b(?:you\s*got\s*the\s*job|we\s*are\s*hiring\s*you)\b", re.I),
]

# 3. Redundant slot asks patterns
_SLOT_PATTERNS = {
    "city": re.compile(
        r"\b(?:which\s*city|what\s*city|where\s*(?:do|are)\s*you\s*(?:live|stay|located)|"
        r"कौनसे\s*शहर|किस\s*शहर|कहाँ\s*रहते|कोणत्या\s*शहरात|કયા\s*શહેરમાં)\b",
        re.I,
    ),
    "phone": re.compile(
        r"\b(?:your\s*(?:mobile|phone)|contact\s*number|phone\s*number|"
        r"फोन\s*नंबर|मोबाइल\s*नंबर|मोबाईल\s*नंबर|नंबर\s*बताइए)\b",
        re.I,
    ),
    "qualification": re.compile(
        r"\b(?:what\s*(?:is|are)\s*your\s*qualification|what\s*did\s*you\s*study|which\s*degree|nursing\s*qualification|"
        r"आपकी\s*क्वालिफिकेशन|क्या\s*पढ़ाई|कौनसी\s*डिग्री|शिक्षण\s*काय)\b",
        re.I,
    ),
    "experience_years": re.compile(
        r"\b(?:how\s*many\s*years\s*of\s*experience|total\s*experience|years\s*in\s*nursing|"
        r"कितने\s*साल\s*का\s*अनुभव|कुल\s*अनुभव|किती\s*वर्षांचा\s*अनुभव)\b",
        re.I,
    ),
}

# Replacement templates by language
_SAFE_SALARY_REPLACEMENTS = {
    "hi-IN": "वेतन और पैकेज की जानकारी रिक्रूटमेंट टीम द्वारा सीधे साझा की जाएगी।",
    "mr-IN": "पगार आणि पॅकेजची माहिती रिक्रूटमेंट टीम थेट देईल.",
    "gu-IN": "પગાર અને પેકેજની વિગતો રિક્રૂટમેન્ટ ટીમ સીધી આપશે.",
    "te-IN": "జీతం మరియు ప్యాకేజీ వివరాలను రిక్రూట్‌మెంట్ బృందం నేరుగా పంచుకుంటుంది.",
    "ta-IN": "சம்பளம் மற்றும் பேக்கேஜ் விவரங்கள் ஆட்சேர்ப்பு குழுவால் நேரடியாக பகிரப்படும்.",
    "kn-IN": "ವೇತನ ಮತ್ತು ಪ್ಯಾಕೇಜ್ ವಿವರಗಳನ್ನು ನೇಮಕಾತಿ ತಂಡವು ನೇರವಾಗಿ ಹಂಚಿಕೊಳ್ಳುತ್ತದೆ.",
    "ml-IN": "ശമ്പളത്തിന്റെയും പാക്കേജിന്റെയും വിവരങ്ങൾ റിക്രൂട്ട്‌മെന്റ് ടീം നേരിട്ട് പങ്കിടും.",
    "bn-IN": "বেতন এবং প্যাকেজের বিবরণ রিক্রুটমেন্ট টিম সরাসরি জানাবে।",
    "pa-IN": "ਤਨਖਾਹ ਅਤੇ ਪੈਕੇਜ ਦੇ ਵੇਰਵੇ ਭਰਤੀ ਟੀਮ ਦੁਆਰਾ ਸਿੱਧੇ ਸਾਂਝੇ ਕੀਤੇ ਜਾਣਗੇ।",
    "od-IN": "ଦରମା ଏବଂ ପ୍ୟାକେଜ୍ ବିବରଣୀ ନିଯୁକ୍ତି ଦଳ ସିଧାସଳଖ ଜଣାଇବ।",
    "en-IN": "Salary and package details will be shared directly by the recruitment team.",
}

_SAFE_OFFER_REPLACEMENTS = {
    "hi-IN": "साक्षात्कार के परिणाम की समीक्षा के बाद रिक्रूटमेंट टीम आपको सूचित करेगी।",
    "mr-IN": "मुलाखतीचे निकाल तपासून रिक्रूटमेंट टीम तुम्हाला कळवेल.",
    "gu-IN": "ઇન્ટરવ્યુની સમીક્ષા પછી રિક્રૂટમેન્ટ ટીમ તમને જાણ કરશે.",
    "te-IN": "ఇంటర్వ్యూ ఫలితాలను సమీక్షించిన తర్వాత రిక్రూట్‌మెంట్ బృందం మీకు తెలియజేస్తుంది.",
    "ta-IN": "நேர்காணல் முடிவுகளை மதிப்பாய்வு செய்த பிறகு ஆட்சேர்ப்பு குழு உங்களுக்குத் தெரிவிக்கும்.",
    "kn-IN": "ಸಂದರ್ಶನದ ಫಲಿತಾಂಶಗಳನ್ನು ಪರಿಶೀಲಿಸಿದ ನಂತರ ನೇಮಕಾತಿ ತಂಡವು ನಿಮಗೆ ತಿಳಿಸುತ್ತದೆ.",
    "ml-IN": "അഭിമുഖ ഫലങ്ങൾ പരിശോധിച്ച ശേഷം റിക്രൂട്ട്‌മെന്റ് ടീം നിങ്ങളെ അറിയിക്കും.",
    "bn-IN": "সাক্ষাৎকারের ফলাফল পর্যালোচনার পর রিক্রুটমেন্ট টিম আপনাকে জানাবে।",
    "pa-IN": "ਇੰਟਰਵਿਊ ਦੇ ਨਤੀਜਿਆਂ ਦੀ ਸਮੀਖਿਆ ਤੋਂ ਬਾਅਦ ਭਰਤੀ ਟੀਮ ਤੁਹਾਨੂੰ ਸੂਚਿਤ ਕਰੇਗੀ।",
    "od-IN": "ସାକ୍ଷାତକାର ଫଳାଫଳ ସମୀକ୍ଷା ପରେ ନିଯୁକ୍ତି ଦଳ ଆପଣଙ୍କୁ ଜଣାଇବ।",
    "en-IN": "The recruitment team will follow up with you after reviewing the interview results.",
}

_SAFE_TRANSITION_REPLACEMENTS = {
    "hi-IN": "आइए अगले प्रश्न पर आगे बढ़ते हैं।",
    "mr-IN": "आपण पुढच्या प्रश्नावर जाऊया.",
    "gu-IN": "ચાલો આપણે આગળના પ્રશ્ન પર આગળ વધીએ.",
    "te-IN": "మనం తర్వాతి ప్రశ్నకు కొనసాగుదాం.",
    "ta-IN": "நாம் அடுத்த கேள்விக்கு செல்லலாம்.",
    "kn-IN": "ನಾವು ಮುಂದಿನ ಪ್ರಶ್ನೆಗೆ ಮುಂದುವರಿಯೋಣ.",
    "ml-IN": "നമുക്ക് അടുത്ത ചോദ്യത്തിലേക്ക് കടക്കാം.",
    "bn-IN": "আসুন পরবর্তী প্রশ্নে এগিয়ে যাই।",
    "pa-IN": "ਆਓ ਅਗਲੇ ਸਵਾਲ 'ਤੇ ਅੱਗੇ ਵਧੀਏ।",
    "od-IN": "ଆସନ୍ତୁ ପରବର୍ତ୍ତୀ ପ୍ରଶ୍ନକୁ ଆଗକୁ ବଢିବା।",
    "en-IN": "Let us continue to the next question.",
}


class OutputGuard:
    """Non-model deterministic filter scanning outbound assistant text before TTS."""

    def __init__(self) -> None:
        pass

    def inspect_text(
        self,
        text: str,
        *,
        language: str = "hi-IN",
        captured_slots: set[str] | None = None,
        single_question: bool = True,
        fallback_text: str = "",
    ) -> tuple[bool, str, str]:
        """Inspect text before TTS.

        Returns:
            (is_blocked, resulting_text, reason)
        """
        raw = text.strip()
        if not raw:
            return False, text, ""

        # Check 1: Salary or compensation leaks
        for pat in _SALARY_PATTERNS:
            if pat.search(raw):
                lang = language if language in _SAFE_SALARY_REPLACEMENTS else "en-IN"
                safe = _SAFE_SALARY_REPLACEMENTS[lang]
                logger.warning("guard.blocked class=salary_leak")
                return True, safe, "salary_leak"

        # Check 2: Selection / hiring promises
        for pat in _OFFER_PATTERNS:
            if pat.search(raw):
                lang = language if language in _SAFE_OFFER_REPLACEMENTS else "en-IN"
                safe = _SAFE_OFFER_REPLACEMENTS[lang]
                logger.warning("guard.blocked class=offer_leak")
                return True, safe, "offer_leak"

        # Check 3: Redundant slot ask
        if captured_slots:
            for slot_name, pat in _SLOT_PATTERNS.items():
                if slot_name in captured_slots and pat.search(raw):
                    logger.warning("guard.blocked class=redundant_slot slot=%s", slot_name)
                    lang = language if language in _SAFE_TRANSITION_REPLACEMENTS else "en-IN"
                    safe = fallback_text.strip() or _SAFE_TRANSITION_REPLACEMENTS[lang]
                    return True, safe, f"redundant_slot_{slot_name}"

        # Check 4: Enforce single question when requested
        if single_question:
            q_count = raw.count("?")
            if q_count > 1:
                first_q_end = raw.find("?")
                truncated = raw[: first_q_end + 1].strip()
                logger.warning("guard.blocked class=multiple_questions count=%d", q_count)
                return True, truncated, "multiple_questions"

        return False, text, ""
