"""Rumik gets the spellings it was measured to pronounce correctly."""

from app.tts.rumik import rumik_pronunciation as p


def test_measured_spellings():
    assert p("क्या आप इस weekend साइट विज़िट करना चाहेंगे?") == "क्या आप इस weekend site visit करना चाहेंगे?"
    assert p("तीन स्लॉट्स हैं: पहला स्लॉट सुबह") == "तीन slots हैं: पहला slot सुबह"
    assert p("possession दिसंबर में, assistant और area") == "पज़ेशन दिसंबर में, असिस्टेंट और एरिया"
    assert p("अमेनिटीज़ में gym है") == "amenities में gym है"


def test_other_words_are_untouched():
    text = "आपका budget कितना है? मैं आपको details भेज देती हूँ।"
    assert p(text) == text
