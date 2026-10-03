import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (personal research script)"}
OUT_DIR = Path("data")


def to_num(text):
    text = text.replace(",", "").replace("%", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def read_table(soup, section_id):
    """Return {row label: {column header: value}} for a Screener section."""
    section = soup.find("section", id=section_id)
    table = section.find("table", class_="data-table")
    cols = [th.get_text(strip=True) for th in table.find("thead").find_all("th")][1:]
    data = {}
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        label = cells[0].get_text(strip=True).rstrip("+").strip()
        data[label] = {c: to_num(td.get_text()) for c, td in zip(cols, cells[1:])}
    return data


def fetch(ticker):
    for suffix in ("consolidated/", ""):
        url = f"https://www.screener.in/company/{ticker}/{suffix}"
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser")
    raise RuntimeError(f"Could not load Screener page for {ticker}")


def net_debt_ebitda(ticker):
    soup = fetch(ticker)
    bs = read_table(soup, "balance-sheet")
    pl = read_table(soup, "profit-loss")
    borrowings, investments = bs["Borrowings"], bs.get("Investments", {})
    op_profit = pl["Operating Profit"]
    series = []
    for year, debt in borrowings.items():
        ebitda = op_profit.get(year)
        if not year.startswith("Mar") or debt is None or not ebitda or ebitda <= 0:
            continue
        ratio = (debt - (investments.get(year) or 0)) / ebitda
        series.append({"x": year, "y": round(ratio, 2)})
    return series


def main():
    tickers = [t.upper() for t in sys.argv[1:]]
    if not tickers:
        sys.exit("Usage: python fetch_screener.py TICKER [TICKER ...]")
    OUT_DIR.mkdir(exist_ok=True)
    failures = 0
    for t in tickers:
        try:
            payload = {
                "ticker": t,
                "metric": "Net Debt / EBITDA (x)",
                "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "series": net_debt_ebitda(t),
            }
            (OUT_DIR / f"{t}.json").write_text(json.dumps(payload, indent=2))
            print(f"{t}: saved {len(payload['series'])} points")
        except Exception as e:
            failures += 1
            print(f"{t}: failed ({type(e).__name__}: {e})")
    if failures == len(tickers):
        sys.exit(1)


if __name__ == "__main__":
    main()
