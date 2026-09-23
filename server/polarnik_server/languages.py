"""Target languages of the voice-over and how each engine / translator refers to them.

The extension picks a target language (by default the user's system language, Polish when
that is Polish); the server translates the captions into it and synthesizes with a voice of
that language. Keys are BCP-47-ish base codes used everywhere in the API ("pl", "en", "zh",
"yue"). Engines map them to their own ids through the per-language fields below.
"""

from __future__ import annotations

from typing import Any

# code -> name (English), native name, YouTube tlang, DeepL target, XTTS-v2 language,
#         Chatterbox language_id, Edge neural voices [(id, label)], Piper voices [(id, label, MB)]
LANGUAGES: dict[str, dict[str, Any]] = {
    "pl": {"name": "Polish", "native": "polski", "youtube": "pl", "deepl": "PL", "xtts": "pl", "chatterbox": "pl",
           "edge": [("pl-PL-ZofiaNeural", "Zofia (female)"), ("pl-PL-MarekNeural", "Marek (male)")],
           "piper": [("pl_PL-gosia-medium", "Gosia (female, medium)", 63), ("pl_PL-darkman-medium", "Darkman (male, medium)", 63),
                     ("pl_PL-mc_speech-medium", "MC Speech (male, medium)", 63)]},
    "en": {"name": "English", "native": "English", "youtube": "en", "deepl": "EN-US", "xtts": "en", "chatterbox": "en",
           "edge": [("en-US-AriaNeural", "Aria (female, US)"), ("en-US-GuyNeural", "Guy (male, US)"),
                    ("en-GB-SoniaNeural", "Sonia (female, UK)"), ("en-GB-RyanNeural", "Ryan (male, UK)")],
           "piper": [("en_US-lessac-medium", "Lessac (female, medium)", 63), ("en_US-amy-medium", "Amy (female, medium)", 63),
                     ("en_GB-alan-medium", "Alan (male, UK, medium)", 63)]},
    "zh": {"name": "Chinese (Mandarin)", "native": "中文（普通话）", "youtube": "zh-Hans", "deepl": "ZH", "xtts": "zh-cn", "chatterbox": "zh",
           "edge": [("zh-CN-XiaoxiaoNeural", "Xiaoxiao (female)"), ("zh-CN-YunxiNeural", "Yunxi (male)")],
           "piper": [("zh_CN-huayan-medium", "Huayan (female, medium)", 63)]},
    "yue": {"name": "Chinese (Cantonese)", "native": "粵語", "youtube": "zh-Hant", "deepl": "ZH-HANT", "xtts": None, "chatterbox": None,
            "edge": [("zh-HK-HiuGaaiNeural", "HiuGaai (female)"), ("zh-HK-WanLungNeural", "WanLung (male)")], "piper": []},
    "hi": {"name": "Hindi", "native": "हिन्दी", "youtube": "hi", "deepl": None, "xtts": "hi", "chatterbox": "hi",
           "edge": [("hi-IN-SwaraNeural", "Swara (female)"), ("hi-IN-MadhurNeural", "Madhur (male)")],
           "piper": [("hi_IN-pratham-medium", "Pratham (male, medium)", 63), ("hi_IN-priyamvada-medium", "Priyamvada (female, medium)", 63)]},
    "es": {"name": "Spanish", "native": "español", "youtube": "es", "deepl": "ES", "xtts": "es", "chatterbox": "es",
           "edge": [("es-ES-ElviraNeural", "Elvira (female, Spain)"), ("es-ES-AlvaroNeural", "Álvaro (male, Spain)"),
                    ("es-MX-DaliaNeural", "Dalia (female, Mexico)"), ("es-MX-JorgeNeural", "Jorge (male, Mexico)")],
           "piper": [("es_ES-sharvard-medium", "Sharvard (male, Spain, medium)", 63), ("es_MX-claude-high", "Claude (male, Mexico, high)", 115)]},
    "fr": {"name": "French", "native": "français", "youtube": "fr", "deepl": "FR", "xtts": "fr", "chatterbox": "fr",
           "edge": [("fr-FR-DeniseNeural", "Denise (female)"), ("fr-FR-HenriNeural", "Henri (male)")],
           "piper": [("fr_FR-siwis-medium", "Siwis (female, medium)", 63), ("fr_FR-upmc-medium", "UPMC (medium)", 63)]},
    "ar": {"name": "Arabic", "native": "العربية", "youtube": "ar", "deepl": "AR", "xtts": "ar", "chatterbox": "ar",
           "edge": [("ar-SA-ZariyahNeural", "Zariyah (female)"), ("ar-SA-HamedNeural", "Hamed (male)"),
                    ("ar-EG-SalmaNeural", "Salma (female, Egypt)")],
           "piper": [("ar_JO-kareem-medium", "Kareem (male, medium)", 63)]},
    "bn": {"name": "Bengali", "native": "বাংলা", "youtube": "bn", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("bn-BD-NabanitaNeural", "Nabanita (female)"), ("bn-BD-PradeepNeural", "Pradeep (male)"),
                    ("bn-IN-TanishaaNeural", "Tanishaa (female, India)")], "piper": []},
    "pt": {"name": "Portuguese", "native": "português", "youtube": "pt", "deepl": "PT-BR", "xtts": "pt", "chatterbox": "pt",
           "edge": [("pt-BR-FranciscaNeural", "Francisca (female, Brazil)"), ("pt-BR-AntonioNeural", "Antônio (male, Brazil)"),
                    ("pt-PT-RaquelNeural", "Raquel (female, Portugal)"), ("pt-PT-DuarteNeural", "Duarte (male, Portugal)")],
           "piper": [("pt_BR-faber-medium", "Faber (male, Brazil, medium)", 63), ("pt_PT-tugao-medium", "Tugão (male, Portugal, medium)", 63)]},
    "ru": {"name": "Russian", "native": "русский", "youtube": "ru", "deepl": "RU", "xtts": "ru", "chatterbox": "ru",
           "edge": [("ru-RU-SvetlanaNeural", "Svetlana (female)"), ("ru-RU-DmitryNeural", "Dmitry (male)")],
           "piper": [("ru_RU-irina-medium", "Irina (female, medium)", 63), ("ru_RU-dmitri-medium", "Dmitri (male, medium)", 63)]},
    "ur": {"name": "Urdu", "native": "اردو", "youtube": "ur", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("ur-PK-UzmaNeural", "Uzma (female)"), ("ur-PK-AsadNeural", "Asad (male)")], "piper": []},
    "id": {"name": "Indonesian", "native": "Bahasa Indonesia", "youtube": "id", "deepl": "ID", "xtts": None, "chatterbox": None,
           "edge": [("id-ID-GadisNeural", "Gadis (female)"), ("id-ID-ArdiNeural", "Ardi (male)")], "piper": []},
    "de": {"name": "German", "native": "Deutsch", "youtube": "de", "deepl": "DE", "xtts": "de", "chatterbox": "de",
           "edge": [("de-DE-KatjaNeural", "Katja (female)"), ("de-DE-ConradNeural", "Conrad (male)")],
           "piper": [("de_DE-thorsten-medium", "Thorsten (male, medium)", 63), ("de_DE-kerstin-low", "Kerstin (female, low)", 20)]},
    "ja": {"name": "Japanese", "native": "日本語", "youtube": "ja", "deepl": "JA", "xtts": "ja", "chatterbox": "ja",
           "edge": [("ja-JP-NanamiNeural", "Nanami (female)"), ("ja-JP-KeitaNeural", "Keita (male)")], "piper": []},
    "sw": {"name": "Swahili", "native": "Kiswahili", "youtube": "sw", "deepl": None, "xtts": None, "chatterbox": "sw",
           "edge": [("sw-KE-ZuriNeural", "Zuri (female)"), ("sw-KE-RafikiNeural", "Rafiki (male)")],
           "piper": [("sw_CD-lanfrica-medium", "Lanfrica (medium)", 63)]},
    "mr": {"name": "Marathi", "native": "मराठी", "youtube": "mr", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("mr-IN-AarohiNeural", "Aarohi (female)"), ("mr-IN-ManoharNeural", "Manohar (male)")], "piper": []},
    "te": {"name": "Telugu", "native": "తెలుగు", "youtube": "te", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("te-IN-ShrutiNeural", "Shruti (female)"), ("te-IN-MohanNeural", "Mohan (male)")], "piper": []},
    "tr": {"name": "Turkish", "native": "Türkçe", "youtube": "tr", "deepl": "TR", "xtts": "tr", "chatterbox": "tr",
           "edge": [("tr-TR-EmelNeural", "Emel (female)"), ("tr-TR-AhmetNeural", "Ahmet (male)")],
           "piper": [("tr_TR-dfki-medium", "DFKI (female, medium)", 63), ("tr_TR-fahrettin-medium", "Fahrettin (male, medium)", 63)]},
    "ta": {"name": "Tamil", "native": "தமிழ்", "youtube": "ta", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("ta-IN-PallaviNeural", "Pallavi (female)"), ("ta-IN-ValluvarNeural", "Valluvar (male)")], "piper": []},
    "vi": {"name": "Vietnamese", "native": "Tiếng Việt", "youtube": "vi", "deepl": "VI", "xtts": None, "chatterbox": None,
           "edge": [("vi-VN-HoaiMyNeural", "HoaiMy (female)"), ("vi-VN-NamMinhNeural", "NamMinh (male)")],
           "piper": [("vi_VN-vais1000-medium", "VAIS1000 (medium)", 63)]},
    "ko": {"name": "Korean", "native": "한국어", "youtube": "ko", "deepl": "KO", "xtts": "ko", "chatterbox": "ko",
           "edge": [("ko-KR-SunHiNeural", "SunHi (female)"), ("ko-KR-InJoonNeural", "InJoon (male)")], "piper": []},
    "fa": {"name": "Persian", "native": "فارسی", "youtube": "fa", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("fa-IR-DilaraNeural", "Dilara (female)"), ("fa-IR-FaridNeural", "Farid (male)")],
           "piper": [("fa_IR-amir-medium", "Amir (male, medium)", 63), ("fa_IR-gyro-medium", "Gyro (medium)", 63)]},
    # --- further languages selectable as the voice-over target (UI falls back to English) ---
    "cs": {"name": "Czech", "native": "čeština", "youtube": "cs", "deepl": "CS", "xtts": "cs", "chatterbox": None,
           "edge": [("cs-CZ-VlastaNeural", "Vlasta (female)"), ("cs-CZ-AntoninNeural", "Antonín (male)")],
           "piper": [("cs_CZ-jirka-medium", "Jirka (male, medium)", 63)]},
    "hu": {"name": "Hungarian", "native": "magyar", "youtube": "hu", "deepl": "HU", "xtts": "hu", "chatterbox": None,
           "edge": [("hu-HU-NoemiNeural", "Noémi (female)"), ("hu-HU-TamasNeural", "Tamás (male)")],
           "piper": [("hu_HU-anna-medium", "Anna (female, medium)", 63), ("hu_HU-berta-medium", "Berta (female, medium)", 63)]},
    "uk": {"name": "Ukrainian", "native": "українська", "youtube": "uk", "deepl": "UK", "xtts": None, "chatterbox": None,
           "edge": [("uk-UA-PolinaNeural", "Polina (female)"), ("uk-UA-OstapNeural", "Ostap (male)")],
           "piper": [("uk_UA-ukrainian_tts-medium", "Ukrainian TTS (medium)", 63), ("uk_UA-lada-x_low", "Lada (female, x_low)", 20)]},
    "it": {"name": "Italian", "native": "italiano", "youtube": "it", "deepl": "IT", "xtts": "it", "chatterbox": "it",
           "edge": [("it-IT-ElsaNeural", "Elsa (female)"), ("it-IT-DiegoNeural", "Diego (male)")],
           "piper": [("it_IT-paola-medium", "Paola (female, medium)", 63), ("it_IT-riccardo-x_low", "Riccardo (male, x_low)", 20)]},
    "nl": {"name": "Dutch", "native": "Nederlands", "youtube": "nl", "deepl": "NL", "xtts": "nl", "chatterbox": "nl",
           "edge": [("nl-NL-ColetteNeural", "Colette (female)"), ("nl-NL-MaartenNeural", "Maarten (male)")],
           "piper": [("nl_NL-mls-medium", "MLS (medium)", 63), ("nl_BE-nathalie-medium", "Nathalie (female, Belgium, medium)", 63)]},
    "ro": {"name": "Romanian", "native": "română", "youtube": "ro", "deepl": "RO", "xtts": None, "chatterbox": None,
           "edge": [("ro-RO-AlinaNeural", "Alina (female)"), ("ro-RO-EmilNeural", "Emil (male)")],
           "piper": [("ro_RO-mihai-medium", "Mihai (male, medium)", 63)]},
    "el": {"name": "Greek", "native": "Ελληνικά", "youtube": "el", "deepl": "EL", "xtts": None, "chatterbox": "el",
           "edge": [("el-GR-AthinaNeural", "Athina (female)"), ("el-GR-NestorasNeural", "Nestoras (male)")],
           "piper": [("el_GR-rapunzelina-low", "Rapunzelina (female, low)", 20)]},
    "sv": {"name": "Swedish", "native": "svenska", "youtube": "sv", "deepl": "SV", "xtts": None, "chatterbox": "sv",
           "edge": [("sv-SE-SofieNeural", "Sofie (female)"), ("sv-SE-MattiasNeural", "Mattias (male)")],
           "piper": [("sv_SE-nst-medium", "NST (medium)", 63)]},
    "da": {"name": "Danish", "native": "dansk", "youtube": "da", "deepl": "DA", "xtts": None, "chatterbox": "da",
           "edge": [("da-DK-ChristelNeural", "Christel (female)"), ("da-DK-JeppeNeural", "Jeppe (male)")],
           "piper": [("da_DK-talesyntese-medium", "Talesyntese (medium)", 63)]},
    "fi": {"name": "Finnish", "native": "suomi", "youtube": "fi", "deepl": "FI", "xtts": None, "chatterbox": "fi",
           "edge": [("fi-FI-NooraNeural", "Noora (female)"), ("fi-FI-HarriNeural", "Harri (male)")],
           "piper": [("fi_FI-harri-medium", "Harri (male, medium)", 63)]},
    "no": {"name": "Norwegian", "native": "norsk", "youtube": "no", "deepl": "NB", "xtts": None, "chatterbox": "no",
           "edge": [("nb-NO-PernilleNeural", "Pernille (female)"), ("nb-NO-FinnNeural", "Finn (male)")],
           "piper": [("no_NO-talesyntese-medium", "Talesyntese (medium)", 63)]},
    "sk": {"name": "Slovak", "native": "slovenčina", "youtube": "sk", "deepl": "SK", "xtts": None, "chatterbox": None,
           "edge": [("sk-SK-ViktoriaNeural", "Viktória (female)"), ("sk-SK-LukasNeural", "Lukáš (male)")],
           "piper": [("sk_SK-lili-medium", "Lili (female, medium)", 63)]},
    "he": {"name": "Hebrew", "native": "עברית", "youtube": "iw", "deepl": "HE", "xtts": None, "chatterbox": "he",
           "edge": [("he-IL-HilaNeural", "Hila (female)"), ("he-IL-AvriNeural", "Avri (male)")], "piper": []},
    "th": {"name": "Thai", "native": "ไทย", "youtube": "th", "deepl": "TH", "xtts": None, "chatterbox": None,
           "edge": [("th-TH-PremwadeeNeural", "Premwadee (female)"), ("th-TH-NiwatNeural", "Niwat (male)")], "piper": []},
    "ms": {"name": "Malay", "native": "Bahasa Melayu", "youtube": "ms", "deepl": None, "xtts": None, "chatterbox": "ms",
           "edge": [("ms-MY-YasminNeural", "Yasmin (female)"), ("ms-MY-OsmanNeural", "Osman (male)")], "piper": []},
    "bg": {"name": "Bulgarian", "native": "български", "youtube": "bg", "deepl": "BG", "xtts": None, "chatterbox": None,
           "edge": [("bg-BG-KalinaNeural", "Kalina (female)"), ("bg-BG-BorislavNeural", "Borislav (male)")], "piper": []},
    "hr": {"name": "Croatian", "native": "hrvatski", "youtube": "hr", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("hr-HR-GabrijelaNeural", "Gabrijela (female)"), ("hr-HR-SreckoNeural", "Srećko (male)")], "piper": []},
    "sr": {"name": "Serbian", "native": "српски", "youtube": "sr", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("sr-RS-SophieNeural", "Sophie (female)"), ("sr-RS-NicholasNeural", "Nicholas (male)")],
           "piper": [("sr_RS-serbski_institut-medium", "Serbski institut (medium)", 63)]},
    "sl": {"name": "Slovenian", "native": "slovenščina", "youtube": "sl", "deepl": "SL", "xtts": None, "chatterbox": None,
           "edge": [("sl-SI-PetraNeural", "Petra (female)"), ("sl-SI-RokNeural", "Rok (male)")],
           "piper": [("sl_SI-artur-medium", "Artur (male, medium)", 63)]},
    "lt": {"name": "Lithuanian", "native": "lietuvių", "youtube": "lt", "deepl": "LT", "xtts": None, "chatterbox": None,
           "edge": [("lt-LT-OnaNeural", "Ona (female)"), ("lt-LT-LeonasNeural", "Leonas (male)")], "piper": []},
    "lv": {"name": "Latvian", "native": "latviešu", "youtube": "lv", "deepl": "LV", "xtts": None, "chatterbox": None,
           "edge": [("lv-LV-EveritaNeural", "Everita (female)"), ("lv-LV-NilsNeural", "Nils (male)")], "piper": []},
    "et": {"name": "Estonian", "native": "eesti", "youtube": "et", "deepl": "ET", "xtts": None, "chatterbox": None,
           "edge": [("et-EE-AnuNeural", "Anu (female)"), ("et-EE-KertNeural", "Kert (male)")], "piper": []},
    "ca": {"name": "Catalan", "native": "català", "youtube": "ca", "deepl": None, "xtts": None, "chatterbox": None,
           "edge": [("ca-ES-JoanaNeural", "Joana (female)"), ("ca-ES-EnricNeural", "Enric (male)")],
           "piper": [("ca_ES-upc_ona-medium", "UPC Ona (female, medium)", 63)]},
    "fil": {"name": "Filipino", "native": "Filipino", "youtube": "fil", "deepl": None, "xtts": None, "chatterbox": None,
            "edge": [("fil-PH-BlessicaNeural", "Blessica (female)"), ("fil-PH-AngeloNeural", "Angelo (male)")], "piper": []},
}

# Languages the extension UI is translated into (the rest use English UI with their own voice-over language).
UI_LANGUAGES = ["pl", "en", "zh", "yue", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ur", "id", "de", "ja", "sw",
                "mr", "te", "tr", "ta", "vi", "ko", "fa"]

DEFAULT_LANGUAGE = "pl"


def normalize_lang(code: str | None) -> str:
    """Map a BCP-47 tag ("pt-BR", "zh-HK", "zh_TW", "iw") to a LANGUAGES key; unknown -> DEFAULT_LANGUAGE."""
    if not code:
        return DEFAULT_LANGUAGE
    c = str(code).strip().replace("_", "-").lower()
    if c in LANGUAGES:
        return c
    if c in ("zh-hk", "zh-mo", "zh-yue", "yue-hk"):
        return "yue"
    if c.startswith("zh"):
        return "zh"
    if c in ("iw", "he-il"):
        return "he"
    if c in ("nb", "nn", "nb-no", "nn-no"):
        return "no"
    if c in ("tl", "tl-ph"):
        return "fil"
    base = c.split("-")[0]
    return base if base in LANGUAGES else DEFAULT_LANGUAGE


def language_name(code: str) -> str:
    return LANGUAGES.get(code, {}).get("name", code)


def catalog() -> list[dict[str, Any]]:
    """What the extension needs to build its language pickers."""
    return [{"code": c, "name": v["name"], "native": v["native"], "ui": c in UI_LANGUAGES,
             "youtube": v["youtube"]} for c, v in LANGUAGES.items()]
