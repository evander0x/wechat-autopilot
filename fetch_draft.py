#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出 / 拉取公众号草稿箱（batchget + get）。

用法：
    python fetch_draft.py list [--count 20] [--json]
    python fetch_draft.py get <media_id> [-o draft_live.json]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests

HOME = Path.home() / ".wewrite"


def load_credentials() -> dict:
    f = HOME / "config.yaml"
    cfg = {}
    if f.exists():
        text = f.read_text(encoding="utf-8")
        for key in ("appid", "secret"):
            m = re.search(rf"{key}:\s*[\"']?([^\"'\n#]+)", text)
            if m:
                cfg[key] = m.group(1).strip()
    for k, var in (("appid", "WECHAT_APPID"), ("secret", "WECHAT_SECRET")):
        if os.environ.get(var):
            cfg[k] = os.environ[var]
    if not cfg.get("appid") or not cfg.get("secret"):
        sys.exit("✗ 缺少凭证：~/.wewrite/config.yaml 需要 wechat.appid/secret")
    return cfg


def get_token(cfg):
    r = requests.get(
        "https://api.weixin.qq.com/cgi-bin/token",
        params={
            "grant_type": "client_credential",
            "appid": cfg["appid"],
            "secret": cfg["secret"],
        },
        timeout=15,
    )
    r.encoding = "utf-8"
    data = r.json()
    if "access_token" not in data:
        sys.exit(f"✗ token 失败：{data}")
    return data["access_token"]


def post(path, token, payload):
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/{path}",
        params={"access_token": token},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    r.encoding = "utf-8"
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["list", "get"])
    ap.add_argument("media_id", nargs="?")
    ap.add_argument("--count", type=int, default=20)
    ap.add_argument("-o", "--output", default="draft_live.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    token = get_token(load_credentials())

    if args.action == "list":
        data = post("draft/batchget", token,
                    {"offset": 0, "count": args.count, "no_content": 1})
        if data.get("errcode"):
            sys.exit(f"✗ 列草稿失败：{data}")
        items = data.get("item", [])
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return
        print(f"共 {data.get('total_count', 0)} 条草稿，本页 {len(items)} 条：\n")
        for i, it in enumerate(items, 1):
            news = it.get("content", {}).get("news_item", [])
            title = news[0].get("title") if news else "(无标题)"
            ts = it.get("update_time", 0)
            import datetime
            when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
            print(f"[{i}] {when}  {title}")
            print(f"    media_id: {it.get('media_id')}")
        return

    if not args.media_id:
        sys.exit("✗ get 需要 media_id")
    data = post("draft/get", token, {"media_id": args.media_id})
    if data.get("errcode"):
        sys.exit(f"✗ 拉取草稿失败：{data}")
    Path(args.output).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for a in data.get("news_item", []):
        print(f"标题: {a.get('title')}")
        print(f"作者: {a.get('author')} | 摘要: {a.get('digest')}")
        print(f"正文长度: {len(a.get('content', ''))} 字符")
        print(f"更新时间: {a.get('update_time')}")
    print(f"→ 已保存 {args.output}")


if __name__ == "__main__":
    main()
