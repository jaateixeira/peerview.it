import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from peerview.adapters.auth.registry import ConfigurationError, build_providers
from peerview.adapters.settings import Settings
from peerview.domain.identity import Provider


def _pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _env(**extra: str) -> dict[str, str]:
    return {"PEERVIEW_SECRET_KEY": "s", "PEERVIEW_BASE_URL": "https://peereview.example", **extra}


def _providers(**extra: str):
    return build_providers(Settings.from_env(_env(**extra)))


def test_nothing_configured_means_password_only():
    assert _providers() == {}


def test_https_base_url_requires_a_secret_key():
    with pytest.raises(RuntimeError):
        Settings.from_env({"PEERVIEW_BASE_URL": "https://peereview.example"})


def test_dev_gets_a_random_secret_key_when_none_is_set():
    a = Settings.from_env({})
    b = Settings.from_env({})
    assert a.secret_key and a.secret_key != b.secret_key


def test_google_is_enabled_by_its_two_variables():
    providers = _providers(PEERVIEW_GOOGLE_CLIENT_ID="id", PEERVIEW_GOOGLE_CLIENT_SECRET="secret")
    assert set(providers) == {Provider.GOOGLE}


def test_partial_configuration_is_an_error_naming_what_is_missing():
    with pytest.raises(ConfigurationError, match="PEERVIEW_GOOGLE_CLIENT_SECRET"):
        _providers(PEERVIEW_GOOGLE_CLIENT_ID="id")


def test_apple_needs_all_four_values_and_accepts_the_key_inline():
    apple = {
        "PEERVIEW_APPLE_CLIENT_ID": "eu.example.web",
        "PEERVIEW_APPLE_TEAM_ID": "TEAM123456",
        "PEERVIEW_APPLE_KEY_ID": "KEY1234567",
        "PEERVIEW_APPLE_PRIVATE_KEY": _pem().replace("\n", "\\n"),
    }
    assert set(_providers(**apple)) == {Provider.APPLE}
    del apple["PEERVIEW_APPLE_TEAM_ID"]
    with pytest.raises(ConfigurationError, match="PEERVIEW_APPLE_TEAM_ID"):
        _providers(**apple)


def test_apple_private_key_can_come_from_a_file(tmp_path):
    key_file = tmp_path / "AuthKey.p8"
    key_file.write_text(_pem())
    providers = _providers(
        PEERVIEW_APPLE_CLIENT_ID="eu.example.web",
        PEERVIEW_APPLE_TEAM_ID="TEAM123456",
        PEERVIEW_APPLE_KEY_ID="KEY1234567",
        PEERVIEW_APPLE_PRIVATE_KEY_FILE=str(key_file),
    )
    assert set(providers) == {Provider.APPLE}


def test_haka_needs_metadata_and_keys():
    haka = {
        "PEERVIEW_HAKA_ENTITY_ID": "https://peereview.example/saml/sp",
        "PEERVIEW_HAKA_CERT_FILE": "sp.crt",
        "PEERVIEW_HAKA_KEY_FILE": "sp.key",
        "PEERVIEW_HAKA_METADATA_URL": "https://haka.funet.fi/metadata/haka-metadata.xml",
        "PEERVIEW_HAKA_METADATA_CERT": "haka-signing.crt",
        "PEERVIEW_HAKA_DISCOVERY_URL": "https://haka.funet.fi/shibboleth/WAYF",
    }
    assert set(_providers(**haka)) == {Provider.HAKA}
    del haka["PEERVIEW_HAKA_KEY_FILE"]
    with pytest.raises(ConfigurationError, match="PEERVIEW_HAKA_KEY_FILE"):
        _providers(**haka)


def test_haka_remote_metadata_must_be_verified_against_a_signing_certificate():
    with pytest.raises(ConfigurationError, match="PEERVIEW_HAKA_METADATA_CERT"):
        _providers(
            PEERVIEW_HAKA_ENTITY_ID="e",
            PEERVIEW_HAKA_CERT_FILE="c",
            PEERVIEW_HAKA_KEY_FILE="k",
            PEERVIEW_HAKA_METADATA_URL="https://haka.funet.fi/metadata/haka-metadata.xml",
            PEERVIEW_HAKA_DISCOVERY_URL="https://haka.funet.fi/shibboleth/WAYF",
        )


def test_haka_needs_discovery_or_a_fixed_idp():
    with pytest.raises(ConfigurationError, match="DISCOVERY_URL"):
        _providers(
            PEERVIEW_HAKA_ENTITY_ID="e",
            PEERVIEW_HAKA_CERT_FILE="c",
            PEERVIEW_HAKA_KEY_FILE="k",
            PEERVIEW_HAKA_METADATA_FILE="idp.xml",
        )
    ok = _providers(
        PEERVIEW_HAKA_ENTITY_ID="e",
        PEERVIEW_HAKA_CERT_FILE="c",
        PEERVIEW_HAKA_KEY_FILE="k",
        PEERVIEW_HAKA_METADATA_FILE="idp.xml",
        PEERVIEW_HAKA_IDP_ENTITY_ID="https://testidp.funet.fi/idp/shibboleth",
    )
    assert set(ok) == {Provider.HAKA}


def test_the_site_host_is_read_from_the_base_url():
    assert Settings("s", base_url="https://peereview.example/").host == "peereview.example"
    assert Settings("s").host == "localhost:8000"
