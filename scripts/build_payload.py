#!/usr/bin/env python3
"""
build_payload.py —— 把 `agent-browser network requests` 的输出转成 JS 前置赋值。

为什么需要它：
  - 同一次页面加载可能出现多条 pack/detail 请求，其中一部分不带 msToken，
    回放时只会返回空 body。所以要把候选 URL 全收集起来，让 collect.js 依次重试。
  - URL 里含 & ，用 sed 注入会被当成"整个匹配"展开；用 JSON 序列化才安全。

用法：
    agent-browser network requests --filter "pack/detail" | python3 build_payload.py
"""

import json
import re
import sys

# [67365.81] POST https://... (XHR) 200
LINE = re.compile(r"^\[[\d.]+\]\s+(?:POST|GET|PUT|PATCH)\s+(\S+)\s+\((?:XHR|Fetch)\)\s+\d+$")


def main():
    urls = []
    for raw in sys.stdin.read().splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        u = m.group(1)
        if u not in urls:
            urls.append(u)

    # 带 msToken 的签名更完整，排前面；其余作为兜底
    urls.sort(key=lambda u: 0 if "msToken" in u else 1)

    print("window.__DY_PACK_URLS__ = %s;" % json.dumps(urls, ensure_ascii=False))


if __name__ == "__main__":
    main()
