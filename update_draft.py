#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全更新公众号草稿：强制「先拉取远程 → 备份 → 再覆盖」（draft/get + draft/update）。

铁律：不拉取远程备份就绝不覆盖。远程原文永远先落盘，防止手改内容丢失。

用法：
    python update_draft.py <media_id> <content.fragment.html> \
        --title "标题" [--digest "摘要"] [--author ""] [--cover-media-id XXX]

流程：
    1. draft/get 拉取远程草稿 → 备份为 draft_remote_backup-<时间戳>.html + .json
    2. 对比远程与本地内容的文字差异并提示
    3. draft/update 覆盖（media_id 不变），失败时可用备份还原

凭证复用 ~/.wewrite/config.yaml（本项目不落任何密钥）。
"""

import argparse
import datetime
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


def post(token, path, payload):
    r = requests.post(
        f"https://api.weixin.qq.com/cgi-bin/{path}",
        params={"access_token": token},
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    r.encoding = "utf-8"
    return r.json()


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", "\n", html)
    return re.sub(r"\n{2,}", "\n", text).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media_id")
    ap.add_argument("content")
    ap.add_argument("--title", required=True)
    ap.add_argument("--digest", default="")
    ap.add_argument("--author", default="")
    ap.add_argument("--cover-media-id", required=True, help="永久素材 media_id（thumb_media_id）")
    ap.add_argument("--backup-dir", default=".", help="远程备份保存目录")
    args = ap.parse_args()

    title_bytes = len(args.title.encode("utf-8"))
    if title_bytes > 78:
        sys.exit(f"✗ 标题过长（{title_bytes} 字节）")
    if len(args.digest.encode("utf-8")) > 120:
        sys.exit("✗ 摘要超过 120 字节")

    cfg = load_credentials()
    token = get_token(cfg)

    # ---- 第一步：强制拉取远程草稿并备份（不成功绝不覆盖） ----
    remote = post(token, "draft/get", {"media_id": args.media_id})
    if remote.get("errcode"):
        sys.exit(f"✗ 拉取远程草稿失败，已中止（不覆盖）：{remote}")
    news = remote.get("news_item") or []
    if not news:
        sys.exit("✗ 远程草稿为空或结构异常，已中止（不覆盖）")
    remote_item = news[0]
    remote_content = remote_item.get("content", "")

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = Path(args.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_html = backup_dir / f"draft_remote_backup-{ts}.html"
    backup_json = backup_dir / f"draft_remote_backup-{ts}.json"
    backup_html.write_text(remote_content, encoding="utf-8")
    backup_json.write_text(
        json.dumps(remote, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"→ 远程草稿已备份：{backup_html.name} / {backup_json.name}")
    print(f"  远程标题：{remote_item.get('title')}")
    print(f"  远程正文：{len(remote_content)} 字符")

    # ---- 第二步：差异提示（远程有而本地没有的文字） ----
    local_html = Path(args.content).read_text(encoding="utf-8")
    local_words = set(strip_tags(local_html))
    remote_words = set(strip_tags(remote_content))
    only_remote = sorted(remote_words - local_words)
    if only_remote:
        sample = "、".join(only_remote[:8])
        print(f"⚠ 注意：远程有 {len(only_remote)} 处本地没有的文字片段，例如：{sample}")
        print("  如这些是你在后台手改的内容，请先并入本地源稿再覆盖。")

    # ---- 第三步：覆盖更新 ----
    payload = {
        "media_id": args.media_id,
        "index": 0,
        "articles": {
            "title": args.title,
            "author": args.author,
            "digest": args.digest,
            "content": local_html,
            "thumb_media_id": args.cover_media_id,
            "need_open_comment": 1,
            "only_fans_can_comment": 0,
        },
    }
    resp = post(token, "draft/update", payload)
    if resp.get("errcode"):
        sys.exit(f"✗ 更新草稿失败：{resp}")
    print(f"✓ 草稿已更新（media_id 不变）: {args.media_id}")
    print(f"  如需回滚：用 {backup_json.name} 里的 content 调 draft/update 即可还原")


if __name__ == "__main__":
    main()
