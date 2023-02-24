from decimal import Decimal
import json
from typing import Tuple
from rich import print
from modules.Config import Config
from modules.State import state

class Balance:
    value: Decimal = Decimal(0)
    tokens: dict[str,Decimal] = {}

    def __init__(self) -> None:
        self.value = Decimal(0)
        self.tokens = {}

    def assetsInBalance(self):
        assets = []
        if abs(self.value) > 0.1:
            assets.append({"amount": self.value, "currency": "erg", "tokenId": None})
        for token in self.tokens:
            if abs(self.tokens[token]) > 0:
                assets.append({"amount": self.tokens[token], "currency": state.koinlyToken(token), "tokenId": token})
        return assets

    def dust(self):
        return self.value if abs(self.value) < 0.1 else Decimal(0)

    def singleAssetBalance(self):
        return len(self.assetsInBalance()) == 1

    def __add__(self, o):
        resultingBalance = Balance()
        resultingBalance.value = self.value + o.value
        for token in (self.tokens | o.tokens).keys():
            combinedTokens = self.tokens.get(token,Decimal(0)) + o.tokens.get(token,Decimal(0))
            if abs(combinedTokens) > 0:
                resultingBalance.tokens[token] = combinedTokens
        return resultingBalance

    def outgoingAssets(self):
        return list(filter(lambda item: item["amount"] > 0,self.assetsInBalance()))

    def incomingAssets(self):
        return list(filter(lambda item: item["amount"] < 0,self.assetsInBalance()))

def inOutBalance(transactionJson: json) -> Balance:
    balance = Balance()
    for input in transactionJson["inputs"]:
        if input["address"] in state.ownAddresses:
            balance.value += Decimal(input["value"])/Decimal(10**9)
            for asset in input["assets"]:
                state.registerAsset(asset)
                decimals = asset["decimals"] if asset["decimals"] else 0
                balance.tokens[asset["tokenId"]] = Decimal(asset["amount"])/Decimal(10**decimals) + (balance.tokens[asset["tokenId"]] if asset["tokenId"] in balance.tokens.keys() else Decimal(0))
    for output in transactionJson["outputs"]:
        if output["address"] in state.ownAddresses:
            balance.value -= Decimal(output["value"])/Decimal(10**9)
            for asset in output["assets"]:
                state.registerAsset(asset)
                decimals = asset["decimals"] if asset["decimals"] else 0
                balance.tokens[asset["tokenId"]] = Decimal(-1*asset["amount"])/Decimal(10**decimals) + (balance.tokens[asset["tokenId"]] if asset["tokenId"] in balance.tokens.keys() else Decimal(0))
    return balance
