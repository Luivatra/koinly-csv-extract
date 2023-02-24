from decimal import Decimal
import os
import typer
import requests
from rich import print
from rich.progress import track
from rich.table import Table
import json
from datetime import datetime, timezone
import time
from modules.State import state
from modules.TxTypes import KoinlyTX, transformErgopadVesting, transformManyOn1Trades, transformDefault, transformEarlyErgopadVesting, transformSpectrumLiquidity, transformStaking

app = typer.Typer()

def fetchErgoPriceHistory():
    print("Fetching ergo price history from coingecko...")
    res = requests.get(f"https://api.coingecko.com/api/v3/coins/ergo/market_chart/range?vs_currency=usd&from=1561939200&to={int(time.time())}")
    if res.ok:
        for price in res.json()["prices"]:
            state.ergoPriceHistory[int(price[0]/86400000)*86400] = Decimal(price[1])
        print("Done fetching ergo price history from coingecko")
    else:
        res.raise_for_status()

def getCurrentHeight():
    res = requests.get("http://213.239.193.208:9053/info")
    if res.ok:
        return int(res.json()["maxPeerHeight"])
    else:
        raise Exception("Could not fetch current block height, ensure the node is online")

def fetchTransactionBlock(address: str, fromHeight: int, toHeight: int, offset: int, limit: int):
    res = requests.get(f"https://api.ergoplatform.com/api/v1/addresses/{address}/transactions?fromHeight={fromHeight}&toHeight={toHeight}&offset={offset}&limit={limit}")
    if res.ok:
        return res.json()
    else:
        res.raise_for_status()

def extractTransactions(transactionsJson: json):
    for transaction in transactionsJson["items"]:
        state.transactionsJson[transaction["id"]] = transaction

def fetchTransactions(address: str, fromHeight: int, toHeight: int):
    offset = 0
    limit = 100
    firstBlock = fetchTransactionBlock(address,fromHeight,toHeight,offset,1)
    for value in track(range(round((firstBlock["total"])/limit)+1), description = f"Fetching transactions for {address}..."):
        block = fetchTransactionBlock(address, fromHeight, toHeight, offset, limit)
        extractTransactions(block)
        offset += limit

def isSmartContract(address: str):
    return len(address) != 51 or address[0] != "9"


def analyzeTransactions():
    fromAddresses = {}
    toAddresses = {}
    for transaction in state.transactionsJson.values():
        for input in transaction["inputs"]:
            fromAddresses[input["address"]] = 1 + (fromAddresses[input["address"]] if input["address"] in fromAddresses.keys() else 0)
        for output in transaction["outputs"]:
            toAddresses[output["address"]] = 1 + (toAddresses[output["address"]] if output["address"] in toAddresses.keys() else 0)
    fromAddressesSorted = sorted(fromAddresses.items(), key = lambda item: item[1], reverse=True) 
    toAddressesSorted = sorted(toAddresses.items(), key = lambda item: item[1], reverse=True)
    frequentAddressTable = Table("Address sent to you","Count","Address you sent to", "Count")
    for i in range(10):
        frequentAddressTable.add_row(fromAddressesSorted[i][0],str(fromAddressesSorted[i][1]),toAddressesSorted[i][0],str(toAddressesSorted[i][1]))
    print(frequentAddressTable)
    with open("from_contract_addresses.txt", "w") as f:
        for sc_address in filter(isSmartContract, fromAddresses.keys()):
            f.write(f"{sc_address}{os.linesep}")
    with open("to_contract_addresses.txt", "w") as f:
        for sc_address in filter(isSmartContract, toAddresses.keys()):
            f.write(f"{sc_address}{os.linesep}")

def extractKoinlyTX(transactionJson: json):
    if transactionJson["id"] not in state.handledTransactions:
        res = transformStaking(transactionJson)
        if len(res) > 0:
            return res
        res = transformErgopadVesting(transactionJson)
        if len(res) > 0:
            return res
        res = transformEarlyErgopadVesting(transactionJson)
        if len(res) > 0:
            return res
        res = transformSpectrumLiquidity(transactionJson)
        if len(res) > 0:
            return res
        res = transformManyOn1Trades(transactionJson)
        if len(res) > 0:
            return res
        res = transformDefault(transactionJson)
        return res
    else:
        return []

def extractKoinlyTransactions(transactionJson):
    for wallet in state.wallets:
        state.ownAddresses = wallet["addresses"]
        transactions = extractKoinlyTX(transactionJson)
        for tx in transactions:
            wallet["output"].write(str(tx))

@app.command()
def analyze(address: str, fromHeight: int = 0, toHeight: int = None):
    toHeight = toHeight if toHeight else getCurrentHeight()
    print(f"Analyzing transactions for {address} between blocks {fromHeight} and {toHeight}")
    fetchTransactions(address,fromHeight,toHeight)
    analyzeTransactions()

@app.command()
def extract(fromHeight: int = 0, toHeight: int = None):
    toHeight = toHeight if toHeight else getCurrentHeight()
    fetchErgoPriceHistory()
    for wallet in state.wallets:
        print(f"Fetching transactions for wallet {wallet['name']}")
        for address in wallet["addresses"]:
            fetchTransactions(address,fromHeight,toHeight)
    print(f"Extracted {len(state.transactionsJson)} transactions")
    state.transactionsJson = dict(sorted(state.transactionsJson.items(), key = lambda item: item[1]["globalIndex"]))
    for wallet in state.wallets:
        wallet["output"] = open(f"{wallet['name']}.csv", "w")
        wallet["output"].write(KoinlyTX.header())
    transactions = list(state.transactionsJson.values())
    for i in track(range(len(transactions)), description = f"Analyzing transactions..."):
        transaction = transactions[i]
        extractKoinlyTransactions(transaction)
    for wallet in state.wallets:
        wallet["output"].close()


if __name__ == "__main__":
    app()