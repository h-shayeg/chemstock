import pytest
from pydantic import ValidationError

from chemstock.config import Settings

SECRET = "s" * 40


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make these tests independent of the machine's environment variables.

    CI sets POSTGRES_HOST and POSTGRES_PORT for its database service, and the
    defaults test must not see them.
    """
    for name in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "SECRET_KEY",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
    ):
        monkeypatch.delenv(name, raising=False)


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_user": "user",
        "postgres_password": "p@ss/word",
        "postgres_db": "db",
        "secret_key": SECRET,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_database_url_uses_defaults_for_local_development() -> None:
    url = make_settings().database_url

    assert url.host == "localhost"
    assert url.port == 5433
    assert url.database == "db"


def test_database_url_can_point_to_docker_service() -> None:
    url = make_settings(postgres_host="db", postgres_port=5432).database_url

    assert url.host == "db"
    assert url.port == 5432


def test_database_url_escapes_special_characters_in_password() -> None:
    rendered = make_settings().database_url.render_as_string(hide_password=False)

    assert "p%40ss%2Fword" in rendered


def test_secret_key_is_required() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            postgres_user="user",
            postgres_password="password",
            postgres_db="db",
        )


def test_short_secret_key_is_rejected_without_leaking_it() -> None:
    with pytest.raises(ValidationError) as error:
        make_settings(secret_key="too-short-secret")

    assert "at least 32 characters" in str(error.value)
    assert "too-short-secret" not in str(error.value)


def test_secret_key_is_hidden_when_settings_are_printed() -> None:
    settings = make_settings()

    assert SECRET not in repr(settings)
    assert SECRET not in str(settings)
    assert settings.secret_key.get_secret_value() == SECRET


def test_token_lifetime_defaults_to_30_minutes() -> None:
    assert make_settings().access_token_expire_minutes == 30


@pytest.mark.parametrize("minutes", [0, 1441])
def test_token_lifetime_must_be_reasonable(minutes: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(access_token_expire_minutes=minutes)


def test_throttling_defaults() -> None:
    settings = make_settings()

    assert settings.login_max_attempts_per_username == 5
    assert settings.login_max_attempts_per_ip == 20
    assert settings.login_lockout_minutes == 15


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("login_max_attempts_per_username", 0),
        ("login_max_attempts_per_username", 101),
        ("login_max_attempts_per_ip", 0),
        ("login_max_attempts_per_ip", 1001),
        ("login_lockout_minutes", 0),
        ("login_lockout_minutes", 1441),
    ],
)
def test_throttling_limits_must_be_reasonable(name: str, value: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(**{name: value})
