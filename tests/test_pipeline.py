from backend.pipeline import canonical_json
from backend.search import GoogleVisionSearch, is_post_url, normalize_url, platform_for_url


def test_canonical_payload_is_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})


def test_social_post_classification_rejects_profiles():
    assert platform_for_url("https://www.instagram.com/p/ABC123/") == "Instagram"
    assert is_post_url("https://www.instagram.com/p/ABC123/", "Instagram")
    assert not is_post_url("https://www.instagram.com/some-profile/", "Instagram")
    assert is_post_url("https://x.com/openai/status/123456789", "X")


def test_tracking_parameters_are_removed():
    assert normalize_url("https://x.com/user/status/12?utm_source=test&lang=en#frag") == "https://x.com/user/status/12?lang=en"


def test_provider_response_yields_only_real_post_urls():
    responses = [{
        "webDetection": {
            "pagesWithMatchingImages": [
                {"url": "https://www.instagram.com/p/real-post/", "pageTitle": "Real post", "fullMatchingImages": [{"url": "https://cdn.example/image.jpg"}]},
                {"url": "https://www.instagram.com/a-profile/", "pageTitle": "Profile", "fullMatchingImages": [{"url": "https://cdn.example/image.jpg"}]},
                {"url": "https://example.com/article", "pageTitle": "Article", "fullMatchingImages": [{"url": "https://cdn.example/image.jpg"}]},
            ]
        }
    }]
    candidates = GoogleVisionSearch._candidates(responses)
    assert [item.page_url for item in candidates] == ["https://www.instagram.com/p/real-post"]
