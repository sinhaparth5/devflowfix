from app.adapters.cache.redis import RedisCache


def test_redis_cache_ignores_blank_password() -> None:
    cache = RedisCache(url="redis://redis:6379/0", password="")

    assert cache.password is None


def test_redis_cache_uses_explicit_password_for_passwordless_url() -> None:
    cache = RedisCache(url="redis://redis:6379/0", password="secret")

    assert cache.password == "secret"


def test_redis_cache_does_not_duplicate_password_from_url() -> None:
    cache = RedisCache(url="redis://default:secret@redis:6379/0", password="ignored")

    assert cache.password is None
