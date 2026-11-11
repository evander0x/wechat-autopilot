#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_draft.py — 把「编辑手记」排版的 HTML 直接推到公众号草稿箱

与 wewrite publish 的区别：本脚本不做二次转换，正文 HTML 原样上传，
因此草稿箱里的样式 == wechat_layout.py 的输出。

用法（建议用 wewrite 的 venv 运行，自带 requests/yaml）：
    ~/wewrite/.venv/bin/python push_draft.py article.fragment.html \
        --cover cover.png --title "标题" [--digest "摘要"] [--author "署名"]

凭证来源：~/.wewrite/config.yaml 的 wechat.appid / secret / author，
也可用环境变量 WECHAT_APPID / WECHAT_SECRET 覆盖。

注意：会真实写入草稿箱（不影响已发布内容）；标题 ≤64 字，摘要 ≤120 字节。
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
    cfg = {}
    f = HOME / "config.yaml"
    if f.exists():
        text = f.read_text(encoding="utf-8")
        for key in ("appid", "secret", "author"):
            m = re.search(rf"{key}:\s*[\"']?([^\"'\n#]+)", text)
            if m:
                cfg[key] = m.group(1).strip()
    env = {"appid": "WECHAT_APPID", "secret": "WECHAT_SECRET", "author": "WECHAT_AUTHOR"}
    for k, var in env.items():
        if os.environ.get(var):
            cfg[k] = os.environ[var]
    if not cfg.get("appid") or not cfg.get("secret"):
        sys.exit("✗ 缺少凭证：请在 ~/.wewrite/config.yaml 填 wechat.appid/secret")
    return cfg


def api_get(url: str):
    r = requests.get(url, timeout=15)
    r.encoding = "utf-8"  # 微信返回的 JSON 不带 charset，requests 会误判为 latin-1
    return r.json()


def api_post_json(url: str, payload: dict):
    # 必须显式 ensure_ascii=False：requests 的 json= 默认把中文转成 \uXXXX，
    # 微信会把转义序列原样存下来，草稿里显示成 "\u62d2\u7edd" 而不是「拒绝」。
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = requests.post(url, data=body, headers={"Content-Type": "application/json"}, timeout=30)
    r.encoding = "utf-8"
    return r.json()


def upload_cover(token: str, cover: Path) -> str:
    """封面传永久素材库，返回 media_id（草稿 thumb_media_id 要求永久素材）。"""
    url = f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={token}&type=image"
    with open(cover, "rb") as fh:
        r = requests.post(url, files={"media": fh}, timeout=60)
    data = r.json()
    if "media_id" not in data:
        sys.exit(f"✗ 封面上传失败：{data}")
    return data["media_id"]


def upload_content_images(token: str, content: str) -> str:
    """正文里的本地图片逐张传 media/uploadimg（10MB 内），src 替换为微信 URL。

    微信会剥离正文中的外链图片，所以必须先换成微信域名的 URL。
    """
    def repl(m):
        src = m.group(1)
        if src.startswith(("http://", "https://")) and "mmbiz.qpic.cn" not in src:
            print(f"⚠ 跳过外链图片（微信会剥离）：{src[:60]}")
            return m.group(0)
        if src.startswith("http"):
            return m.group(0)  # 已是微信 URL
        path = Path(src)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.exists():
            sys.exit(f"✗ 正文图片不存在：{path}")
        url = f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={token}"
        with open(path, "rb") as fh:
            r = requests.post(url, files={"media": fh}, timeout=60)
        data = r.json()
        if "url" not in data:
            sys.exit(f"✗ 正文图片上传失败：{data}")
        print(f"→ 正文图片已上传：{path.name}")
        return m.group(0).replace(src, data["url"])

    return re.sub(r'<img[^>]+src="([^"]+)"', repl, content)


def main():
    ap = argparse.ArgumentParser(description="HTML → 公众号草稿箱")
    ap.add_argument("input", help="wechat_layout.py --fragment 产出的正文 HTML")
    ap.add_argument("--cover", required=True, help="封面图（建议 900×383）")
    ap.add_argument("--title", required=True, help="标题，≤64 字")
    ap.add_argument("--digest", default="", help="摘要，≤120 字节（约 40 个汉字）")
    ap.add_argument("--author", default="")
    args = ap.parse_args()

    cfg = load_credentials()
    title_bytes = len(args.title.encode("utf-8"))
    if title_bytes > 78:
        sys.exit(f"✗ 标题过长（{title_bytes} 字节）。实测超过约 80 字节微信会报 45003，"
                 "建议控制在 25 个汉字以内")
    digest = args.digest
    if len(digest.encode("utf-8")) > 120:
        sys.exit("✗ 摘要超过 120 字节（约 40 个汉字）")
    author = args.author or cfg.get("author", "")

    token_resp = api_get(
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={cfg['appid']}&secret={cfg['secret']}"
    )
    if "access_token" not in token_resp:
        sys.exit(f"✗ 获取 token 失败：{token_resp}")
    token = token_resp["access_token"]

    print("→ 上传封面…")
    thumb = upload_cover(token, Path(args.cover))

    content = Path(args.input).read_text(encoding="utf-8")
    content = upload_content_images(token, content)
    payload = {
        "articles": [
            {
                "title": args.title,
                "author": author,
                "digest": digest,
                "content": content,
                "thumb_media_id": thumb,
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
            }
        ]
    }
    print("→ 新建草稿…")
    resp = api_post_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={token}", payload
    )
    if resp.get("errcode"):
        sys.exit(f"✗ 建草稿失败：{resp}")

    media_id = resp["media_id"]
    print(f"✓ 草稿已创建 media_id: {media_id}")
    return media_id


if __name__ == "__main__":
    main()
