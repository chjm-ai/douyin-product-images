#!/usr/bin/env python3
"""
build_payload.py —— 把 `agent-browser network requests` 的输出转成 JS 前置赋值。

为什么需要它（两个真实的血坑）：
  1. URL 里含 & ，用 sed 注入会被当成"整个匹配"展开，把链接搅碎；必须 JSON 序列化。
  2. 同一次加载可能出现多条 pack/detail，签名强度不同：
     - 只有 `a_bogus`（约 44 字符）、没有 `msToken` → 回放必定返回空 body
     - 带 `msToken` 且 `a_bogus` 较长 → 才有机会拿到完整数据
     所以要把候选按"签名完整度"打分排序，弱签名留作兜底。

用法：
    agent-browser network requests --filter "pack/detail" | python3 build_payload.py
"""

import json
import re
import sys
import urllib.parse as up

# [67365.81] POST https://... (XHR) 200
LINE = re.compile(r"^\[[\d.]+\]\s+(?:POST|GET|PUT|PATCH)\s+(\S+)\s+\((?:XHR|Fetch)\)\s+\d+$")


def score(url):
    """签名完整度打分：越高越可能回放成功。"""
    q = up.parse_qs(up.urlparse(url).query)
    bogus = (q.get("a_bogus") or [""])[0]
    s = 0
    if "msToken" in q:
        s += 4                      # 决定性因素
    if len(bogus) > 80:
        s += 2                      # 短 bogus(≈44) 基本是废签
    if len(url) > 200:
        s += 1
    return s


def main():
    urls, seen = [], set()
    for raw in sys.stdin.read().splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        u = m.group(1)
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)

    # 稳定排序：高分在前，同分保持原序
    urls.sort(key=lambda u: -score(u))

    print("window.__DY_PACK_URLS__ = %s;" % json.dumps(urls, ensure_ascii=False))
    print("window.__DY_PACK_SCORES__ = %s;" % json.dumps([score(u) for u in urls]))


if __name__ == "__main__":
    main()
