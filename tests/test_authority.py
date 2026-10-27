from itertools import product

import pytest

from chemstock.authority import may_assign, may_manage
from chemstock.roles import ROLE_RANK, Role

# Written down independently of ROLE_RANK: lowest to highest.
ORDER = [Role.VIEWER, Role.MEMBER, Role.ADMIN, Role.OWNER]


def test_every_role_has_a_rank_in_the_expected_order() -> None:
    assert set(ROLE_RANK) == set(Role)
    assert sorted(Role, key=lambda role: ROLE_RANK[role]) == ORDER


@pytest.mark.parametrize(
    ("actor", "other"), list(product(ORDER, ORDER)), ids=lambda role: role.value
)
def test_only_strictly_lower_roles_can_be_assigned_or_managed(
    actor: Role, other: Role
) -> None:
    expected = ORDER.index(other) < ORDER.index(actor)

    assert may_assign(actor, other) is expected
    assert may_manage(actor, other) is expected


def test_nobody_can_assign_the_owner_role() -> None:
    assert not any(may_assign(actor, Role.OWNER) for actor in Role)


def test_admins_cannot_manage_each_other_or_the_owner() -> None:
    assert not may_manage(Role.ADMIN, Role.ADMIN)
    assert not may_manage(Role.ADMIN, Role.OWNER)


def test_the_owner_manages_everyone_else() -> None:
    assert all(may_manage(Role.OWNER, other) for other in ORDER[:-1])
    assert may_assign(Role.OWNER, Role.ADMIN)
