"""Pan-Indic phrase banks for heuristic turn recovery.

Covers interview languages in language.PROFILES (en + hi/mr/ta/te/kn/ml/bn/gu/pa/od)
with native script and common romanizations. Patterns compile once at import.
"""

from __future__ import annotations

import re


def _phrase_re(*phrases: str) -> re.Pattern[str]:
    parts = sorted({p for p in phrases if p}, key=len, reverse=True)
    return re.compile("|".join(re.escape(p) for p in parts), re.IGNORECASE)


DONT_KNOW_RE = _phrase_re(
    "don't know",
    'dont know',
    'do not know',
    'no idea',
    'not sure',
    "i don't remember",
    'never done',
    'idk',
    'dunno',
    'no clue',
    "can't say",
    'cannot say',
    'never learnt',
    'never learned',
    'not really sure',
    'i dk',
    'pata nahi',
    'pata nahin',
    'pata nai',
    'nahi pata',
    'maloom nahi',
    'malum nahi',
    'mahit nahi',
    'mahit nay',
    'mala mahit nahi',
    'mala mahit nahie',
    'samajat nahi',
    'kala nahi',
    'kalat nahi',
    'पता नहीं',
    'नहीं पता',
    'मालूम नहीं',
    'माहित नाही',
    'माहीत नाही',
    'मला माहित नाही',
    'मला माहीत नाही',
    'कळत नाही',
    'कलत नाही',
    'समजत नाही',
    'theriyadhu',
    'theriyathu',
    'theriyala',
    'தெரியாது',
    'தெரியலை',
    'தெரியல',
    'telidu',
    'teliyadu',
    'తెలియదు',
    'తెలీదు',
    'gottilla',
    'gothilla',
    'ಗೊತ್ತಿಲ್ಲ',
    'ariyilla',
    'അറിയില്ല',
    'jani na',
    'jani nai',
    'জানি না',
    'জানি নাই',
    'khabar nathi',
    'ખબર નથી',
    'ਪਤਾ ਨਹੀਂ',
    'ଜଣା ନାହିଁ',
)

REPEAT_RE = _phrase_re(
    'repeat',
    'say again',
    'once more',
    'again please',
    'pardon',
    'sorry?',
    'phir se',
    'dobara',
    'dubara',
    'punha',
    'parat sanga',
    'malli',
    'matte',
    'veendum',
    'abar',
    'farithi',
    'फिर से',
    'दोबारा',
    'दुबारा',
    'पुन्हा',
    'परत सांगा',
    'परत सांग',
    'மறுபடி',
    'மீண்டும்',
    'திரும்ப',
    'మళ్ళీ',
    'మళ్లీ',
    'ಮತ್ತೆ',
    'ಮತ್ತೊಮ್ಮೆ',
    'വീണ്ടും',
    'আবার বলুন',
    'আবার বলো',
    'ફરીથી',
    'ફરી કહો',
    'ਫਿਰ ਤੋਂ',
    'ਦੁਬਾਰਾ',
    'ପୁଣି',
    'ଆଉଥରେ',
)

REPHRASE_RE = _phrase_re(
    "don't understand",
    "didn't understand",
    'not understand',
    'what do you mean',
    'samajh nahi',
    'samaj nahi',
    'samajla nahi',
    'puriyala',
    'artham kaledu',
    'arthavagalilla',
    'manasilayilla',
    'समझ नहीं आया',
    'समझ नहीं आ',
    'समजलं नाही',
    'समजले नाही',
    'புரியவில்லை',
    'புரியல',
    'అర్థం కాలేదు',
    'ಅರ್ಥವಾಗಲಿಲ್ಲ',
    'മനസ്സിലായില്ല',
    'বুঝতে পারিনি',
    'বুঝলাম না',
    'સમજાયું નહીં',
    'ਸਮਝ ਨਹੀਂ ਆਇਆ',
    'ବୁଝିପାରିଲି ନାହିଁ',
)

STOP_RE = _phrase_re(
    'want to stop',
    'wanna stop',
    'i want to stop',
    'stop the interview',
    'end the interview',
    'end this',
    'leave now',
    'i quit',
    "i'm done",
    'im done',
    "don't want to continue",
    'do not want to continue',
    'not continue',
    'band karo',
    'band kar',
    'chhodna',
    'chhod do',
    'रोक दो',
    'बंद करो',
    'बंद कर',
    'छोड़ना',
    'छोड़ दो',
    'इंटरव्यू बंद',
    'नहीं करना है इंटरव्यू',
    'थांबवा',
    'बंद करा',
    'सोडून द्या',
    'நிறுத்து',
    'நிறுத்துங்க',
    'விட்டுடு',
    'ఆపు',
    'ఆపేయ్',
    'ఆపండి',
    'ನಿಲ್ಲಿಸಿ',
    'ಬಿಡಿ',
    'നിര്ത്ത്',
    'നിര്ത്തണം',
    'বন্ধ করো',
    'থামো',
    'બંધ કરો',
    'રોકો',
    'ਬੰਦ ਕਰੋ',
    'ਰੋਕੋ',
    'ବନ୍ଦ କର',
    'ରୋକ',
)

REFUSAL_RE = _phrase_re(
    "won't answer",
    'will not answer',
    "i won't tell",
    'i will not tell',
    'not telling',
    "don't want to say",
    'do not want to say',
    'prefer not to say',
    'refuse to answer',
    'नहीं बताऊंगा',
    'नहीं बताऊँगा',
    'नहीं बताउंगी',
    'नहीं बताऊँगी',
    'नहीं बताना',
    'सांगायचं नाही',
    'सांगणार नाही',
    'சொல்ல மாட்டேன்',
    'சொல்லவே மாட்டேன்',
    'చెప్పను',
    'చెప్పడం లేదు',
    'ಹೇಳುವುದಿಲ್ಲ',
    'ಹೇಳಲ್ಲ',
    'പറയില്ല',
    'പറയാൻ ഇഷ്ടമില്ല',
    'বলব না',
    'বলবো না',
    'বলতে চাই না',
    'કહીશ નહીં',
    'કહેવું નથી',
    'ਨਹੀਂ ਦੱਸਾਂਗਾ',
    'ਨਹੀਂ ਦੱਸਾਂਗੀ',
    'ਦੱਸਣਾ ਨਹੀਂ',
    'କହିବି ନାହିଁ',
)

OFF_TOPIC_RE = _phrase_re(
    'what is the weather',
    'tell me a joke',
    'who is the prime minister',
    'क्रिकेट',
    'फिल्म',
    'मौसम',
    'கிரிக்கெட்',
    'சினிமா',
    'வானிலை',
    'క్రికెట్',
    'సినిమా',
    'ಕ್ರಿಕೆಟ್',
    'ಸಿನಿಮಾ',
    'ക്രിക്കട്ട്',
    'സിനിമ',
    'ক্রিকেট',
    'সিনেমা',
    'আবহাওয়া',
    'ક્રિકેટ',
    'ફિલ્મ',
    'ਕ੍ਰਿਕਟ',
    'ਫਿਲਮ',
    'କ୍ରିକେଟ',
    'ଛ଼ିଲ୍ମ',
)

FILLER_ONLY: frozenset[str] = frozenset({'hmm', 'hm', 'um', 'uh', 'umm', 'uhh', 'ok', 'okay', 'haan', 'han', 'ji', 'huh', 'ah', 'aa', 'aama', 'ama', 'avunu', 'howdu', 'athe', 'hyan', 'hya', 'ho', 'ha', 'हाँ', 'हां', 'जी', 'हं', 'हा', 'हो', 'ठीक', 'ஆமா', 'ஆம்', 'சரி', 'అవును', 'సరే', 'ఆ', 'ಹೌದು', 'ಹಾ', 'ಸರಿ', 'അതെ', 'ശരി', 'হ্যাঁ', 'হ্যা', 'জি', 'ঠিক', 'હા', 'હાં', 'જી', 'ਹਾਂ', 'ਜੀ', 'ହଁ', 'ହଂ'})

CONFIRM_YES_RE = re.compile(
    r"(?:"
    r"\b(?:yes|yeah|correct|right|haan|han|sahi|ho|aama|avunu|howdu|athe)\b"
    r"|हाँ|हां|जी\b|बरोबर|सही|होय|ठीक"
    r"|ஆமா|ஆம்|சரி|சரிதான்"
    r"|అవును|సరే|ఒప్పు"
    r"|ಹೌದು|ಸರಿ|ಸರಿಯಾಗಿದೆ"
    r"|അതെ|ശരി|ശരിയാണ്"
    r"|হ্যাঁ|হ্যা|জি|ঠিক|সঠিক"
    r"|હા|હાં|જી|બરાબર|સાચું"
    r"|ਹਾਂ|ਜੀ|ਸਹੀ|ਠੀਕ"
    r"|ହଁ|ଠିକ୍|ସଠିକ୍"
    r")",
    re.IGNORECASE,
)

CONFIRM_NO_RE = re.compile(
    r"(?:"
    r"\b(?:no|nahi|nope|wrong|galat|illa|ledu|alla|nai)\b"
    r"|नहीं|गलत|नाही|चूक|नको"
    r"|இல்ல|தவறு|வேண்டாம்"
    r"|లేదు|తప్పు|కాదు"
    r"|ಇಲ್ಲ|ತಪ್ಪು"
    r"|ഇല്ല|തെറ്റ്"
    r"|না|ভুল"
    r"|ના|નહીં|ખોટું"
    r"|ਨਹੀਂ|ਗਲਤ|ਨਾ"
    r"|ନା|ଭୁଲ"
    r")",
    re.IGNORECASE,
)

CARE_YES_RE = re.compile(
    r"(?:"
    r"\b(?:yes|yeah|yep|sure|ready|okay|ok|haan|han|ho|aama|avunu|howdu|athe|"
    r"will(?:\s+do)?|can\s+do|i'?ll\s+do)\b"
    r"|हाँ|हां|हा\b|जी\b|हो\b|तयार|ठीक\s*है|बरोबर|होय"
    r"|कर\s*(?:सकता|सकती|सकते|लूँगा|लूंगी|लेंगे|लेगा|लेगी)"
    r"|करु?\s*शकत"
    r"|सीख\s*(?:लूँगा|लूंगी|लेंगे)|learn"
    r"|ஆமா|ஆம்|சரி|தயார|செய்வேன்|பண்ணுவேன்"
    r"|అవును|సరే|సిద్ధం|చేస్తాను"
    r"|ಹೌದು|ಸರಿ|ಸಿದ್ಧ|ಮಾಡುತ್ತೇನೆ"
    r"|അതെ|ശരി|തയ്യാർ|ചെയ്യാം"
    r"|হ্যাঁ|হ্যা|জি|ঠিক\s*আছে|প্রস্তুত|করব"
    r"|હા|હાં|જી|બરાબર|તૈયાર"
    r"|ਹਾਂ|ਜੀ|ਠੀਕ|ਤਿਆਰ"
    r"|ହଁ|ଠିକ୍|ପ୍ରସ୍ତୁତ"
    r")",
    re.IGNORECASE,
)

CARE_NO_RE = re.compile(
    r"(?:"
    # Avoid bare nahi/नहीं — those collide with don't-know ("pata nahi").
    r"\b(?:nope|won'?t|refuse|not\s+willing)\b"
    r"|(?:^|\s)(?:no|nahi|illa|ledu|alla|venda|nai)(?:\s|$|[.,!?])"
    r"|नहीं\s*कर|नाही\s*कर|कर\s*नहीं|कर\s*नाही|नको\b|मना\b"
    r"|(?:^|[\s,])(?:नहीं|नाही)(?:$|[\s.,!?])"
    r"|अन्य\s*काम|other\s+(?:things|duties|work)|बाकी\s*काम"
    r"|\bi\s+can'?t\b|\bcannot\b|\bi\s+won'?t\b"
    r"|முடியாது|வேண்டாம்|மாட்டேன்"
    r"|(?:^|[\s,])(?:இல்ல|లేదు|ಇಲ್ಲ|ഇല്ല|না|ના|નહીં|ਨਹੀਂ|ਨਾ|ନା)(?:$|[\s.,!?])"
    r"|వద్దు|చేయను"
    r"|ಬೇಡ|ಮಾಡುವುದಿಲ್ಲ"
    r"|വേണ്ട|ചെയ്യില്ല"
    r"|পারব\s*না|করব\s*না"
    r"|કરીશ\s*નહીં"
    r"|ਨਹੀਂ\s*ਕਰਾਂਗਾ"
    r"|କରିବି\s*ନାହିଁ"
    r")",
    re.IGNORECASE,
)
