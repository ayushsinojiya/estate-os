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


def test_numbers_stay_digits_with_hindi_units_and_times_for_rumik():
    from app.lang.devanagari import to_devanagari_speech as speech

    def rumik(text):
        return speech(text, "hi", None, english_words=False, number_words=False)

    assert rumik("Skyline Crest में 2 BHK 76.5 lakh से 82 lakh में है, और आपकी visit Sunday 4 PM को है।") == \
        "Skyline Crest में 2 BHK 76.5 लाख से 82 लाख में है, और आपकी visit Sunday शाम 4 बजे है।"
    assert rumik("1 crore 5 lakh से 1 crore 15 lakh") == "1 करोड़ 5 लाख से 1 करोड़ 15 लाख"
    assert rumik("Saturday 10 AM या Monday 6:30 PM") == "Saturday सुबह 10 बजे या Monday शाम 6:30 बजे"
    assert rumik("Price ₹85,00,000 है, GST 5% है।") == "Price 85 लाख है, GST 5 प्रतिशत है।"
    assert rumik("सुबह 10 AM मिलते हैं") == "सुबह 10 बजे मिलते हैं"


def test_pune_localities_use_the_chosen_spellings():
    assert p("Wakad, Baner और Kharadi में options हैं") == "वाकड, बाणेर और खराडी में options हैं"
    assert p("Ravet, Hadapsar, Magarpatta") == "रावेट, हड़पसर, मगरपट्टा"
    assert p("हिंजवडी, वाघोली और कोथरूड") == "Hinjewadi, Wagholi और Kothrud"
    assert p("Hinjewadi Phase 2, Undri, Viman Nagar, Pune") == "Hinjewadi Phase 2, Undri, Viman Nagar, Pune"
