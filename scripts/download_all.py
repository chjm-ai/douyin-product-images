#!/usr/bin/env python3
"""
download_all.py —— 依据 collect.js 产出的 JSON 下载抖音商品三类图片。

用法：
    python3 download_all.py raw.json ~/Desktop/抖音图片_山趣橡果灯

输入 raw.json 可以是：
  - collect.js 原样输出（含 \\" 转义的 JSON 字符串）
  - 已解析的 JSON 对象
脚本会自动兼容这两种情况。
"""

import json
import os
import subprocess
import sys
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
REFERER = "https://haohuo.jinritemai.com/"
HOSTS = ["p26-item.ecombdimg.com", "p3-item.ecombdimg.com", "p9-item.ecombdimg.com"]

# 各类型的 URL 模板：越靠前越优先
TEMPLATES = {
    "detail": ["~tplv-5mmsx3fupr-image.png",
               "~tplv-5mmsx3fupr-resize:750:3000.jpeg"],
    "main": ["~tplv-5mmsx3fupr-resize_q:1080:1080:q90.webp",
             "~tplv-5mmsx3fupr-image.png"],
}


def load_payload(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    data = json.loads(raw)
    # collect.js 的返回值会被 CLI 再包一层 JSON 字符串
    if isinstance(data, str):
        data = json.loads(data)
    if isinstance(data, dict) and "result" in data and isinstance(data["result"], str):
        data = json.loads(data["result"])
    return data


def fetch(url, depth=0):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": REFERER})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.read()
    except Exception as e:
        if depth < len(HOSTS):
            # 换节点重试：把主机名替换为下一个 CDN 节点
            host = url.split("/")[2]
            nxt = HOSTS[depth % len(HOSTS)]
            if host != nxt:
                return fetch(url.replace("//" + host + "/", "//" + nxt + "/", 1), depth + 1)
        raise e


def save_binary(data, out_path):
    with open(out_path, "wb") as f:
        f.write(data)


def convert_to_jpg(src, dst):
    """macOS 上用 sips 转格式；失败则保留原文件。"""
    try:
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "95",
                        src, "--out", dst],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def download_group(uris, out_dir, kind, prefix):
    os.makedirs(out_dir, exist_ok=True)
    ok = 0
    for i, uri in enumerate(uris, 1):
        # 详情图 / 主图是 uri，拼 CDN 地址 + 模板
        suffixes = TEMPLATES.get(kind, [""]) if not uri.startswith("http") else [""]
        base = uri if uri.startswith("http") else f"https://{HOSTS[0]}/img/{uri}"
        done = False
        for suf in suffixes:
            if uri.startswith("http"):
                url = uri
            else:
                # 先去掉 uri 上可能已带的模板，避免叠加
                url = base.split("~tplv")[0] + suf
            try:
                data = fetch(url)
            except Exception:
                continue
            if len(data) < 1024:
                continue
            ext = ".png" if url.endswith(".png") else (".webp" if ".webp" in url else ".jpg")
            tmp = os.path.join(out_dir, f".tmp_{prefix}_{i:02d}{ext}")
            save_binary(data, tmp)
            final_base = os.path.join(out_dir, f"{prefix}_{i:02d}")
            if kind == "detail" and ext == ".png":
                os.replace(tmp, final_base + ".png")
            else:
                # 主图 webp / 买家秀 heic → 统一转 jpg，方便打开
                if not convert_to_jpg(tmp, final_base + ".jpg"):
                    os.replace(tmp, final_base + ext)
                else:
                    os.remove(tmp)
            ok += 1
            done = True
            break
        if not done:
            print(f"  ! 跳过 {prefix}_{i:02d}: {uri[:70]}")
    return ok


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    payload = load_payload(sys.argv[1])
    out_root = os.path.expanduser(sys.argv[2])

    main_imgs = payload.get("main") or []
    detail_imgs = payload.get("detail") or []
    buyershow = payload.get("buyershow") or []

    print(f"商品: product_id={payload.get('product_id')} "
          f"promotion_id={payload.get('promotion_id')}")
    print(f"主图 {len(main_imgs)} / 详情图 {len(detail_imgs)} / 买家秀 {len(buyershow)}")

    if not payload.get("ok") and not detail_imgs:
        print(f"  ! 详情接口未成功: {payload.get('reason')} status={payload.get('status_code')}")

    n1 = download_group(main_imgs, out_root, "main", "主图") if main_imgs else 0
    n2 = download_group(detail_imgs, os.path.join(out_root, "详情图"),
                        "detail", "详情") if detail_imgs else 0
    n3 = download_group(buyershow, os.path.join(out_root, "详情页_买家秀"),
                        "buyershow", "买家秀") if buyershow else 0

    print(f"\n完成 → {out_root}")
    print(f"  主图   {n1}/{len(main_imgs)}")
    print(f"  详情图 {n2}/{len(detail_imgs)}")
    print(f"  买家秀 {n3}/{len(buyershow)}")


if __name__ == "__main__":
    main()
