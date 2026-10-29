#!/usr/bin/env python3
"""
summarize.py —— 读 collect.js 的输出，打印计数；详情图拿不到时打印诊断。

退出码：0 = 拿到详情图；2 = 只有主图/买家秀；1 = 连主图都没拿到

用法：
    python3 summarize.py raw.json
"""

import json
import sys


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return {}
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return {"reason": "output_not_json", "raw_head": raw[:200]}
    # CLI 会把返回值再包一层 JSON 字符串
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except json.JSONDecodeError:
            return {"reason": "inner_not_json", "raw_head": d[:200]}
    return d if isinstance(d, dict) else {}


def main():
    d = load(sys.argv[1]) if len(sys.argv) > 1 else {}
    n_main = len(d.get("main") or [])
    n_detail = len(d.get("detail") or [])
    n_bs = len(d.get("buyershow") or [])

    print(f"product_id={d.get('product_id')} promotion_id={d.get('promotion_id')}")
    print(f"主图 {n_main} / 详情图 {n_detail} / 买家秀 {n_bs}")

    if n_detail:
        sys.exit(0)

    reason = d.get("reason")
    if d.get("status_code") not in (None, 0):
        print(f"详情接口 status_code={d.get('status_code')} {d.get('status_msg') or ''}")
    if reason:
        print(f"原因: {reason}")
    if d.get("hint"):
        print(f"提示: {d['hint']}")
    for t in (d.get("tried") or []):
        print(f"  候选#{t.get('i')} → {t.get('code')} {str(t.get('msg'))[:60]}")

    sys.exit(2 if (n_main or n_bs) else 1)


if __name__ == "__main__":
    main()
