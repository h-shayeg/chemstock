import subprocess
import sys

from chemstock import security, users
from chemstock.security import hash_password, verify_password

# OWASP's minimum for Argon2id (Password Storage Cheat Sheet): 19 MiB of memory,
# 2 passes and 1 lane. The real server must never hash with less than this.
OWASP_MIN_MEMORY_KIB = 19456
OWASP_MIN_TIME_COST = 2

FRESH_INTERPRETER = (
    "from chemstock.security import DUMMY_HASH, hash_password\n"
    "print(hash_password('a long enough password'))\n"
    "print(DUMMY_HASH)\n"
)


def _parameters(hashed: str) -> dict[str, int]:
    """Read m, t and p from a hash such as $argon2id$v=19$m=65536,t=3,p=4$..."""
    pairs = hashed.split("$")[3].split(",")
    return {name: int(value) for name, value in (pair.split("=") for pair in pairs)}


def test_hash_is_not_the_password_and_uses_argon2() -> None:
    hashed = hash_password("correct horse battery")

    assert "correct horse" not in hashed
    assert hashed.startswith("$argon2")


def test_same_password_gives_different_hashes() -> None:
    # Every hash has its own random salt.
    assert hash_password("same password!") != hash_password("same password!")


def test_verify_accepts_only_the_right_password() -> None:
    hashed = hash_password("right password 1")

    assert verify_password("right password 1", hashed)
    assert not verify_password("wrong password 1", hashed)


def test_dummy_hash_never_matches_a_real_password() -> None:
    assert not verify_password("anything at all", security.DUMMY_HASH)


def test_the_test_suite_hashes_with_the_cheapest_valid_settings() -> None:
    # conftest.py makes the suite fast. If that stops working the suite becomes
    # slow again, and this test says why.
    cheapest = {"m": 8, "t": 1, "p": 1}

    assert _parameters(hash_password("a long enough password")) == cheapest
    assert _parameters(security.DUMMY_HASH) == cheapest
    assert _parameters(users.DUMMY_HASH) == cheapest


def test_the_real_server_uses_strong_parameters() -> None:
    # A fresh interpreter: nothing of this test suite has touched the module.
    result = subprocess.run(
        [sys.executable, "-c", FRESH_INTERPRETER],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    new_hash, dummy_hash = result.stdout.split()

    for hashed in (new_hash, dummy_hash):
        parameters = _parameters(hashed)
        assert hashed.startswith("$argon2id$")
        assert parameters["m"] >= OWASP_MIN_MEMORY_KIB
        assert parameters["t"] >= OWASP_MIN_TIME_COST
        assert parameters["p"] >= 1
