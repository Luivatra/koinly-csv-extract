# koinly-csv-extract
Extract of ergo transactions in koinly csv format. Please keep in mind this is a first version and probably will never be 100% correct in all cases. Make sure you do a sanity check once the csv is imported into Koinly.

## Features
- Breaks up multi asset transactions so each token gets imported into Koinly
- Assigns a name to each token/nft that is not known by Koinly and makes sure it is consistent between your wallets (NULL1, NULL2, NFT1, NFT2 etc.) Look in the description for transactions for which token it is about.
- Combines trades on fe. Spectrum into one exchange transaction in Koinly
- Fetches price of tokens with value to assign a networth to transactions in Koinly
- Ergopad vesting redeems are handled according to this description: [Koinly ICO transactions](https://help.koinly.io/en/articles/3732271-how-do-i-enter-ico-transactions)
- Ergopad staking transactions are handled according to this description: [Koinly Staking](https://help.koinly.io/en/articles/4928636-staking)

## Requirements
To use this tool you need to have [Python](https://www.python.org/) installed. Once it has been tested I will generate standalone executables to make it easier for the average user.

## Usage
1. Download the files in this repository using either git or just download (Green "Code" dropdown on top right -> "Download as zip")
2. In the folder with the downloaded files edit the file "wallets.json" with a text editor to match your needs.
3. *First use only* Install required Python packages with pip by calling this command:
```
pip install -r requirements.txt
``` 
4. Run the extraction, it will generate a csv for each wallet defined in wallets.json
```
python main.py extract
```

If you want to extract transactions in a specific block range only (fe. between block 123000 and 450000) you can add parameters like this:
```
python main.py extract 123000 450000
```