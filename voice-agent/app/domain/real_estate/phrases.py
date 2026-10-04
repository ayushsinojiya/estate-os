"""Static sentences Riya speaks, in every supported language.

Pre-rendered to audio at startup (PhraseAudioCache), so greetings, fillers and closes cost no TTS
latency mid-call. The builder name and the disclosure flags are part of the text, so changing
either re-renders the affected phrases automatically (the cache key includes a text hash).
"""

from __future__ import annotations

from typing import Mapping

from app.lang.languages import Lang

_DISCLOSURE: dict[tuple[bool, bool], dict[Lang, str]] = {
    (True, True): {
        "en": "I'm an AI assistant, and this call is recorded for quality.",
        "hi": "मैं एक एआई असिस्टेंट हूँ, और यह कॉल क्वालिटी के लिए रिकॉर्ड हो रही है।",
        "mr": "मी एक एआय असिस्टंट आहे, आणि हा कॉल गुणवत्तेसाठी रेकॉर्ड होत आहे.",
    },
    (True, False): {
        "en": "I'm an AI assistant.",
        "hi": "मैं एक एआई असिस्टेंट हूँ।",
        "mr": "मी एक एआय असिस्टंट आहे.",
    },
    (False, True): {
        "en": "This call is recorded for quality.",
        "hi": "यह कॉल क्वालिटी के लिए रिकॉर्ड हो रही है।",
        "mr": "हा कॉल गुणवत्तेसाठी रेकॉर्ड होत आहे.",
    },
    (False, False): {"en": "", "hi": "", "mr": ""},
}

_PHRASES: dict[str, dict[Lang, str]] = {
    "greeting_inbound": {
        "en": "Hello, this is Riya, a property advisor with {builder}. {disclosure} How can I help you today?",
        "hi": "नमस्ते, मैं रिया बोल रही हूँ, {builder} से प्रॉपर्टी एडवाइज़र। {disclosure} बताइए, मैं आपकी क्या मदद कर सकती हूँ?",
        "mr": "नमस्कार, मी रिया बोलतेय, {builder} कडून प्रॉपर्टी ॲडव्हायझर. {disclosure} सांगा, मी तुमची काय मदत करू शकते?",
    },
    # ---- engine phrases (app/domain/base.py ENGINE_PHRASES)
    "thinking": {
        "en": "One moment, let me check.",
        "hi": "एक मिनट, मैं देखती हूँ।",
        "mr": "एक मिनिट, मी बघते.",
    },
    "silence_prompt": {
        "en": "Sorry, I couldn't hear you. Could you say that again?",
        "hi": "मुझे सुनाई नहीं दिया। कृपया दोबारा बताइए।",
        "mr": "मला ऐकू आले नाही. कृपया पुन्हा सांगा.",
    },
    "still_there": {
        "en": "Are you still there?",
        "hi": "क्या आप लाइन पर हैं?",
        "mr": "आपण लाईनवर आहात का?",
    },
    "closing": {
        "en": "Thank you for your time. Have a lovely day!",
        "hi": "आपके समय के लिए धन्यवाद। आपका दिन शुभ हो।",
        "mr": "तुमच्या वेळेबद्दल धन्यवाद. तुमचा दिवस छान जावो.",
    },
    "transfer": {
        "en": "I'm having trouble on my side. A property expert will call you back shortly.",
        "hi": "मेरी तरफ़ से थोड़ी दिक्कत आ रही है। हमारे प्रॉपर्टी एक्सपर्ट जल्द ही आपको कॉल करेंगे।",
        "mr": "माझ्याकडे थोडी अडचण येत आहे. आमचे प्रॉपर्टी एक्सपर्ट तुम्हाला लवकरच कॉल करतील.",
    },
    # ---- tool fillers, played while a lookup runs
    "filler_search": {
        "en": "Just a second, let me check what's available.",
        "hi": "एक सेकंड, मैं चेक करती हूँ।",
        "mr": "एक सेकंद, मी चेक करते.",
    },
    "filler_knowledge": {
        "en": "One moment, let me look that up.",
        "hi": "एक सेकंड, मैं जानकारी देखती हूँ।",
        "mr": "एक सेकंद, मी माहिती बघते.",
    },
    "filler_slots": {
        "en": "Let me check the visit slots.",
        "hi": "एक सेकंड, मैं विज़िट के स्लॉट देखती हूँ।",
        "mr": "एक सेकंद, मी व्हिजिटचे स्लॉट बघते.",
    },
    "filler_booking": {
        "en": "Okay, booking that for you now.",
        "hi": "ठीक है, मैं बुक कर रही हूँ।",
        "mr": "ठीक आहे, मी बुक करते.",
    },
    # ---- guardrail responses
    "expert_confirm": {
        "en": "I'll have our expert confirm the exact figure.",
        "hi": "सही आंकड़ा हमारे एक्सपर्ट आपको कन्फ़र्म कर देंगे।",
        "mr": "नेमका आकडा आमचे एक्सपर्ट तुम्हाला कन्फर्म करतील.",
    },
    "dnc_ack": {
        "en": "I'm sorry for the trouble. We won't call you again. Goodbye.",
        "hi": "परेशानी के लिए माफ़ी चाहती हूँ। हम आपको दोबारा कॉल नहीं करेंगे। नमस्ते।",
        "mr": "त्रासाबद्दल माफ करा. आम्ही तुम्हाला पुन्हा कॉल करणार नाही. नमस्कार.",
    },
    "sensitive_refusal": {
        "en": "Please don't share any ID or card numbers. I don't need them for this.",
        "hi": "कृपया कोई भी आईडी या कार्ड नंबर न बताइए, इसकी ज़रूरत नहीं है।",
        "mr": "कृपया कोणताही आयडी किंवा कार्ड नंबर सांगू नका, त्याची गरज नाही.",
    },
    "no_promises": {
        "en": "I can't advise on investment returns, financing or tax, but our property expert can guide you.",
        "hi": "रिटर्न, फाइनेंसिंग या टैक्स पर मैं सलाह नहीं दे सकती, हमारे प्रॉपर्टी एक्सपर्ट इसमें आपकी मदद करेंगे।",
        "mr": "रिटर्न, फायनान्सिंग किंवा टॅक्सबद्दल मी सल्ला देऊ शकत नाही, आमचे प्रॉपर्टी एक्सपर्ट यात मदत करतील.",
    },
    "wrong_number": {
        "en": "Sorry for the trouble, I must have the wrong number. Goodbye.",
        "hi": "माफ़ कीजिए, शायद गलत नंबर लग गया। नमस्ते।",
        "mr": "माफ करा, बहुधा चुकीचा नंबर लागला. नमस्कार.",
    },
}

# Pune localities in the demo inventory, so they are spoken in the conversation's script.
LOCALITY_NAMES: dict[str, str] = {
    "Pune": "पुणे", "Baner": "बाणेर", "Wakad": "वाकड", "Kharadi": "खराडी", "Hadapsar": "हडपसर",
    "Kothrud": "कोथरूड", "Aundh": "औंध", "Pashan": "पाषाण", "Bavdhan": "बावधन",
    "Viman Nagar": "विमान नगर", "Kondhwa": "कोंढवा", "Hinjawadi": "हिंजवडी", "Hinjewadi": "हिंजवडी",
    "Balewadi": "बालेवाडी", "Moshi": "मोशी", "Ravet": "रावेत", "Magarpatta": "मगरपट्टा",
    "Wagholi": "वाघोली", "Undri": "उंड्री", "Koregaon Park": "कोरेगाव पार्क", "Tathawade": "ताथवडे",
    "Sus": "सूस", "Dhanori": "धानोरी", "Mundhwa": "मुंढवा", "Warje": "वारजे", "Dhayari": "धायरी",
    "NIBM Road": "एनआयबीएम रोड", "Riya": "रिया",
}


class RealEstatePhrases:
    def __init__(self, builder_name: str, disclose_ai: bool = True, disclose_recording: bool = True,
                 extra_names: Mapping[str, str] | None = None):
        self.builder_name = builder_name
        self.disclosure = _DISCLOSURE[(disclose_ai, disclose_recording)]
        self.names: dict[str, str] = {**LOCALITY_NAMES, **(extra_names or {})}

    def keys(self) -> tuple[str, ...]:
        return tuple(_PHRASES)

    def render(self, key: str, lang: Lang) -> str:
        entry = _PHRASES.get(key)
        if not entry:
            raise KeyError(f"unknown phrase: {key}")
        text = entry.get(lang) or entry["en"]
        if "{" in text:
            text = text.format(builder=self.builder_name, disclosure=self.disclosure.get(lang, ""))
        return " ".join(text.split())
