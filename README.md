# wechat-autopilot

公众号全流程自动化 skill：**选题 → 写稿 → 审稿 → 排版 → 推草稿箱**。

给 AI Agent（WorkBuddy / Claude 类环境）用的编排层：内容判断（选题好不好、稿子行不行）由 Agent 按 [wewrite](https://github.com/imraywang/wewrite) 的标准执行，确定性操作（转 HTML、调微信 API）走本仓库脚本，不手搓。

## 内含脚本

| 脚本 | 作用 |
|---|---|
| `fetch_draft.py` | 拉取/备份草稿箱草稿（list / get），原文落盘 |
| `push_draft.py` | 推新草稿：上传封面与正文图片换微信 URL → `draft/add` → 回读校验 |
| `update_draft.py` | 安全覆盖已有草稿：**强制先备份远程原文** → 差异提示 → `draft/update`（media_id 不变） |

## 安装

```bash
ln -s /path/to/wechat-autopilot ~/.workbuddy/skills/wechat-autopilot
```

需要搭配 [wechat-editorial](https://github.com/evander0x/wechat-editorial)（排版层）使用；配合 [wewrite](https://github.com/imraywang/wewrite) 获得选题/写稿/审稿能力。一句话触发全流程：「写一篇 XX 主题的公众号文章推草稿箱」。

## 前置条件

- 公众号后台拿到 `appid` + `secret`，写入 `~/.wewrite/config.yaml`（权限 600）
- 把本机公网 IP 加入公众号开发者平台的 API IP 白名单
- 常见报错：`40164` IP 不在白名单、`48001` 账号无草稿权限（个人未认证号）、`45003` 标题超长

## 安全

- 凭证只从 `~/.wewrite/config.yaml` 运行时读取，**本仓库永不落 AppID/AppSecret**
- 默认不发布；明确授权才调草稿箱 API，推送后回读校验
- `update_draft.py` 强制「先拉取远程 → 备份 → 再覆盖」，防止手改内容丢失

完整文档见 [SKILL.md](SKILL.md)；主仓库与示例见 [autopilot-wechat](https://github.com/evander0x/autopilot-wechat)。

## License

MIT
