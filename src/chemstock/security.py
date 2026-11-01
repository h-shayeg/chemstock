"""Password hashing (Argon2id, through pwdlib)."""

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# The cost is chosen here on purpose, not left to the library's defaults (which
# could change with an upgrade). It is the second option recommended by RFC 9106:
# 64 MiB of memory, 3 passes, 4 lanes. OWASP's minimum for Argon2id is 19 MiB, 2
# passes and 1 lane; tests/test_security.py fails if the cost ever drops below it.
TIME_COST = 3
MEMORY_COST_KIB = 65536
PARALLELISM = 4


def make_password_hash(
    time_cost: int = TIME_COST,
    memory_cost: int = MEMORY_COST_KIB,
    parallelism: int = PARALLELISM,
) -> PasswordHash:
    """Build a hasher. Only the test suite passes cheaper values than the defaults."""
    return PasswordHash(
        (
            Argon2Hasher(
                time_cost=time_cost,
                memory_cost=memory_cost,
                parallelism=parallelism,
            ),
        )
    )


_password_hash = make_password_hash()


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return _password_hash.verify(password, hashed_password)


# Verifying against this hash when a username does not exist makes "unknown
# user" and "wrong password" take about the same time, so response times do
# not reveal which usernames exist.
DUMMY_PASSWORD = "this-is-not-a-real-password"
DUMMY_HASH = hash_password(DUMMY_PASSWORD)
