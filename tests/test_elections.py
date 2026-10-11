from simdemocracy.elections import allocate_seats


def test_dhondt_known_result() -> None:
    votes = {1: 100_000, 2: 80_000, 3: 30_000, 4: 20_000}
    seats = allocate_seats(votes, 8, "dhondt", 0.0)
    assert seats == {1: 4, 2: 3, 3: 1, 4: 0}
    assert sum(seats.values()) == 8


def test_sainte_lague_differs_from_dhondt() -> None:
    votes = {1: 100_000, 2: 80_000, 3: 30_000, 4: 20_000}
    dhondt = allocate_seats(votes, 8, "dhondt", 0.0)
    sainte = allocate_seats(votes, 8, "sainte_lague", 0.0)
    assert sum(sainte.values()) == 8
    assert sainte != dhondt


def test_threshold_excludes_small_parties() -> None:
    votes = {1: 90, 2: 8, 3: 2}
    seats = allocate_seats(votes, 10, "dhondt", 0.05)
    assert seats[3] == 0
    assert sum(seats.values()) == 10


def test_no_votes_allocates_nothing() -> None:
    assert allocate_seats({1: 0, 2: 0}, 5, "dhondt", 0.0) == {1: 0, 2: 0}
