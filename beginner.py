"""從台股與比特幣公開日線學習指標與現貨回測。"""
import argparse
import json
import math
import os
import ssl
import subprocess
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from urllib.error import URLError
from urllib.request import urlopen

FEE = 0.001425  # 模擬手續費
SELL_TAX = 0.003  # 此範例的普通股賣出稅率假設


def fetch_days(stock):
    today = datetime.now(timezone(timedelta(hours=8))).date()
    # 從昨天所在月份往前查；月初也能直接從上個月開始。
    month = (today - timedelta(days=1)).replace(day=1)
    prices = {}
    for _ in range(8):
        url = ("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
               f"?response=json&date={month:%Y%m%d}&stockNo={stock}")
        try:
            with urlopen(url, timeout=20) as response:
                report = json.load(response)
        except URLError as error:
            if os.name != "nt" or not isinstance(error.reason, ssl.SSLCertVerificationError):
                raise
            # Windows curl 可使用系統憑證庫，仍須通過 HTTPS 驗證。
            raw = subprocess.check_output(["curl.exe", "-fsS", "--max-time", "20", url])
            report = json.loads(raw)
        if report["stat"] != "OK":
            if month.month == today.month and "沒有符合" in report["stat"]:
                month = (month - timedelta(days=1)).replace(day=1)
                continue
            raise ValueError(f"{month:%Y-%m}：{report['stat']}")
        fields = report["fields"]
        for row in report["data"]:
            year, m, d = map(int, row[fields.index("日期")].split("/"))
            day = date(year + 1911, m, d)
            if day >= today:
                continue
            opening, closing = (float(row[fields.index(key)].replace(",", ""))
                                for key in ("開盤價", "收盤價"))
            if not all(math.isfinite(p) and p > 0 for p in (opening, closing)):
                raise ValueError(f"{day} 價格無效")
            if day in prices:
                raise ValueError(f"{day} 日期重複")
            prices[day] = (opening, closing)
        if len(prices) >= 120:
            return [(day, *prices[day]) for day in sorted(prices)[-120:]]
        month = (month - timedelta(days=1)).replace(day=1)
    raise ValueError("資料不足 120 個交易日")



def fetch_btc_days():
    DAY = 86400
    end = int(datetime.now(timezone.utc).timestamp()) // DAY * DAY
    start = end - 120 * DAY
    url = (f"https://api.bitopro.com/v3/trading-history/btc_twd"
           f"?resolution=1d&from={start}&to={end - 1}")
    with urlopen(url, timeout=20) as response:
        rows = json.load(response)["data"]
    prices = {}
    for row in rows:
        stamp = int(row["timestamp"])
        opening, closing = float(row["open"]), float(row["close"])
        if not all(math.isfinite(price) and price > 0 for price in (opening, closing)):
            raise ValueError("開盤或收盤價無效")
        if stamp in prices and prices[stamp] != (opening, closing):
            raise ValueError("同一天出現兩組不同價格")
        prices[stamp] = (opening, closing)
    days = []
    for second in range(start, end, DAY):
        date = datetime.fromtimestamp(second, timezone.utc).date()
        if second * 1000 not in prices:
            raise ValueError(f"{date} 缺少日線，請稍後重試")
        days.append((date, *prices[second * 1000]))
    return days


def backtest(days, indicator, period, crypto=False):
    fee = 0.001 if crypto else FEE
    sell_tax = 0 if crypto else SELL_TAX
    closes = [close for date, opening, close in days]
    cash, quantity = 10000.0, 0
    trades = []
    for today in range(max(period + 1, len(days) - 59), len(days)):
        date, opening, closing = days[today]
        yesterday = closes[today - 1]
        if indicator == "ma":
            value = mean(closes[today - period:today])
            hold = yesterday > value
        else:
            value = (yesterday / closes[today - 1 - period] - 1) * 100
            hold = value > 0
        if hold and quantity == 0:
            quantity = cash / (opening * (1 + fee))
            if not crypto:
                quantity = int(quantity)
            if quantity == 0:
                continue
            cash -= quantity * opening * (1 + fee)
            trades.append((date, "買入", opening, value))
        elif not hold and quantity > 0:
            cash += quantity * opening * (1 - fee - sell_tax)
            quantity = 0
            trades.append((date, "賣出", opening, value))
    equity = cash + quantity * closes[-1] * (1 - fee - sell_tax)
    return trades, equity


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--indicator", choices=["ma", "roc"], default="ma")
    parser.add_argument("--period", type=int, default=20)
    assets = parser.add_mutually_exclusive_group()
    assets.add_argument("--btc", action="store_true", help="使用幣託 BTC/TWD 日線")
    assets.add_argument("--stock", choices=["2330", "2317"], default="2330", help="2330 台積電或 2317 鴻海")
    args = parser.parse_args()
    if not 2 <= args.period <= 60:
        parser.error("週期請輸入 2 到 60 的整數")
    label = "BTC/TWD（UTC）" if args.btc else f"上市普通股 {args.stock}"
    try:
        days = fetch_btc_days() if args.btc else fetch_days(args.stock)
    except (OSError, URLError, ValueError, TypeError, KeyError, IndexError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"無法讀取{label}日線：{error}\n")
    trades, equity = backtest(days, args.indicator, args.period, crypto=args.btc)
    print(f"{label}｜{days[0][0]} 至 {days[-1][0]}｜{len(days)} 根日線")
    print(f"{args.indicator.upper()} {args.period} 個交易日｜首個可成交日 {days[-59][0]}")
    for date, action, price, signal in trades:
        print(f"{date} {action}  開盤價 {price:,.2f}  前一天指標 {signal:,.2f}")
    print(f"買賣訊號成交 {len(trades)} 次｜本金 10,000 TWD｜期末淨值 {equity:,.2f} TWD")
    print(f"扣費報酬率 {(equity / 10000 - 1):.2%}")


if __name__ == "__main__":
    main()
