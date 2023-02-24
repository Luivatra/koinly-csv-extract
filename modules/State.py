from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
import json

from modules.Vesting import Vesting


class State:
    transactionsJson: dict[str,dict] = {}
    wallets = {}
    ownAddresses: list[str] = []
    allOwnAddresses: list[str] = []
    tokens: OrderedDict[str,dict] = {}
    nfts: OrderedDict[str,dict] = {}
    ergoPriceHistory: dict[int, Decimal] = {}
    vesting: dict[str,Vesting] = {}
    staking: dict[str, Decimal] = {}
    handledTransactions = list[str]

    def __init__(self, wallets) -> None:
        self.transactionsJson = {}
        self.wallets = wallets
        self.ownAddresses = []
        self.tokens = {}
        self.nfts = {}
        self.ergoPriceHistory = {}
        self.vesting = {}
        self.handledTransactions = []
        self.allOwnAddresses = []
        self.staking = {}
        for wallet in wallets:
            for address in wallet["addresses"]:
                self.allOwnAddresses.append(address)

    def getErgoPrice(self, timestamp: int) -> Decimal:
        return self.ergoPriceHistory.get(int(timestamp/86400000)*86400)
    
    def getTokenName(self, tokenId):
        if tokenId in self.tokens.keys():
            return (self.tokens[tokenId]["name"] if self.tokens[tokenId]["name"] else "Unknown").replace('"','')
        elif tokenId in self.nfts.keys():
            return (self.nfts[tokenId]["name"] if self.nfts[tokenId]["name"] else "Unknown").replace('"','')
    
    def koinlyToken(self, tokenId: str) -> str:
        if tokenId in self.tokens.keys():
            return 'NULL'+str(list(self.tokens.keys()).index(tokenId)+1)
        elif tokenId in self.nfts.keys():
            return 'NFT'+str(list(self.nfts.keys()).index(tokenId)+1)
        
    def registerAsset(self, asset):
        if (asset["tokenId"] not in self.tokens.keys() and asset["tokenId"] not in self.nfts.keys()):
            if (asset["amount"] == 1):
                self.nfts[asset["tokenId"]] = asset
            else:
                self.tokens[asset["tokenId"]] = asset

wallets = {}
with open("wallets.json","r") as f:
    wallets = json.loads(f.read())["wallets"]
state = State(wallets)