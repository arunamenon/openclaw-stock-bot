#!/bin/bash

cd "$(dirname "$0")"

# activate virtual env
source .venv/bin/activate

# run screener
python3 market_screener.py
