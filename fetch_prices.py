"""부자금고 시세 파일 만들기 (GitHub Actions에서 하루 한 번 실행)"""
import json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

KEY = os.environ.get("DATA_GO_KR_KEY", "").strip()
if not KEY:
    sys.exit("DATA_GO_KR_KEY 가 없습니다. 저장소 Settings > Secrets 에 넣어 주십시오.")
if "%" in KEY:
    KEY = urllib.parse.unquote(KEY)

BASE = "https://apis.data.go.kr/1160100/service"
SOURCES = [
    ("주식", [BASE + "/GetStockSecuritiesInfoService/getStockPriceInfo",
             "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2"]),
    ("ETF", [BASE + "/GetSecuritiesProductInfoService/getETFPriceInfo",
            "https://apis.data.go.kr/1160100/GetSecuritiesProductInfoService_V2/getETFPriceInfo_V2"]),
]
KST = timezone(timedelta(hours=9))


def call(url, params):
    q = urllib.parse.urlencode({"serviceKey": KEY, "resultType": "json", **params})
    req = urllib.request.Request(url + "?" + q, headers={"User-Agent": "bujageumgo-price-feed"})
    err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode("utf-8"))
            return body["response"]["body"]
        except Exception as e:
            err = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{url} 호출 실패: {err}")


def items_of(body):
    it = (body.get("items") or {}).get("item") or []
    return it if isinstance(it, list) else [it]


def fetch_day(urls, basdt):
    for url in urls:
        try:
            out, page = [], 1
            while True:
                body = call(url, {"basDt": basdt, "numOfRows": 3000, "pageNo": page})
                rows = items_of(body)
                out += rows
                total = int(body.get("totalCount") or 0)
                if not rows or len(out) >= total:
                    break
                page += 1
            return out
        except Exception as e:
            print("  다음 주소로 시도:", e)
    return []


def main():
    today = datetime.now(KST).date()
    prices, used_day = {}, None
    for back in range(1, 12):
        day = today - timedelta(days=back)
        basdt = day.strftime("%Y%m%d")
        got = {}
        for name, urls in SOURCES:
            rows = fetch_day(urls, basdt)
            print(f"{basdt} {name}: {len(rows)}개")
            for r in rows:
                code = str(r.get("srtnCd", "")).strip()
                nm = str(r.get("itmsNm", "")).strip()
                try:
                    close = int(float(str(r.get("clpr", "0")).replace(",", "")))
                except ValueError:
                    continue
                if code and nm and 0 < close < 1_000_000_000:
                    got[code.lstrip("A")] = [nm, close]
        if len(got) > 500:
            prices, used_day = got, day
            break
    if not prices:
        sys.exit("최근 거래일 시세를 찾지 못했습니다. 기존 prices.json 은 그대로 둡니다.")
    data = {"v": 1, "d": used_day.isoformat(), "src": "금융위원회 주식시세정보·증권상품시세정보 (공공데이터포털)",
            "n": len(prices), "c": dict(sorted(prices.items()))}
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"저장: {used_day} 종가 {len(prices)}개 종목")


if __name__ == "__main__":
    main()
