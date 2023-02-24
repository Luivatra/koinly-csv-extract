from datetime import date, datetime, timezone
from decimal import Decimal
import os
import json
import requests
from modules.Balance import inOutBalance
from modules.Config import Config

from modules.State import state
from modules.Vesting import Vesting

from rich import print

class KoinlyTX:
    date: datetime
    sentAmount: float
    sentCurrency: str
    receivedAmount: float
    receivedCurrency: str
    feeAmount: float
    feeCurrency: str
    netWorthAmount: float
    netWorthCurrency: str
    label: str
    description: str
    txHash: str

    def __init__(self,
        date: datetime,
        sentAmount: str = '',
        sentCurrency: str = '',
        receivedAmount: str = '',
        receivedCurrency: str = '',
        feeAmount: str = '',
        feeCurrency: str = '',
        netWorthAmount: str = '',
        netWorthCurrency: str = '',
        label: str = '',
        description: str = '',
        txHash: str = '') -> None:

        self.date = date
        self.sentAmount = sentAmount
        self.sentCurrency = sentCurrency
        self.receivedAmount = receivedAmount
        self.receivedCurrency = receivedCurrency
        self.feeAmount = feeAmount
        self.feeCurrency = feeCurrency
        self.netWorthAmount = netWorthAmount
        self.netWorthCurrency = netWorthCurrency
        self.label = label
        self.description = description
        self.txHash = txHash

    def header() -> str:
        return '"Date","Sent Amount","Sent Currency","Received Amount","Received Currency","Fee Amount","Fee Currency","Net Worth Amount","Net Worth Currency","Label","Description","TxHash"'+os.linesep

    def __str__(self) -> str:
        return f"{self.date.isoformat()},{self.sentAmount},{self.sentCurrency},{self.receivedAmount},{self.receivedCurrency},{self.feeAmount},{self.feeCurrency},{self.netWorthAmount},{self.netWorthCurrency},{self.label},{self.description},{self.txHash}{os.linesep}"

def getTokenPrice(token: str, t: int):
    if token in Config.config["tokensWithValue"].keys():
        ergoPrice = state.getErgoPrice(t)
        res = requests.get(f"https://api.ergopad.io/asset/price/{Config.config['tokensWithValue'][token]}/{t}")
        if res.ok:
            if token == "SigUSD":
                return min(Decimal(1.1),max(Decimal(0.9),Decimal(res.json()["price"])*ergoPrice))
            return Decimal(res.json()["price"])*ergoPrice
        else:
            return res.raise_for_status()
    else:
        return Decimal(0)

def initiateEarlyVesting(transactionJson: json, vestingKey: str):
    for input in transactionJson["inputs"]:
        if "R9" in input["additionalRegisters"].keys():
            if input["additionalRegisters"]["R9"]["renderedValue"] == vestingKey:
                vestingPeriods = round(int(input["additionalRegisters"]["R8"]["renderedValue"])/int(input["additionalRegisters"]["R6"]["renderedValue"]))
                price = 0.0
                if vestingPeriods == 9: #Seed sale
                    price = 0.011
                elif vestingPeriods == 6:
                    price = 0.02
                elif vestingPeriods == 3:
                    price = 0.03
                state.vesting[vestingKey] = Vesting(price*int(input["additionalRegisters"]["R8"]["renderedValue"]),int(input["additionalRegisters"]["R8"]["renderedValue"]))

def transformStaking(transactionJson):
    result = []
    balance = None
    for output in transactionJson["outputs"]:
        if output["address"] == Config.config["stakingV1"]:
            balance = inOutBalance(transactionJson)
        if output["address"] not in state.allOwnAddresses and output["spentTransactionId"] in state.transactionsJson.keys():
            for input in state.transactionsJson[output["spentTransactionId"]]["inputs"]:
                if input["address"] in Config.config["stakingV2"]:
                    balance = inOutBalance(transactionJson) + inOutBalance(state.transactionsJson[output["spentTransactionId"]])
                    state.handledTransactions.append(output["spentTransactionId"])
    if balance:
        stakeKey = None
        for ass in balance.assetsInBalance():
            if ass["tokenId"]:
                if "Stake Key" in state.getTokenName(ass["tokenId"]):
                    stakeKey = ass["tokenId"]
        for ass in balance.outgoingAssets():
            if ass["tokenId"] and ass["tokenId"] != stakeKey:
                if stakeKey not in state.staking.keys():
                    state.staking[stakeKey] = Decimal(0)
                state.staking[stakeKey] += abs(ass["amount"])
                tokenName = state.getTokenName(ass["tokenId"])
                description = f'{ass["currency"]}={tokenName}'
                result.append(
                    KoinlyTX(
                        date=datetime.fromtimestamp(transactionJson["timestamp"]/1000),
                        sentAmount=abs(ass["amount"]),
                        sentCurrency=state.koinlyToken(ass["tokenId"]),
                        label="Sent to Pool",
                        description=description,
                        txHash=transactionJson["id"]
                    )
                )
            else:
                description = ""
                if ass["tokenId"]:
                    tokenName = state.getTokenName(ass["tokenId"])
                    description = f'{ass["currency"]}={tokenName}'
                result.append(
                    KoinlyTX(
                        date=datetime.fromtimestamp(transactionJson["timestamp"]/1000,tz=timezone.utc),
                        sentAmount=abs(ass["amount"]),
                        sentCurrency=state.koinlyToken(ass["tokenId"]) if ass["tokenId"] else 'erg',
                        description=description,
                        txHash=transactionJson["id"]
                    )
                )
        for ass in balance.incomingAssets():
            if ass["tokenId"] and ass["tokenId"] != stakeKey:
                if stakeKey not in state.staking.keys():
                    state.staking[stakeKey] = Decimal(0)
                state.staking[stakeKey] -= abs(ass["amount"])
                tokenName = state.getTokenName(ass["tokenId"])
                description = f'{ass["currency"]}={tokenName}'
                reward = Decimal(0)
                if state.staking[stakeKey] < 0:
                    reward = abs(state.staking[stakeKey])
                    state.staking[stakeKey] = Decimal(0)
                if reward < abs(ass["amount"]):
                    result.append(
                        KoinlyTX(
                            date=datetime.fromtimestamp(transactionJson["timestamp"]/1000,tz=timezone.utc),
                            receivedAmount=abs(ass["amount"])-reward,
                            receivedCurrency=state.koinlyToken(ass["tokenId"]),
                            label="Received from Pool",
                            description=description,
                            txHash=transactionJson["id"]
                        )
                    )
                if reward > 0:
                    price = getTokenPrice(ass["tokenId"], transactionJson["timestamp"])
                    result.append(
                        KoinlyTX(
                            date=datetime.fromtimestamp(transactionJson["timestamp"]/1000,tz=timezone.utc),
                            receivedAmount=reward,
                            receivedCurrency=state.koinlyToken(ass["tokenId"]),
                            netWorthAmount=price*reward,
                            netWorthCurrency='usd',
                            label="reward",
                            description=description,
                            txHash=transactionJson["id"]
                        )
                    )
            else:
                description = ""
                if ass["tokenId"]:
                    tokenName = state.getTokenName(ass["tokenId"])
                    description = f'{ass["currency"]}={tokenName}'
                result.append(
                    KoinlyTX(
                        date=datetime.fromtimestamp(transactionJson["timestamp"]/1000,tz=timezone.utc),
                        receivedAmount=abs(ass["amount"]),
                        receivedCurrency=state.koinlyToken(ass["tokenId"]) if ass["tokenId"] else 'erg',
                        description=description,
                        txHash=transactionJson["id"]
                    )
                )
    return result

                
def transformErgopadVesting(transactionJson: json) -> list[KoinlyTX]:
    vestedTokens = 0
    vestedValue = {}
    for input in transactionJson["inputs"]:
        if input["address"] in Config.config["vesting"]:
            vestedTokens = input["assets"][0]["amount"]
    if vestedTokens > 0:
        defaultRes = transformDefault(transactionJson)
        for output in transactionJson["outputs"][0:1]:
            if output["address"] in state.ownAddresses:
                if len(output["assets"])>2 and output["assets"][1]["tokenId"] in Config.config["tokensWithValue"].keys():
                    vestingKey = output["assets"][0]["tokenId"]
                    receivedTokens = output["assets"][1]["amount"]
                    if not state.vesting[vestingKey].tokensVested:
                        state.vesting[vestingKey].tokensVested = vestedTokens
                    receivedValue = Decimal(receivedTokens)/Decimal(state.vesting[vestingKey].tokensVested)*Decimal(state.vesting[vestingKey].valueInUSD)
                    state.vesting[vestingKey].tokensVested -= receivedTokens
                    state.vesting[vestingKey].valueInUSD -= receivedValue
                    if state.koinlyToken(output["assets"][1]["tokenId"]) not in vestedValue.keys():
                        vestedValue[state.koinlyToken(output["assets"][1]["tokenId"])] = 0
                    vestedValue[state.koinlyToken(output["assets"][1]["tokenId"])] += receivedValue
        for koinlyTX in defaultRes:
            if koinlyTX.receivedCurrency in vestedValue.keys():
                koinlyTX.netWorthAmount = vestedValue[koinlyTX.receivedCurrency]/100
                koinlyTX.netWorthCurrency = "usd"
        return defaultRes
    else:
        return []

def transformEarlyErgopadVesting(transactionJson: json) -> list[KoinlyTX]:
    earlyVestingDetected = False
    vestedValue = {}
    for input in transactionJson["inputs"]:
        if input["address"] == Config.config["earlyVesting"]:
            earlyVestingDetected = True
    if earlyVestingDetected:
        defaultRes = transformDefault(transactionJson)
        for output in transactionJson["outputs"]:
            if output["address"] in state.ownAddresses:
                if "R4" in output["additionalRegisters"].keys() and output["assets"][0]["tokenId"] in Config.config["tokensWithValue"].keys():
                    vestingKey = output["additionalRegisters"]["R4"]["renderedValue"]
                    if vestingKey not in state.vesting.keys():
                        initiateEarlyVesting(transactionJson,vestingKey)
                    receivedTokens = output["assets"][0]["amount"]
                    receivedValue = float(receivedTokens)/float(state.vesting[vestingKey].tokensVested)*state.vesting[vestingKey].valueInUSD
                    state.vesting[vestingKey].tokensVested -= receivedTokens
                    state.vesting[vestingKey].valueInUSD -= receivedValue
                    if state.koinlyToken(output["assets"][0]["tokenId"]) not in vestedValue.keys():
                        vestedValue[state.koinlyToken(output["assets"][0]["tokenId"])] = 0
                    vestedValue[state.koinlyToken(output["assets"][0]["tokenId"])] += receivedValue
        for koinlyTX in defaultRes:
            if koinlyTX.receivedCurrency in vestedValue.keys():
                koinlyTX.netWorthAmount = vestedValue[koinlyTX.receivedCurrency]/100
                koinlyTX.netWorthCurrency = "usd"
        return defaultRes
    else:
        return []

def transformSpectrumLiquidity(transactionJson: json) -> list[KoinlyTX]:
    potentialLiquidity = None
    for output in transactionJson["outputs"]:
        if output["address"] not in state.ownAddresses and output["spentTransactionId"] in state.transactionsJson.keys():
            for input in state.transactionsJson[output["spentTransactionId"]]["inputs"]:
                if input["address"] in Config.config["spectrumPoolContracts"]:
                    potentialLiquidity = output["spentTransactionId"]
    if potentialLiquidity:
        sentBalance = inOutBalance(transactionJson)
        receivedBalance = inOutBalance(state.transactionsJson[potentialLiquidity])
        combinedBalance = sentBalance + receivedBalance
        sentAssets = combinedBalance.outgoingAssets()
        receivedAssets = combinedBalance.incomingAssets()
        t = state.transactionsJson[potentialLiquidity]["timestamp"]
        if len(sentAssets) == 1 and len(receivedAssets) == 2: #Liquidity removed
            state.handledTransactions.append(potentialLiquidity)
            firstHalfPrice = getTokenPrice(receivedAssets[0]["tokenId"], t) if receivedAssets[0]["tokenId"] else state.getErgoPrice(t)
            secondHalfPrice = getTokenPrice(receivedAssets[1]["tokenId"], t) if receivedAssets[1]["tokenId"] else state.getErgoPrice(t)
            return [
                KoinlyTX(
                    date=datetime.fromtimestamp(state.transactionsJson[potentialLiquidity]["timestamp"]/1000,tz=timezone.utc),
                    sentAmount=sentAssets[0]["amount"]/2,
                    sentCurrency=sentAssets[0]["currency"],
                    receivedAmount=abs(receivedAssets[0]["amount"]),
                    receivedCurrency=receivedAssets[0]["currency"],
                    feeAmount='' if combinedBalance.dust() == 0 else combinedBalance.dust()/2,
                    feeCurrency='' if combinedBalance.dust() == 0 else 'erg',
                    netWorthAmount=round(firstHalfPrice*receivedAssets[0]["amount"],2),
                    netWorthCurrency="USD",
                    label='Liquidity Out',
                    txHash=potentialLiquidity
                ),
                KoinlyTX(
                    date=datetime.fromtimestamp(state.transactionsJson[potentialLiquidity]["timestamp"]/1000,tz=timezone.utc),
                    sentAmount=sentAssets[0]["amount"]/2,
                    sentCurrency=sentAssets[0]["currency"],
                    receivedAmount=abs(receivedAssets[1]["amount"]),
                    receivedCurrency=receivedAssets[1]["currency"],
                    feeAmount='' if combinedBalance.dust() == 0 else combinedBalance.dust()/2,
                    feeCurrency='' if combinedBalance.dust() == 0 else 'erg',
                    netWorthAmount=round(secondHalfPrice*receivedAssets[1]["amount"],2),
                    netWorthCurrency="USD",
                    label='Liquidity Out',
                    txHash=potentialLiquidity
                )
            ]
        elif len(sentAssets) == 2 and len(receivedAssets) == 1: #Liquidity deposited
            state.handledTransactions.append(potentialLiquidity)
            firstHalfPrice = getTokenPrice(sentAssets[0]["tokenId"], t) if sentAssets[0]["tokenId"] else state.getErgoPrice(t)
            secondHalfPrice = getTokenPrice(sentAssets[1]["tokenId"], t) if sentAssets[1]["tokenId"] else state.getErgoPrice(t)
            return [
                KoinlyTX(
                    date=datetime.fromtimestamp(state.transactionsJson[potentialLiquidity]["timestamp"]/1000,tz=timezone.utc),
                    sentAmount=sentAssets[0]["amount"],
                    sentCurrency=sentAssets[0]["currency"],
                    receivedAmount=abs(receivedAssets[0]["amount"]/2),
                    receivedCurrency=receivedAssets[0]["currency"],
                    feeAmount='' if combinedBalance.dust() == 0 else combinedBalance.dust()/2,
                    feeCurrency='' if combinedBalance.dust() == 0 else 'erg',
                    netWorthAmount=round(firstHalfPrice*sentAssets[0]["amount"],2),
                    netWorthCurrency="USD",
                    label='Liquidity In',
                    txHash=potentialLiquidity
                ),
                KoinlyTX(
                    date=datetime.fromtimestamp(state.transactionsJson[potentialLiquidity]["timestamp"]/1000,tz=timezone.utc),
                    sentAmount=sentAssets[1]["amount"],
                    sentCurrency=sentAssets[1]["currency"],
                    receivedAmount=abs(receivedAssets[0]["amount"]/2),
                    receivedCurrency=receivedAssets[0]["currency"],
                    feeAmount='' if combinedBalance.dust() == 0 else combinedBalance.dust()/2,
                    feeCurrency='' if combinedBalance.dust() == 0 else 'erg',
                    netWorthAmount=round(secondHalfPrice*sentAssets[1]["amount"],2),
                    netWorthCurrency="USD",
                    label='Liquidity In',
                    txHash=potentialLiquidity
                )
            ]

    return []

def transformManyOn1Trades(transactionJson: json) -> list[KoinlyTX]:
    potentialTrade = None
    for output in transactionJson["outputs"]:
        if output["address"] not in state.allOwnAddresses and output["spentTransactionId"] in state.transactionsJson.keys():
            potentialTrade = output["spentTransactionId"]
    if potentialTrade:
        sentBalance = inOutBalance(transactionJson)
        receivedBalance = inOutBalance(state.transactionsJson[potentialTrade])
        combinedBalance = sentBalance + receivedBalance
        outgoingAssets = combinedBalance.outgoingAssets()
        incomingAssets = combinedBalance.incomingAssets()
        t = state.transactionsJson[potentialTrade]["timestamp"]
        if len(incomingAssets) == 1 and len(outgoingAssets) == 1:
            description = ''
            sentAmount = outgoingAssets[0]["amount"]
            sentCurrency = outgoingAssets[0]["currency"]
            if outgoingAssets[0]["currency"] != "erg":
                tokenName = state.getTokenName(outgoingAssets[0]["tokenId"])
                description += f'{outgoingAssets[0]["currency"]}={tokenName}'
            receivedAmount = abs(incomingAssets[0]["amount"])
            receivedCurrency = incomingAssets[0]["currency"]
            if incomingAssets[0]["currency"] != "erg":
                tokenName = state.getTokenName(incomingAssets[0]["tokenId"])
                description += f' {incomingAssets[0]["currency"]}={tokenName}'

            if combinedBalance.dust() > 0:
                feeAmount = combinedBalance.dust()
                feeCurrency = "erg"
            else:
                feeAmount = ''
                feeCurrency = ''
            receivedPrice = getTokenPrice(receivedCurrency, t) if receivedCurrency!="erg" else state.getErgoPrice(t)
            sentPrice = getTokenPrice(sentCurrency, t) if sentCurrency!="erg" else state.getErgoPrice(t)
            pricesFound = 0
            totalWorth = Decimal(0)
            if receivedPrice > 0:
                totalWorth += receivedPrice*receivedAmount
                pricesFound += 1
            if sentPrice > 0:
                totalWorth += sentPrice*sentAmount
                pricesFound += 1
            
            if incomingAssets[0]["tokenId"]:
                if "Vesting Key" in state.getTokenName(incomingAssets[0]["tokenId"]):
                    state.vesting[incomingAssets[0]["tokenId"]] = Vesting(round(totalWorth/pricesFound if pricesFound > 0 else Decimal(0),2), None)
            
            state.handledTransactions.append(potentialTrade)

            return [KoinlyTX(
                date=datetime.fromtimestamp(t/1000,tz=timezone.utc),
                sentAmount=sentAmount,
                sentCurrency=sentCurrency,
                receivedAmount=receivedAmount,
                receivedCurrency=receivedCurrency,
                feeAmount=feeAmount,
                feeCurrency=feeCurrency,
                netWorthAmount=round(totalWorth/pricesFound if pricesFound > 0 else Decimal(0),2),
                netWorthCurrency="USD",
                description=description,
                txHash=potentialTrade
            )]
        elif len(incomingAssets) == 1 and len(outgoingAssets) > 1:
            netWorthAmount = Decimal(0)
            for outgoingAsset in outgoingAssets:
                netWorthAmount += abs(outgoingAsset["amount"]) * (getTokenPrice(outgoingAsset["tokenId"], t) if outgoingAsset["tokenId"] else state.getErgoPrice(t))
            result = transformDefault(transactionJson,mergeWith=potentialTrade)+transformDefault(state.transactionsJson[potentialTrade], netWorthAmount=netWorthAmount)
            state.handledTransactions.append(potentialTrade)
            return result
    return []

def transformDefault(transactionJson: json, netWorthAmount: Decimal = None, mergeWith: str = None) -> list[KoinlyTX]:
    result = []
    if transactionJson["id"] in state.handledTransactions:
        return result
    registerJson = state.transactionsJson[mergeWith] if mergeWith else transactionJson
    balance = inOutBalance(transactionJson) 
    for token in balance.tokens:
        if balance.tokens[token] != 0:
            price = getTokenPrice(token,transactionJson["timestamp"])
            tokenName = state.getTokenName(token)
            if balance.tokens[token] > 0:
                result.append(KoinlyTX(
                    date=datetime.fromtimestamp(registerJson["timestamp"]/1000,tz=timezone.utc),
                    sentAmount=balance.tokens[token],
                    sentCurrency=state.koinlyToken(token),
                    netWorthAmount=round(netWorthAmount if netWorthAmount else balance.tokens[token]*price,2),
                    netWorthCurrency="usd",
                    description=f"{state.koinlyToken(token)}={tokenName}",
                    txHash=registerJson["id"]
                    )
                )
                balance.fee = 0
            elif balance.tokens[token] < 0:
                if "Vesting Key" in state.getTokenName(token):
                    if netWorthAmount:
                        vestingCostBasis = netWorthAmount
                    else:
                        vestingCostBasis = Decimal(0)
                        for ass in balance.outgoingAssets():
                            vestingCostBasis += abs(ass["amount"])*(getTokenPrice(ass["tokenId"],transactionJson["timestamp"]) if ass["tokenId"] else state.getErgoPrice(transactionJson["timestamp"]))
                    state.vesting[token] = Vesting(vestingCostBasis, None)
                result.append(KoinlyTX(
                    date=datetime.fromtimestamp(registerJson["timestamp"]/1000,tz=timezone.utc),
                    receivedAmount=(-1*balance.tokens[token]),
                    receivedCurrency=state.koinlyToken(token),
                    netWorthAmount=round(netWorthAmount if netWorthAmount else -1*balance.tokens[token]*price,2),
                    netWorthCurrency="usd",
                    description=f"{state.koinlyToken(token)}={tokenName}",
                    txHash=registerJson["id"]
                    )
                )
    if balance.value > 0:
        result.append(KoinlyTX(
            date=datetime.fromtimestamp(registerJson["timestamp"]/1000,tz=timezone.utc),
            sentAmount=balance.value,
            sentCurrency="erg",
            txHash=registerJson["id"]
            )
        )
    elif balance.value < 0:
        result.append(KoinlyTX(
            date=datetime.fromtimestamp(registerJson["timestamp"]/1000,tz=timezone.utc),
            receivedAmount=(-1*balance.value),
            receivedCurrency="erg",
            txHash=registerJson["id"]
            )
        )
    return result

