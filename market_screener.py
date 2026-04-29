import requests
import yfinance as yf
import pandas as pd
import yaml
from pathlib import Path
from datetime import datetime


def load_config(config_path="config.yaml"):
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Missing config file: {config_path}. Create config.yaml in the same folder."
        )

    with open(path, "r") as f:
        return yaml.safe_load(f)


CONFIG = load_config()


def get_us_stock_universe():
    urls = CONFIG["data_sources"]["symbol_directory_urls"]
    symbols = []

    for url in urls:
        text = requests.get(url, timeout=CONFIG["runtime"]["request_timeout_seconds"]).text
        rows = text.strip().split("\n")
        header = rows[0].split("|")

        for row in rows[1:]:
            parts = row.split("|")
            if len(parts) != len(header):
                continue

            record = dict(zip(header, parts))

            symbol = record.get("Symbol") or record.get("ACT Symbol")
            name = record.get("Security Name", "")
            etf = record.get("ETF", "N")

            if not symbol:
                continue

            symbol = symbol.replace(".", "-")

            if etf == CONFIG["stock_universe"]["exclude_etf_flag"]:
                continue

            bad_words = CONFIG["stock_universe"]["exclude_name_keywords"]
            if any(word.lower() in name.lower() for word in bad_words):
                continue

            symbols.append(symbol)

    return sorted(list(set(symbols)))


def analyze_stock(ticker):
    stock_cfg = CONFIG["stock_screen"]

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(
            period=stock_cfg["history_period"],
            interval=stock_cfg["history_interval"]
        )

        min_history_days = max(
            stock_cfg["avg_volume_window"],
            stock_cfg["ma_short_window"],
            stock_cfg["ma_medium_window"],
            stock_cfg["ma_long_window"],
            stock_cfg["return_3m_window"],
            stock_cfg["volatility_window"],
        )

        if hist.empty or len(hist) < min_history_days:
            return None

        price = hist["Close"].iloc[-1]
        avg_volume = hist["Volume"].rolling(stock_cfg["avg_volume_window"]).mean().iloc[-1]

        if price < stock_cfg["min_price"]:
            return None

        if avg_volume < stock_cfg["min_avg_volume"]:
            return None

        ma_short = hist["Close"].rolling(stock_cfg["ma_short_window"]).mean().iloc[-1]
        ma_medium = hist["Close"].rolling(stock_cfg["ma_medium_window"]).mean().iloc[-1]
        ma_long = hist["Close"].rolling(stock_cfg["ma_long_window"]).mean().iloc[-1]

        ret_1m = hist["Close"].pct_change(stock_cfg["return_1m_window"]).iloc[-1]
        ret_3m = hist["Close"].pct_change(stock_cfg["return_3m_window"]).iloc[-1]
        volatility = hist["Close"].pct_change().rolling(stock_cfg["volatility_window"]).std().iloc[-1]

        dollar_volume = price * avg_volume

        score = 0
        score += stock_cfg["score_weights"]["price_above_short_ma"] if price > ma_short else 0
        score += stock_cfg["score_weights"]["price_above_medium_ma"] if price > ma_medium else 0
        score += stock_cfg["score_weights"]["price_above_long_ma"] if price > ma_long else 0
        score += stock_cfg["score_weights"]["positive_1m_return"] if ret_1m > 0 else 0
        score += stock_cfg["score_weights"]["positive_3m_return"] if ret_3m > 0 else 0
        score += stock_cfg["score_weights"]["low_volatility"] if volatility < stock_cfg["max_volatility_for_bonus"] else 0
        score += stock_cfg["score_weights"]["high_dollar_volume"] if dollar_volume > stock_cfg["min_dollar_volume_for_bonus"] else 0

        max_score = sum(stock_cfg["score_weights"].values())

        return {
            "Ticker": ticker,
            "Price": round(price, stock_cfg["round_price_digits"]),
            "Avg Volume": int(avg_volume),
            "Dollar Volume": int(dollar_volume),
            "1M Return %": round(ret_1m * 100, stock_cfg["round_percent_digits"]),
            "3M Return %": round(ret_3m * 100, stock_cfg["round_percent_digits"]),
            "Volatility": round(volatility, stock_cfg["round_volatility_digits"]),
            "Score": score,
            "Max Score": max_score,
        }

    except Exception:
        return None


def screen_stocks():
    stock_cfg = CONFIG["stock_screen"]
    symbols = get_us_stock_universe()

    max_symbols = stock_cfg["max_symbols_to_scan"]
    if max_symbols:
        symbols = symbols[:max_symbols]

    rows = []

    for i, ticker in enumerate(symbols, start=1):
        result = analyze_stock(ticker)
        if result:
            rows.append(result)

        if (
            CONFIG["output"]["include_progress_logs"]
            and i % CONFIG["output"]["progress_log_every_n_symbols"] == 0
        ):
            print(f"Processed {i}/{len(symbols)} symbols...", flush=True)

    df = pd.DataFrame(rows)

    if df.empty:
        return df

    return df.sort_values(
        stock_cfg["sort_columns"],
        ascending=stock_cfg["sort_ascending"]
    )


def get_options_for_ticker(ticker):
    opt_cfg = CONFIG["options_screen"]

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=opt_cfg["underlying_history_period"])

        if hist.empty:
            return None

        price = hist["Close"].iloc[-1]
        expiries = stock.options

        if not expiries:
            return None

        start = opt_cfg["expiries_start_index"]
        end = opt_cfg["expiries_end_index"]
        selected_expiries = expiries[start:end] if len(expiries) > start else expiries[:opt_cfg["fallback_expiry_count"]]

        all_rows = []

        for expiry in selected_expiries:
            try:
                chain = stock.option_chain(expiry)

                calls = chain.calls.copy()
                puts = chain.puts.copy()

                calls["Type"] = opt_cfg["call_label"]
                puts["Type"] = opt_cfg["put_label"]

                df = pd.concat([calls, puts], ignore_index=True)

                if df.empty:
                    continue

                df["Ticker"] = ticker
                df["Underlying Price"] = price
                df["Expiry"] = expiry

                df["volume"] = df["volume"].fillna(opt_cfg["missing_volume_fill"])
                df["openInterest"] = df["openInterest"].fillna(opt_cfg["missing_open_interest_fill"])

                df["Mid"] = (df["bid"] + df["ask"]) / opt_cfg["mid_price_divisor"]
                df = df[df["Mid"] > opt_cfg["min_mid_price"]]

                df["Spread %"] = (df["ask"] - df["bid"]) / df["Mid"]
                df["Distance %"] = abs(df["strike"] - price) / price

                df = df[
                    (df["bid"] >= opt_cfg["min_bid"]) &
                    (df["ask"] >= opt_cfg["min_ask"]) &
                    (df["volume"] >= opt_cfg["min_volume"]) &
                    (df["openInterest"] >= opt_cfg["min_open_interest"]) &
                    (df["Spread %"] <= opt_cfg["max_spread_pct"]) &
                    (df["Distance %"] <= opt_cfg["max_distance_pct"])
                ]

                if not df.empty:
                    all_rows.append(df)

            except Exception:
                continue

        if not all_rows:
            return None

        df = pd.concat(all_rows, ignore_index=True)

        df["Option Score"] = (
            opt_cfg["score_weights"]["volume_rank"] * df["volume"].rank(pct=True) +
            opt_cfg["score_weights"]["open_interest_rank"] * df["openInterest"].rank(pct=True) -
            opt_cfg["score_weights"]["spread_penalty"] * df["Spread %"].rank(pct=True) -
            opt_cfg["score_weights"]["distance_penalty"] * df["Distance %"].rank(pct=True)
        )

        return df

    except Exception:
        return None


def screen_options(stock_df):
    if stock_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    opt_cfg = CONFIG["options_screen"]
    option_rows = []

    scan_df = stock_df.head(CONFIG["stock_screen"]["option_scan_top_stocks"])

    for ticker in scan_df["Ticker"].tolist():
        result = get_options_for_ticker(ticker)
        if result is not None and not result.empty:
            option_rows.append(result)

    if not option_rows:
        return pd.DataFrame(), pd.DataFrame()

    options_df = pd.concat(option_rows, ignore_index=True)

    top_calls = (
        options_df[options_df["Type"] == opt_cfg["call_label"]]
        .sort_values(opt_cfg["sort_column"], ascending=opt_cfg["sort_ascending"])
        .head(opt_cfg["top_calls_to_show"])
    )

    top_puts = (
        options_df[options_df["Type"] == opt_cfg["put_label"]]
        .sort_values(opt_cfg["sort_column"], ascending=opt_cfg["sort_ascending"])
        .head(opt_cfg["top_puts_to_show"])
    )

    return top_calls, top_puts


def format_output():
    stock_cfg = CONFIG["stock_screen"]
    output_cfg = CONFIG["output"]

    all_stock_candidates = screen_stocks()
    top_stocks = all_stock_candidates.head(stock_cfg["top_stocks_to_show"]) if not all_stock_candidates.empty else pd.DataFrame()

    top_calls, top_puts = screen_options(all_stock_candidates)

    msg = []
    msg.append(output_cfg["title"])
    msg.append(f"Generated: {datetime.now().strftime(output_cfg['datetime_format'])}")
    msg.append("")
    msg.append(output_cfg["disclaimer"])
    msg.append(output_cfg["universe_note"])
    msg.append(output_cfg["criteria_note"])
    msg.append("")

    msg.append(output_cfg["stocks_header"])
    if top_stocks.empty:
        msg.append(output_cfg["no_stocks_message"])
    else:
        for i, row in enumerate(top_stocks.to_dict("records"), 1):
            msg.append(
                f"{i}. {row['Ticker']} | ${row['Price']} | "
                f"1M: {row['1M Return %']}% | "
                f"3M: {row['3M Return %']}% | "
                f"Score: {row['Score']}/{row['Max Score']}"
            )

    msg.append("")
    msg.append(output_cfg["calls_header"])
    if top_calls.empty:
        msg.append(output_cfg["no_calls_message"])
    else:
        for i, row in enumerate(top_calls.to_dict("records"), 1):
            msg.append(
                f"{i}. {row['Ticker']} {row['Expiry']} "
                f"${row['strike']} CALL | "
                f"Bid/Ask: {row['bid']}/{row['ask']} | "
                f"Vol: {int(row['volume'])} | "
                f"OI: {int(row['openInterest'])}"
            )

    msg.append("")
    msg.append(output_cfg["puts_header"])
    if top_puts.empty:
        msg.append(output_cfg["no_puts_message"])
    else:
        for i, row in enumerate(top_puts.to_dict("records"), 1):
            msg.append(
                f"{i}. {row['Ticker']} {row['Expiry']} "
                f"${row['strike']} PUT | "
                f"Bid/Ask: {row['bid']}/{row['ask']} | "
                f"Vol: {int(row['volume'])} | "
                f"OI: {int(row['openInterest'])}"
            )

    return "\n".join(msg)


if __name__ == "__main__":
    print(format_output())