"""Pre-approved spoken lines for first-time screening asks, so those turns skip the voice LLM.

Flow still decides what is asked; these are only the words. Every supported join-screen language has
lines. A leading ack word (अच्छा / ठीक आहे / சரி ...) is one the TTS filter strips when a reaction
already played, so the pair never sounds like "ok, ok... ok, so". Lines use no gendered verb forms.
Clinical names stay in Latin letters, as the language rules require.
"""

from __future__ import annotations

import zlib

EDU = "education"  # qualification + year asked together
YEAR = "year"  # qualification year alone
BODY = "body"  # height + weight
EXP = "experience"  # total years + where they worked

_KEYS: dict[frozenset[str], str] = {
    frozenset({"qualification", "qualification_year"}): EDU,
    frozenset({"qualification_year"}): YEAR,
    frozenset({"height_cm", "weight_kg"}): BODY,
    frozenset({"experience_years", "experience_settings"}): EXP,
}

LINES: dict[str, dict[str, tuple[str, ...]]] = {
    "hi-IN": {
        EDU: (
            "अच्छा, तो आपकी nursing qualification क्या है, और आपने वो किस साल में पूरी की?",
            "अच्छा, आपने nursing में कौन सा course किया है, GNM, ANM या B.Sc Nursing, और किस साल पास किया?",
        ),
        YEAR: ("और ये आपने किस साल में पास किया?",),
        BODY: (
            "अच्छा, profile form के लिए, आपकी height और weight कितना है?",
            "अच्छा, बस profile form के लिए, अपनी height और weight बता दीजिए, feet या centimetre, दोनों चलेगा।",
        ),
        EXP: (
            "अच्छा, आपको nursing में कितने साल का experience है, और आपने कहाँ काम किया है?",
            "अच्छा, अब अपने काम के बारे में बताइए, कितने साल का experience है, और किस hospital या ward में काम किया?",
        ),
    },
    "en-IN": {
        EDU: (
            "Okay, what is your nursing qualification, and which year did you complete it?",
            "Okay, which nursing course did you do, GNM, ANM or B.Sc Nursing, and which year did you pass?",
        ),
        YEAR: ("And which year did you pass that?",),
        BODY: (
            "Okay, just for the profile form, what is your height and weight?",
            "Okay, for the profile form, may I know your height and weight? Feet or centimetres are both fine.",
        ),
        EXP: (
            "Okay, how many years of nursing experience do you have, and where have you worked?",
            "Okay, tell me about your work so far, how many years, and in which hospital or ward?",
        ),
    },
    "mr-IN": {
        EDU: ("ठीक आहे, तुमचं nursing चं शिक्षण काय आहे, आणि ते कोणत्या वर्षी पूर्ण केलं?",),
        YEAR: ("आणि ते कोणत्या वर्षी पास झालात?",),
        BODY: ("ठीक आहे, profile form साठी, तुमची उंची आणि वजन किती आहे?",),
        EXP: ("ठीक आहे, तुम्हाला nursing मध्ये किती वर्षांचा अनुभव आहे, आणि तुम्ही कुठे काम केलं आहे?",),
    },
    "gu-IN": {
        EDU: ("સારું, તમારું nursing નું શિક્ષણ શું છે, અને તે કયા વર્ષમાં પૂરું કર્યું?",),
        YEAR: ("અને તે કયા વર્ષમાં પાસ કર્યું?",),
        BODY: ("સારું, profile form માટે, તમારી ઊંચાઈ અને વજન કેટલું છે?",),
        EXP: ("સારું, તમને nursing માં કેટલા વર્ષનો અનુભવ છે, અને તમે ક્યાં કામ કર્યું છે?",),
    },
    "ta-IN": {
        EDU: ("சரி, உங்க nursing படிப்பு என்ன, அதை எந்த வருஷம் முடிச்சீங்க?",),
        YEAR: ("அதை எந்த வருஷம் முடிச்சீங்க?",),
        BODY: ("சரி, profile form-க்காக, உங்க உயரம் மற்றும் எடை எவ்வளவு?",),
        EXP: ("சரி, nursing-ல உங்களுக்கு எத்தனை வருஷம் அனுபவம் இருக்கு, எங்கெல்லாம் வேலை செஞ்சிருக்கீங்க?",),
    },
    "te-IN": {
        EDU: ("సరే, మీ nursing చదువు ఏమిటి, అది ఏ సంవత్సరంలో పూర్తి చేశారు?",),
        YEAR: ("అది ఏ సంవత్సరంలో పూర్తి చేశారు?",),
        BODY: ("సరే, profile form కోసం, మీ ఎత్తు మరియు బరువు ఎంత?",),
        EXP: ("సరే, nursing లో మీకు ఎన్ని సంవత్సరాల అనుభవం ఉంది, ఎక్కడ పని చేశారు?",),
    },
    "kn-IN": {
        EDU: ("ಸರಿ, ನಿಮ್ಮ nursing ವಿದ್ಯಾರ್ಹತೆ ಏನು, ಅದನ್ನು ಯಾವ ವರ್ಷ ಪೂರ್ಣಗೊಳಿಸಿದಿರಿ?",),
        YEAR: ("ಅದನ್ನು ಯಾವ ವರ್ಷ ಪೂರ್ಣಗೊಳಿಸಿದಿರಿ?",),
        BODY: ("ಸರಿ, profile form ಗಾಗಿ, ನಿಮ್ಮ ಎತ್ತರ ಮತ್ತು ತೂಕ ಎಷ್ಟು?",),
        EXP: ("ಸರಿ, nursing ನಲ್ಲಿ ನಿಮಗೆ ಎಷ್ಟು ವರ್ಷದ ಅನುಭವ ಇದೆ, ಎಲ್ಲಿ ಕೆಲಸ ಮಾಡಿದ್ದೀರಿ?",),
    },
    "ml-IN": {
        EDU: ("ശരി, നിങ്ങളുടെ nursing യോഗ്യത എന്താണ്, അത് ഏത് വർഷമാണ് പൂർത്തിയാക്കിയത്?",),
        YEAR: ("അത് ഏത് വർഷമാണ് പൂർത്തിയാക്കിയത്?",),
        BODY: ("ശരി, profile form-നു വേണ്ടി, നിങ്ങളുടെ ഉയരവും ഭാരവും എത്രയാണ്?",),
        EXP: ("ശരി, nursing-ൽ നിങ്ങൾക്ക് എത്ര വർഷത്തെ പരിചയമുണ്ട്, എവിടെയാണ് ജോലി ചെയ്തത്?",),
    },
    "bn-IN": {
        EDU: ("আচ্ছা, আপনার nursing যোগ্যতা কী, আর সেটা কোন বছরে শেষ করেছেন?",),
        YEAR: ("সেটা কোন বছরে শেষ করেছেন?",),
        BODY: ("আচ্ছা, profile form-এর জন্য, আপনার উচ্চতা আর ওজন কত?",),
        EXP: ("আচ্ছা, nursing-এ আপনার কত বছরের অভিজ্ঞতা, আর কোথায় কাজ করেছেন?",),
    },
    "pa-IN": {
        EDU: ("ਠੀਕ ਹੈ, ਤੁਹਾਡੀ nursing ਦੀ ਪੜ੍ਹਾਈ ਕੀ ਹੈ, ਤੇ ਇਹ ਕਿਸ ਸਾਲ ਪੂਰੀ ਕੀਤੀ?",),
        YEAR: ("ਤੇ ਇਹ ਕਿਸ ਸਾਲ ਪੂਰੀ ਕੀਤੀ?",),
        BODY: ("ਠੀਕ ਹੈ, profile form ਲਈ, ਤੁਹਾਡਾ ਕੱਦ ਤੇ ਭਾਰ ਕਿੰਨਾ ਹੈ?",),
        EXP: ("ਠੀਕ ਹੈ, nursing ਵਿੱਚ ਤੁਹਾਨੂੰ ਕਿੰਨੇ ਸਾਲ ਦਾ ਤਜਰਬਾ ਹੈ, ਤੇ ਕਿੱਥੇ ਕੰਮ ਕੀਤਾ ਹੈ?",),
    },
    "od-IN": {
        EDU: ("ଆଚ୍ଛା, ଆପଣଙ୍କ nursing ଯୋଗ୍ୟତା କଣ, ଏବଂ ତାହା କେଉଁ ବର୍ଷ ସମ୍ପୂର୍ଣ୍ଣ କରିଥିଲେ?",),
        YEAR: ("ତାହା କେଉଁ ବର୍ଷ ସମ୍ପୂର୍ଣ୍ଣ କରିଥିଲେ?",),
        BODY: ("ଆଚ୍ଛା, profile form ପାଇଁ, ଆପଣଙ୍କ ଉଚ୍ଚତା ଓ ଓଜନ କେତେ?",),
        EXP: ("ଆଚ୍ଛା, nursing ରେ ଆପଣଙ୍କର କେତେ ବର୍ଷର ଅନୁଭବ ଅଛି, ଏବଂ କେଉଁଠି କାମ କରିଛନ୍ତି?",),
    },
}


def screening_ask_line(field_ids: list[str] | tuple[str, ...], language: str, interview_id: str) -> str | None:
    """Fixed line for this ask, or None when the voice LLM should word it."""
    key = _KEYS.get(frozenset(str(f) for f in field_ids))
    options = LINES.get(language, {}).get(key or "")
    if not options:
        return None
    # Stable per interview and ask, so a rejoin hears the same wording; varies across candidates.
    seed = f"{interview_id}:{','.join(sorted(field_ids))}".encode()
    return options[zlib.crc32(seed) % len(options)]
