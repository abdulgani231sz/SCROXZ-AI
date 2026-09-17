"""Shared language choices for model replies, microphone and speech output."""
import re

REPLY_LANGUAGES = {
    'auto': 'Auto / match me',
    'hi': 'Hindi / हिंदी',
    'hinglish': 'Hinglish / हिंदी + English',
    'en': 'English',
}
INSTRUCTIONS = {
    'auto': "Match the user's language. For Roman Hindi/Hinglish input, answer in natural Hinglish with Hindi words in Devanagari and English terms in Latin script.",
    'hi': 'उत्तर हिंदी में दें। हिंदी शब्द देवनागरी लिपि में लिखें। सवाल अंग्रेज़ी में हो तब भी जवाब हिंदी में दें। Reply in Hindi, not English. Keep code, names and necessary technical terms unchanged.',
    'hinglish': 'जवाब हिंदी और English मिलाकर दें। हिंदी शब्द देवनागरी में, English technical terms Latin script में लिखें। सवाल English में हो तब भी पूरा जवाब English में मत दें। Example: Computer memory में data store होता है। RAM temporary memory है। Reply in this mixed Hindi-English style.',
    'en': 'Reply in English. Keep the explanation natural and clear.',
}


def language_instruction(config):
    return INSTRUCTIONS[config.get('reply_language', 'hinglish')] + ' Prefer short, speakable sentences. Do not announce the language setting.'


def speech_language(language, text):
    if language in ('hi', 'hinglish'):
        return 'hi'
    if language == 'en':
        return 'en'
    return 'hi' if re.search(r'[\u0900-\u097f]', text) else 'en'


def microphone_language(language):
    # Whisper has no separate Hinglish language code; auto supports code switching.
    return 'auto' if language == 'hinglish' else language
