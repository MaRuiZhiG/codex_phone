# Codex Phone

`Codex Phone` 是一个面向 Windows 的本地桥接项目，用手机网页去远程操控电脑上的 `Codex Desktop`。

它的核心目标是：

- 用手机发送文本和图片
- 让本机服务把内容转发给 `Codex Desktop`
- 读取本地会话和状态日志
- 再把结果同步回手机网页

这个项目的思路和 `codex-mini` 类似，但实现方式完全针对 Windows 重写：

- 后端使用 `FastAPI + Uvicorn + Python`
- 桌面自动化基于 Windows GUI 控制
- 支持局域网和 ZeroTier 组网访问
- 提供手机聊天页和本地管理页

## Features

- 手机端聊天页面
- 本地管理页面
- `token` 鉴权
- Codex 线程列表读取
- 线程切换
- 新线程创建
- 文本发送
- 图片发送
- 历史记录回流
- 执行状态轮询
- ZeroTier 访问配置
- 本地日志记录

## How It Works

整体链路大致如下：

1. 手机网页把文本或图片发给本地 FastAPI 服务
2. 服务端校验 `token`
3. 服务端读取本地 Codex 会话数据，确定目标线程
4. 服务端调用 Windows 自动化，把 `Codex Desktop` 切到前台
5. 服务端把文本/图片写入系统剪贴板并模拟粘贴、发送
6. `Codex Desktop` 真正执行任务
7. 服务端轮询 `.codex/sessions` 中的线程历史和状态
8. 手机网页同步显示最新回复和运行进度

## Project Structure

```text
app/
  main.py              FastAPI 入口
  access_manager.py    局域网 / ZeroTier 访问状态管理
  codex_session.py     Codex 会话、历史、状态读取
  codex_models.py      Codex 模型配置读取与写入
  windows_gui.py       Windows GUI 自动化
  security.py          token 鉴权
  config.py            配置与路径加载
  schemas.py           请求与响应模型

static/
  index.html           手机聊天页
  admin.html           本地管理页
```

## Requirements

- Windows
- 已安装并至少运行过一次 `Codex Desktop`
- Python 3.11+
- 可访问本地 `~/.codex` 会话目录

## Install

```powershell
python -m pip install -r requirements.txt
```

## Run

推荐启动方式：

```powershell
python -m app.main
```

或者：

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8787
```

启动后默认监听：

```text
http://127.0.0.1:8787
```

## Pages

- 手机聊天页：
  `http://127.0.0.1:8787/?token=<token>`
- 本地管理页：
  `http://127.0.0.1:8787/admin`

如果走局域网或 ZeroTier，就把 `127.0.0.1` 换成对应 IP。

## Token

首次启动后，程序会自动生成 token，默认保存在：

```text
%USERPROFILE%\.codex-phone\token.txt
```

手机访问时需要把 token 带在 URL 中，例如：

```text
http://<your-ip>:8787/?token=<token>
```

## Access Modes

当前主要支持两种使用方式：

- 局域网
- ZeroTier 组网

本地管理页可以帮助你：

- 查看当前可用地址
- 切换推荐访问模式
- 配置 ZeroTier IP
- 复制手机访问链接

## Useful Environment Variables

- `CODEX_PHONE_PORT`
- `CODEX_PHONE_HOST`
- `CODEX_PHONE_STATE_DIR`
- `CODEX_PHONE_UPLOAD_DIR`
- `CODEX_PHONE_LOG_FILE`
- `CODEX_PHONE_DESKTOP_LOGS_DIR`
- `CODEX_PHONE_FOCUS_SETTLE_MS`
- `CODEX_PHONE_DEEPLINK_SETTLE_MS`
- `CODEX_PHONE_CLICK_SETTLE_MS`
- `CODEX_PHONE_COMPOSER_BOTTOM_OFFSET`

## Notes

- 当前桌面输入框定位仍然依赖窗口区域和点击偏移，不是严格的 UI 元素级定位
- 需要 `Codex Desktop` 已正确安装并能正常打开线程
- 建议不要把本地状态目录、日志、token、`.codex` 会话数据提交到 GitHub

## Recommended Files To Commit

建议提交这些内容：

- `app/`
- `static/`
- `requirements.txt`
- `README.md`
- `.gitignore`

不建议提交这些内容：

- `.idea/`
- `__pycache__/`
- `*.pyc`
- `*.log`
- 临时截图
- 本地 token / 状态文件
