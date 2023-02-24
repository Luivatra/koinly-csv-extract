class Vesting:
    valueInUSD: float
    tokensVested: int

    def __init__(self, valueInUSD: float, tokensVested: int) -> None:
        self.valueInUSD = valueInUSD
        self.tokensVested = tokensVested