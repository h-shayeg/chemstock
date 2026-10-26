from chemstock.security import DUMMY_HASH, hash_password, verify_password


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
    assert not verify_password("anything at all", DUMMY_HASH)
