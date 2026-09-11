import argparse
import urllib.request
import urllib.error
import sys


def main():
    # 定義命令列參數
    parser = argparse.ArgumentParser(description="Simple curl-like tool")
    parser.add_argument("url", help="URL to fetch")
    # -v: 顯示請求與回應的詳細資訊
    parser.add_argument("-v", "--verbose", action="store_true", help="Print request details")
    # -X: 指定 HTTP 方法（GET、POST、PUT、DELETE 等）
    parser.add_argument("-X", "--request", default="GET", help="HTTP method (default: GET)")
    # -H: 自訂 Header，可重複使用多次，格式 key:value
    parser.add_argument("-H", "--header", action="append", default=[], help="Custom header (key:value), repeatable")
    # -d: POST/PUT/DELETE 時附帶的請求資料
    parser.add_argument("-d", "--data", default=None, help="Data to send with the request")
    args = parser.parse_args()

    # 解析所有 -H 參數，轉成 dict
    headers = {}
    for h in args.header:
        if ":" in h:
            key, value = h.split(":", 1)
            headers[key.strip()] = value.strip()

    # 如果有 -d 資料，預設 Content-Type 為 form-urlencoded
    data = None
    if args.data is not None:
        data = args.data.encode("utf-8")
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/x-www-form-urlencoded"

    # 將方法轉成大寫，建立 Request 物件
    method = args.request.upper()
    req = urllib.request.Request(args.url, data=data, headers=headers, method=method)

    # -v 模式：印出送出的請求資訊
    if args.verbose:
        print(f"> {req.method} {req.full_url}")
        for k, v in req.header_items():
            print(f"> {k}: {v}")
        if data:
            print(f">")
            print(f"> {args.data}")
        print(">", end="\n\n")

    try:
        # 執行請求並讀取回應
        with urllib.request.urlopen(req) as response:
            # -v 模式：印出回應狀態碼與 Header
            if args.verbose:
                print(f"< HTTP/{response.version / 10:.1f} {response.status}")
                for k, v in response.headers.items():
                    print(f"< {k}: {v}")
                print("<", end="\n\n")
            # 輸出回應內容
            print(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        # 伺服器回傳錯誤狀態碼（4xx、5xx）
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        # 無法連線到目標主機
        print(f"URL Error: {e.reason}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
