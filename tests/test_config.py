from chemstock.config import Settings


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "postgres_user": "user",
        "postgres_password": "p@ss/word",
        "postgres_db": "db",
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
