"""Kiểm tra nhanh các service đã lên: python tests/smoke_health.py [--dev]
Mặc định chỉ kiểm tra Web (:8000, cổng duy nhất mở ra ngoài). --dev kiểm tra thêm 3 service backend
(cần docker-compose.override.yml, mặc định đã được nạp)."""
import argparse
import json
import sys
import urllib.request

TARGETS = {"web": 8000}
DEV_TARGETS = {"user": 8001, "tuition": 8002, "payment": 8003}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true", help="kiểm tra cả User, Tuition, Payment")
    args = ap.parse_args()
    targets = {**TARGETS, **(DEV_TARGETS if args.dev else {})}
    failed = 0
    for name, port in targets.items():
        url = f"http://127.0.0.1:{port}/health"
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                ok = r.status == 200 and json.load(r).get("status") == "ok"
        except Exception as exc:  # noqa: BLE001
            ok, err = False, exc
        print(f"[{'OK ' if ok else 'FAIL'}] {name:8s} {url}" + ("" if ok else f"  ({err})"))
        failed += 0 if ok else 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
