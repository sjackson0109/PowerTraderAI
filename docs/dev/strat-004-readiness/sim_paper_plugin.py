"""pytest plugin (scratch): the proposed change simulated in memory for one test run.
STRAT-004's loaded catalogue entry reads "paper"; catalogue.json is not touched."""


def pytest_configure(config):
    from strategies import catalogue as cat

    cat.CATALOGUE["STRAT-004"] = dict(cat.CATALOGUE["STRAT-004"], authorisation="paper")
