"""Static voice / model catalogues for Kokoro, Kitten and Pocket.

Lists were compiled from the official sources:

* Kokoro: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
* Kitten: https://github.com/KittenML/KittenTTS (README + docs/voices-and-expression.md
  + docs/onnx-models.md)
* Pocket: https://github.com/kyutai-labs/pocket-tts README and
  https://huggingface.co/kyutai/tts-voices

Piper's catalogue is fetched dynamically from ``rhasspy/piper-voices`` and is
therefore not part of this module.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Shared language metadata
# ---------------------------------------------------------------------------

KOKORO_LANGUAGES: dict[str, dict[str, Any]] = {
    "a": {"name": "American English", "flag": "🇺🇸", "espeak": "en-us"},
    "b": {"name": "British English", "flag": "🇬🇧", "espeak": "en-gb"},
    "e": {"name": "Spanish", "flag": "🇪🇸", "espeak": "es"},
    "f": {"name": "French", "flag": "🇫🇷", "espeak": "fr-fr"},
    "h": {"name": "Hindi", "flag": "🇮🇳", "espeak": "hi"},
    "i": {"name": "Italian", "flag": "🇮🇹", "espeak": "it"},
    "j": {"name": "Japanese", "flag": "🇯🇵", "espeak": None},
    "p": {"name": "Brazilian Portuguese", "flag": "🇧🇷", "espeak": "pt-br"},
    "z": {"name": "Mandarin Chinese", "flag": "🇨🇳", "espeak": None},
}

# ---------------------------------------------------------------------------
# Kokoro-82M - all 54 official voices (VOICES.md)
# ---------------------------------------------------------------------------

_KOKORO_VOICES: list[tuple[str, str, str, str | None, list[str], str]] = [
    # (voice id, gender, overall grade, description, tags, lang code)
    ("af_heart", "female", "A", "Top-tier American female voice", ["heart"], "a"),
    ("af_alloy", "female", "C", "American female", [], "a"),
    ("af_aoede", "female", "C+", "American female", [], "a"),
    ("af_bella", "female", "A-", "Expressive American female", ["hot"], "a"),
    ("af_jessica", "female", "D", "American female", [], "a"),
    ("af_kore", "female", "C+", "American female", [], "a"),
    ("af_nicole", "female", "B-", "American female", ["headphones"], "a"),
    ("af_nova", "female", "C", "American female", [], "a"),
    ("af_river", "female", "D", "American female", [], "a"),
    ("af_sarah", "female", "C+", "American female", [], "a"),
    ("af_sky", "female", "C-", "American female", [], "a"),
    ("am_adam", "male", "F+", "American male", [], "a"),
    ("am_echo", "male", "D", "American male", [], "a"),
    ("am_eric", "male", "D", "American male", [], "a"),
    ("am_fenrir", "male", "C+", "American male", [], "a"),
    ("am_liam", "male", "D", "American male", [], "a"),
    ("am_michael", "male", "C+", "American male", [], "a"),
    ("am_onyx", "male", "D", "American male", [], "a"),
    ("am_puck", "male", "C+", "American male", [], "a"),
    ("am_santa", "male", "D-", "American male", [], "a"),
    ("bf_alice", "female", "D", "British female", [], "b"),
    ("bf_emma", "female", "B-", "British female", [], "b"),
    ("bf_isabella", "female", "C", "British female", [], "b"),
    ("bf_lily", "female", "D", "British female", [], "b"),
    ("bm_daniel", "male", "D", "British male", [], "b"),
    ("bm_fable", "male", "C", "British male", [], "b"),
    ("bm_george", "male", "C", "British male", [], "b"),
    ("bm_lewis", "male", "D+", "British male", [], "b"),
    ("jf_alpha", "female", "C+", "Japanese female", [], "j"),
    ("jf_gongitsune", "female", "C", "Japanese female (Gongitsune)", [], "j"),
    ("jf_nezumi", "female", "C-", "Japanese female (Nezumi no Yomeiri)", [], "j"),
    ("jf_tebukuro", "female", "C", "Japanese female (Tebukuro wo Kaini)", [], "j"),
    ("jm_kumo", "male", "C-", "Japanese male (Kumo no Ito)", [], "j"),
    ("zf_xiaobei", "female", "D", "Mandarin female", [], "z"),
    ("zf_xiaoni", "female", "D", "Mandarin female", [], "z"),
    ("zf_xiaoxiao", "female", "D", "Mandarin female", [], "z"),
    ("zf_xiaoyi", "female", "D", "Mandarin female", [], "z"),
    ("zm_yunjian", "male", "D", "Mandarin male", [], "z"),
    ("zm_yunxi", "male", "D", "Mandarin male", [], "z"),
    ("zm_yunxia", "male", "D", "Mandarin male", [], "z"),
    ("zm_yunyang", "male", "D", "Mandarin male", [], "z"),
    ("ef_dora", "female", None, "Spanish female", [], "e"),
    ("em_alex", "male", None, "Spanish male", [], "e"),
    ("em_santa", "male", None, "Spanish male (Santa)", [], "e"),
    ("ff_siwis", "female", "B-", "French female", [], "f"),
    ("hf_alpha", "female", "C", "Hindi female", [], "h"),
    ("hf_beta", "female", "C", "Hindi female", [], "h"),
    ("hm_omega", "male", "C", "Hindi male", [], "h"),
    ("hm_psi", "male", "C", "Hindi male", [], "h"),
    ("if_sara", "female", "C", "Italian female", [], "i"),
    ("im_nicola", "male", "C", "Italian male", [], "i"),
    ("pf_dora", "female", None, "Brazilian Portuguese female", [], "p"),
    ("pm_alex", "male", None, "Brazilian Portuguese male", [], "p"),
    ("pm_santa", "male", None, "Brazilian Portuguese male (Santa)", [], "p"),
]

KOKORO_VOICES: list[dict[str, Any]] = [
    {
        "id": voice_id,
        "name": voice_id,
        "lang_code": lang_code,
        "language": KOKORO_LANGUAGES[lang_code]["name"],
        "flag": KOKORO_LANGUAGES[lang_code]["flag"],
        "gender": gender,
        "grade": grade,
        "description": description,
        "tags": tags,
    }
    for voice_id, gender, grade, description, tags, lang_code in _KOKORO_VOICES
]

KOKORO_LANG_BY_VOICE: dict[str, str] = {
    voice["id"]: voice["lang_code"] for voice in KOKORO_VOICES
}

KOKORO_VARIANTS: list[dict[str, Any]] = [
    {
        "id": "kokoro-82m",
        "label": "Kokoro-82M",
        "description": (
            "82M parameter StyleTTS2-based model. 54 voices across 9 languages, "
            "Apache-2.0 licensed."
        ),
        "repo": "hexgrad/Kokoro-82M",
        "size_hint": "~330 MB (fp32) + per-voice tensors (~500 KB each)",
        "download_required": False,
        "languages": [
            {
                "code": code,
                "name": meta["name"],
                "flag": meta["flag"],
            }
            for code, meta in KOKORO_LANGUAGES.items()
        ],
    }
]

# ---------------------------------------------------------------------------
# Kitten TTS
# ---------------------------------------------------------------------------

KITTEN_LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"name": "English", "flag": "🇬🇧"},
    "ar": {"name": "Arabic", "flag": "🇸🇦"},
    "zh": {"name": "Chinese (Mandarin)", "flag": "🇨🇳"},
    "fr": {"name": "French", "flag": "🇫🇷"},
    "de": {"name": "German", "flag": "🇩🇪"},
    "hi": {"name": "Hindi", "flag": "🇮🇳"},
    "it": {"name": "Italian", "flag": "🇮🇹"},
    "pt": {"name": "Portuguese", "flag": "🇧🇷"},
    "ru": {"name": "Russian", "flag": "🇷🇺"},
    "es": {"name": "Spanish", "flag": "🇪🇸"},
}

KITTEN_08_VOICES: list[tuple[str, str]] = [
    ("Bella", "female"),
    ("Jasper", "male"),
    ("Luna", "female"),
    ("Bruno", "male"),
    ("Rosie", "female"),
    ("Hugo", "male"),
    ("Kiki", "female"),
    ("Leo", "male"),
]

KITTEN2_VOICES: list[dict[str, Any]] = [
    # KittenTTS 0.8 speakers, carried over to KittenTTS 2
    {"id": "Bella", "gender": "female", "desc": "KittenTTS 0.8 voice, female"},
    {"id": "Jasper", "gender": "male", "desc": "KittenTTS 0.8 voice, male"},
    {"id": "Luna", "gender": "female", "desc": "KittenTTS 0.8 voice, female"},
    {"id": "Bruno", "gender": "male", "desc": "KittenTTS 0.8 voice, male"},
    {"id": "Rosie", "gender": "female", "desc": "KittenTTS 0.8 voice, female"},
    {"id": "Hugo", "gender": "male", "desc": "KittenTTS 0.8 voice, male"},
    {"id": "Kiki", "gender": "female", "desc": "KittenTTS 0.8 voice, female"},
    {"id": "Leo", "gender": "male", "desc": "KittenTTS 0.8 voice, male"},
    {"id": "Matthew", "gender": "male", "desc": "Exhausted mechanic"},
    {"id": "Elliot", "gender": "male", "desc": "Grieving young"},
    {"id": "Willow", "gender": "female", "desc": "Hushed young"},
    {"id": "Dolores", "gender": "female", "desc": "Southern elderly"},
    {"id": "Victor", "gender": "male", "desc": "Controlled fury, older"},
    {"id": "Dante", "gender": "male", "desc": "Playful smooth, young"},
    {"id": "Alfred", "gender": "male", "desc": "Tender, older"},
    {"id": "Saoirse", "gender": "female", "desc": "Joyful Irish"},
    {"id": "Claire", "gender": "female", "desc": "Playful professional"},
    {"id": "Raven", "gender": "female", "desc": "Controlled fury, young"},
    {"id": "Marcus", "gender": "male", "desc": "Smooth radio DJ"},
    {"id": "Herbert", "gender": "male", "desc": "Wise elderly professor"},
    {"id": "Diana", "gender": "female", "desc": "Stern military officer"},
    {"id": "Laurence", "gender": "male", "desc": "Dramatic stage actor"},
    {"id": "Maeve", "gender": "female", "desc": "Cozy warm storyteller"},
    {"id": "Walter", "gender": "male", "desc": "Warm grandfather"},
    {"id": "Edith", "gender": "female", "desc": "Soft elderly grandmother"},
    {"id": "Miles", "gender": "male", "desc": "Gentle librarian"},
    {"id": "Grace", "gender": "female", "desc": "Soothing nurse"},
    {"id": "Reginald", "gender": "male", "desc": "Distinguished elderly diplomat"},
    {"id": "Iris", "gender": "female", "desc": "Hushed museum guide"},
    {"id": "Frank", "gender": "male", "desc": "Gravelly grizzled war veteran"},
    {"id": "Serena", "gender": "female", "desc": "Gentle yoga instructor"},
    {"id": "Julian", "gender": "male", "desc": "Dreamy soft poet"},
    {"id": "Eleanor", "gender": "female", "desc": "Somber historian"},
    {"id": "Otis", "gender": "male", "desc": "Rumbling blues musician"},
    {"id": "Vincent", "gender": "male", "desc": "Hushed museum guide"},
    {"id": "Martha", "gender": "female", "desc": "Weathered radio journalist"},
    {"id": "Sable", "gender": "female", "desc": "Hushed conspirator"},
    {"id": "Victoria", "gender": "female", "desc": "Regal narrator"},
    # Multilingual voices, named after their language
    {"id": "Arabic", "gender": None, "desc": "Multilingual voice (ar)", "lang": "ar"},
    {"id": "Chinese", "gender": None, "desc": "Multilingual voice (zh)", "lang": "zh"},
    {"id": "French", "gender": None, "desc": "Multilingual voice (fr)", "lang": "fr"},
    {"id": "German", "gender": None, "desc": "Multilingual voice (de)", "lang": "de"},
    {"id": "Hindi", "gender": None, "desc": "Multilingual voice (hi)", "lang": "hi"},
    {"id": "Italian", "gender": None, "desc": "Multilingual voice (it)", "lang": "it"},
    {
        "id": "Portuguese",
        "gender": None,
        "desc": "Multilingual voice (pt)",
        "lang": "pt",
    },
    {"id": "Russian", "gender": None, "desc": "Multilingual voice (ru)", "lang": "ru"},
    {"id": "Spanish", "gender": None, "desc": "Multilingual voice (es)", "lang": "es"},
]

KITTEN2_EXPRESSIONS: dict[str, list[str]] = {
    "emotions": [
        "angry",
        "contemplative",
        "excited",
        "joyful",
        "mundane",
        "nervous",
        "sad",
        "stern",
        "surprised",
        "tender",
    ],
    "events": [
        "gasp",
        "giggle",
        "growl",
        "gulp",
        "laugh",
        "pause",
        "scoff",
        "sigh",
        "sob",
        "um",
    ],
}

KITTEN_VARIANTS: list[dict[str, Any]] = [
    {
        "id": "kitten-tts-2",
        "label": "KittenTTS 2 (1.7B)",
        "family": "llm",
        "model_ids": ["KittenML/kitten-tts-2"],
        "description": (
            "Flagship 1.7B 1-bit speech LM with in-context voice cloning, "
            "47 voices, 10 languages and expression control. Runs realtime on CPU."
        ),
        "size_hint": "506 MiB (emb4) / 947 MiB (packed)",
        "download_required": True,
        "cloning": True,
    },
    {
        "id": "kitten-tts-mini-0.8",
        "label": "KittenTTS Mini (80M)",
        "family": "onnx",
        "model_ids": ["KittenML/kitten-tts-mini-0.8"],
        "description": "80M parameter ONNX model, 8 voices, very fast on CPU.",
        "size_hint": "80 MB",
        "download_required": True,
        "cloning": False,
    },
    {
        "id": "kitten-tts-micro-0.8",
        "label": "KittenTTS Micro (40M)",
        "family": "onnx",
        "model_ids": ["KittenML/kitten-tts-micro-0.8"],
        "description": "40M parameter ONNX model, 8 voices.",
        "size_hint": "41 MB",
        "download_required": True,
        "cloning": False,
    },
    {
        "id": "kitten-tts-nano-0.8",
        "label": "KittenTTS Nano (15M fp32)",
        "family": "onnx",
        "model_ids": [
            "KittenML/kitten-tts-nano-0.8",
            "KittenML/kitten-tts-nano-0.8-fp32",
        ],
        "description": "15M parameter ONNX model (fp32), 8 voices, tiny footprint.",
        "size_hint": "56 MB",
        "download_required": True,
        "cloning": False,
    },
    {
        "id": "kitten-tts-nano-0.8-int8",
        "label": "KittenTTS Nano (15M int8)",
        "family": "onnx",
        "model_ids": ["KittenML/kitten-tts-nano-0.8-int8"],
        "description": "15M parameter quantized ONNX model, 8 voices, 25 MB.",
        "size_hint": "25 MB",
        "download_required": True,
        "cloning": False,
    },
]

# ---------------------------------------------------------------------------
# Pocket TTS
# ---------------------------------------------------------------------------

POCKET_VOICES: list[dict[str, Any]] = [
    {"id": "alba", "language": "English", "lang": "en", "gender": "female",
     "desc": "Alba Mackenna (casual)"},
    {"id": "anna", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p228"},
    {"id": "azelma", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p303"},
    {"id": "bill_boerst", "language": "English", "lang": "en", "gender": "male",
     "desc": "Voice Zero"},
    {"id": "caro_davy", "language": "English", "lang": "en", "gender": "female",
     "desc": "Voice Zero"},
    {"id": "charles", "language": "English", "lang": "en", "gender": "male",
     "desc": "VCTK p254"},
    {"id": "cosette", "language": "English", "lang": "en", "gender": "female",
     "desc": "Expresso (confused)"},
    {"id": "eponine", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p262"},
    {"id": "eve", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p361"},
    {"id": "fantine", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p244"},
    {"id": "george", "language": "English", "lang": "en", "gender": "male",
     "desc": "VCTK p315"},
    {"id": "jane", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p339"},
    {"id": "jean", "language": "English", "lang": "en", "gender": None,
     "desc": "EARS p010 (freeform speech)"},
    {"id": "javert", "language": "English", "lang": "en", "gender": "male",
     "desc": "Voice donation (Butter)"},
    {"id": "marius", "language": "English", "lang": "en", "gender": "male",
     "desc": "Voice donation (Selfie)"},
    {"id": "mary", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p333"},
    {"id": "michael", "language": "English", "lang": "en", "gender": "male",
     "desc": "VCTK p360"},
    {"id": "paul", "language": "English", "lang": "en", "gender": "male",
     "desc": "VCTK p259"},
    {"id": "peter_yearsley", "language": "English", "lang": "en", "gender": "male",
     "desc": "Voice Zero"},
    {"id": "stuart_bell", "language": "English", "lang": "en", "gender": "male",
     "desc": "Voice Zero"},
    {"id": "vera", "language": "English", "lang": "en", "gender": "female",
     "desc": "VCTK p229"},
    {"id": "estelle", "language": "French", "lang": "fr", "gender": "female",
     "desc": "unmute (développeuse)"},
    {"id": "juergen", "language": "German", "lang": "de", "gender": "male",
     "desc": "Common Voice (de-DE)"},
    {"id": "giovanni", "language": "Italian", "lang": "it", "gender": "male",
     "desc": "Common Voice (it)"},
    {"id": "rafael", "language": "Portuguese", "lang": "pt", "gender": "male",
     "desc": "g-Vi8PgmSY0 (enhanced)"},
    {"id": "lola", "language": "Spanish", "lang": "es", "gender": "female",
     "desc": "Common Voice (es)"},
]

POCKET_VARIANTS: list[dict[str, Any]] = [
    {"id": "english", "label": "English", "language": "English", "lang": "en",
     "layers": 6, "high_quality": False},
    {"id": "english_2026-01", "label": "English (2026-01)", "language": "English",
     "lang": "en", "layers": 6, "high_quality": False},
    {"id": "english_2026-04", "label": "English (2026-04)", "language": "English",
     "lang": "en", "layers": 6, "high_quality": False},
    {"id": "english_2026-09", "label": "English (2026-09)", "language": "English",
     "lang": "en", "layers": 6, "high_quality": False},
    {"id": "french", "label": "French", "language": "French", "lang": "fr",
     "layers": 6, "high_quality": False},
    {"id": "french_24l", "label": "French 24L", "language": "French", "lang": "fr",
     "layers": 24, "high_quality": True},
    {"id": "german", "label": "German", "language": "German", "lang": "de",
     "layers": 6, "high_quality": False},
    {"id": "german_24l", "label": "German 24L", "language": "German", "lang": "de",
     "layers": 24, "high_quality": True},
    {"id": "portuguese", "label": "Portuguese", "language": "Portuguese", "lang": "pt",
     "layers": 6, "high_quality": False},
    {"id": "portuguese_24l", "label": "Portuguese 24L", "language": "Portuguese",
     "lang": "pt", "layers": 24, "high_quality": True},
    {"id": "italian", "label": "Italian", "language": "Italian", "lang": "it",
     "layers": 6, "high_quality": False},
    {"id": "italian_24l", "label": "Italian 24L", "language": "Italian", "lang": "it",
     "layers": 24, "high_quality": True},
    {"id": "spanish", "label": "Spanish", "language": "Spanish", "lang": "es",
     "layers": 6, "high_quality": False},
    {"id": "spanish_24l", "label": "Spanish 24L", "language": "Spanish", "lang": "es",
     "layers": 24, "high_quality": True},
    {"id": "dutch", "label": "Dutch", "language": "Dutch", "lang": "nl",
     "layers": 6, "high_quality": False},
    {"id": "dutch_24l", "label": "Dutch 24L", "language": "Dutch", "lang": "nl",
     "layers": 24, "high_quality": True},
]
