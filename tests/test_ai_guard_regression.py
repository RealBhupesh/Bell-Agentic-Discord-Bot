import pytest


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("stupid https://example.org", "safe"),
        ("éupiñ https://example.org", "safe"),
        ("éupi https://example.org", "safe"),
        ("upi٣ https://example.org", "safe"),
        ("(upi) https://example.org", "scam_phishing"),
        ("skill yourself", "safe"),
        ("kill yourselfish", "safe"),
        ("kill yourself!", "harassment_toxic"),
        ("ABCDEFGHIJKLMNOPQRS", "safe"),
        ("ABCDEFGHIJKLMNOPQRST", "spam_flood"),
        ("a" * 11, "safe"),
        ("a" * 12, "spam_flood"),
        ("bc idiot", "safe"),
        ("mc idiot", "safe"),
    ],
)
def test_ai_guard_heuristic_boundaries(text, category):
    import bot

    normalized, _ = bot._ai_mod_normalize_hinglish(text)
    result = bot._ai_mod_heuristic_payload(text, normalized, corroborators={})
    assert result["category"] == category
