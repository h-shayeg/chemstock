"""Password hashing (Argon2, through pwdlib)."""

from pwdlib import PasswordHash

_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _password_hash.verify(password, hashed_password)


# Verifying against this hash when a username does not exist makes "unknown
# user" and "wrong password" take about the same time, so response times do
# not reveal which usernames exist.
DUMMY_HASH = hash_password("this-is-not-a-real-password")
