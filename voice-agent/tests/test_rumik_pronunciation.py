"""Rumik gets the spellings it was measured to pronounce correctly."""

from app.tts.rumik import rumik_pronunciation as p


def test_measured_spellings():
    assert p("क्या आप इस weekend साइट विज़िट करना चाहेंगे?") == "क्या आप इस weekend site visit करना चाहेंगे?"
    assert p("तीन स्लॉट्स हैं: पहला स्लॉट सुबह") == "तीन slots हैं: पहला slot सुबह"
    assert p("possession दिसंबर में, assistant और area") == "पज़ेशन दिसंबर में, assistent और एरिया"
    assert p("अमेनिटीज़ में gym है") == "amenities में gym है"


def test_other_words_are_untouched():
    text = "आपका budget कितना है? मैं आपको details भेज देती हूँ।"
    assert p(text) == text


def test_acronyms_and_brochure():
    assert p("मैं एक एआई असिस्टेंट हूँ") == "मैं एक AI assistent हूँ"
    assert p("brochure WhatsApp पर भेज दूँ? RERA number") == "ब्रोशर WhatsApp पर भेज दूँ? रेरा number"


def test_english_words_stay_in_latin_for_rumik():
    from app.lang.devanagari import to_devanagari_speech
    out = to_devanagari_speech("Skyline Crest में 2 BHK 76.5 lakh से है, budget बताइए", "hi", None, english_words=False)
    assert out == "Skyline Crest में दो BHK साढ़े छिहत्तर लाख से है, budget बताइए"
