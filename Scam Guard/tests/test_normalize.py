import hashlib

from scamguard.models import EntityType
from scamguard.normalize import detect_type, identifier_hash, mask, normalize


class TestDetectType:
    def test_digits_is_phone(self):
        assert detect_type("03001234567") == EntityType.PHONE

    def test_formatted_phone_is_phone(self):
        assert detect_type("+92 300 1234567") == EntityType.PHONE
        assert detect_type("0300-1234567") == EntityType.PHONE

    def test_at_handle_is_instagram(self):
        assert detect_type("@x") == EntityType.INSTAGRAM

    def test_instagram_url_is_instagram(self):
        assert detect_type("https://instagram.com/shop.pk") == EntityType.INSTAGRAM
        assert detect_type("instagram.com/shop.pk") == EntityType.INSTAGRAM

    def test_facebook_url_is_facebook(self):
        assert detect_type("https://facebook.com/marketplace/item/99") == EntityType.FACEBOOK

    def test_garbage_is_none(self):
        assert detect_type("totally not an identifier!") is None
        assert detect_type("") is None
        assert detect_type("   ") is None


class TestNormalize:
    def test_phone_local_number_unchanged(self):
        assert normalize("03001234567", EntityType.PHONE) == "03001234567"

    def test_phone_plus92_prefix(self):
        assert normalize("+92 300 1234567", EntityType.PHONE) == "03001234567"

    def test_phone_0092_prefix(self):
        assert normalize("00923001234567", EntityType.PHONE) == "03001234567"

    def test_instagram_at_handle_lowercased(self):
        assert normalize("@Shop.Pk", EntityType.INSTAGRAM) == "shop.pk"

    def test_instagram_url_lowercased(self):
        assert normalize("https://instagram.com/Shop.pk", EntityType.INSTAGRAM) == "shop.pk"

    def test_instagram_url_with_www_and_query(self):
        assert normalize("https://www.instagram.com/Shop.pk/?hl=en", EntityType.INSTAGRAM) == "shop.pk"

    def test_facebook_url_scheme_less_lowercase(self):
        assert (
            normalize("https://www.facebook.com/Marketplace/Item/123456789/", EntityType.FACEBOOK)
            == "facebook.com/marketplace/item/123456789"
        )

    def test_facebook_www_prefix_stripped(self):
        with_www = normalize(
            "https://www.facebook.com/Marketplace/Item/123456789/", EntityType.FACEBOOK
        )
        without_www = normalize(
            "https://facebook.com/Marketplace/Item/123456789/", EntityType.FACEBOOK
        )
        assert with_www == without_www
        assert with_www == "facebook.com/marketplace/item/123456789"

    def test_facebook_profile_ids_do_not_collide(self):
        one = normalize("https://www.facebook.com/profile.php?id=123", EntityType.FACEBOOK)
        two = normalize("https://www.facebook.com/profile.php?id=456", EntityType.FACEBOOK)
        assert one == "facebook.com/profile.php?id=123"
        assert two == "facebook.com/profile.php?id=456"
        assert one != two

    def test_facebook_other_query_params_dropped(self):
        assert (
            normalize("https://facebook.com/marketplace/item/1/?ref=ser&_fbclid=abc", EntityType.FACEBOOK)
            == "facebook.com/marketplace/item/1"
        )


class TestMask:
    def test_phone_mask(self):
        assert mask("03001234567", EntityType.PHONE) == "03**-***-4567"

    def test_instagram_mask(self):
        assert mask("shop.pk", EntityType.INSTAGRAM) == "@sh**.pk"

    def test_facebook_mask_first_20_chars(self):
        canonical = "www.facebook.com/marketplace/item/123456789"
        assert mask(canonical, EntityType.FACEBOOK) == "www.facebook.com/mar…"


class TestIdentifierHash:
    def test_sha256_hex_of_canonical(self):
        digest = identifier_hash("03001234567")
        assert digest == hashlib.sha256(b"03001234567").hexdigest()
        assert len(digest) == 64
        assert set(digest) <= set("0123456789abcdef")
