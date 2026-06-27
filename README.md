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

## ZeroTier 远程访问详细教程

如果你的手机和电脑在同一个 Wi-Fi 下面，不需要看这一节，直接使用局域网入口即可。

如果你人在外面，例如手机用的是流量、公司 Wi-Fi、学校 Wi-Fi，而电脑放在宿舍或家里，这时手机通常不能直接访问电脑。ZeroTier 的作用，就是把手机和电脑放进同一个“虚拟局域网”里。你可以把它理解成：

```text
普通 Wi-Fi：
手机和电脑连到同一个路由器，所以它们能互相访问。

ZeroTier：
手机和电脑虽然不在同一个地方，但都加入同一个 ZeroTier 网络。
ZeroTier 会给它们各自分配一个虚拟内网 IP，让它们像在同一个路由器下面一样互相访问。
```

这里最重要的是一句话：

```text
手机和电脑必须加入同一个 ZeroTier Network ID，并且都要在 ZeroTier 后台授权。
```

### 你需要准备什么

- 一台正在运行 `Codex Phone` 的 Windows 电脑
- 电脑端 ZeroTier
- 手机端 ZeroTier One
- 一个 ZeroTier 账号
- 一个 ZeroTier Network ID

Android 用户如果已经拿到了 `ZeroTier One` 的 APK，可以直接安装这个 APK。iPhone 用户需要通过 App Store 安装 `ZeroTier One`。

### 第一步：创建 ZeroTier 网络

1. 打开 ZeroTier Central：
   `https://my.zerotier.com/`
2. 注册或登录账号。
3. 进入 `Networks` 页面。
4. 点击 `Create A Network`。
5. 创建后会看到一个很长的 `Network ID`，类似：

```text
8056c2e21c000001
```

这个 `Network ID` 就像一个虚拟房间号。后面电脑和手机都要填写同一个 ID。

建议保持网络为 `Private`。这样新设备加入后不会自动放行，必须由你在后台手动授权，更安全。

### 第二步：让 Windows 电脑加入这个网络

1. 在电脑上安装并启动 ZeroTier。
2. 找到 Windows 右下角托盘里的 ZeroTier 图标。
3. 右键 ZeroTier 图标。
4. 选择 `Join New Network...`。
5. 粘贴刚刚复制的 `Network ID`。
6. 点击确认。

这一步完成后，电脑只是“申请加入”了网络，还不能马上使用。你还需要去网页后台授权。

### 第三步：在 ZeroTier 后台授权电脑

1. 回到 `https://my.zerotier.com/`。
2. 打开刚才创建的网络。
3. 往下找到 `Members` 列表。
4. 你会看到刚刚加入的电脑设备。
5. 勾选这一行前面的 `Auth` 或 `Authorized`。
6. 建议顺手给它改个名字，例如：

```text
dorm-windows-pc
```

授权后，ZeroTier 会给这台电脑分配一个虚拟 IP，通常长得像：

```text
10.147.20.35
```

这个 IP 才是后面要填进 `Codex Phone` 的 ZeroTier IP。注意，不要填手机的 IP，也不要填 `127.0.0.1`。

### 第四步：让手机加入同一个网络

#### Android

1. 安装 `ZeroTier One` APK。
2. 打开 `ZeroTier One`。
3. 点击添加网络的按钮，通常是 `+`。
4. 填入同一个 `Network ID`。
5. 保存。
6. 打开这个网络的开关。
7. 如果系统提示要创建 VPN 连接，选择允许。

Android 上 ZeroTier 通常会以 VPN 的形式运行，这是正常的。它不是传统意义上用来翻墙的 VPN，而是用来创建一个虚拟局域网。

#### iPhone / iPad

1. 安装 `ZeroTier One`。
2. 打开 `ZeroTier One`。
3. 添加网络。
4. 填入同一个 `Network ID`。
5. 打开网络开关。
6. 如果系统提示添加 VPN 配置，选择允许。

### 第五步：在 ZeroTier 后台授权手机

手机加入网络后，也需要授权：

1. 回到 `https://my.zerotier.com/`。
2. 打开你的 ZeroTier 网络。
3. 在 `Members` 列表里找到手机。
4. 勾选 `Auth` 或 `Authorized`。
5. 建议改个名字，例如：

```text
my-android-phone
```

到这里，电脑和手机就已经在同一个 ZeroTier 虚拟局域网里了。

你可以这样理解现在的关系：

```text
ZeroTier Network ID
├─ Windows 电脑，已授权，ZeroTier IP：10.147.20.35
└─ 手机，已授权，ZeroTier IP：10.147.20.88
```

手机要访问的是电脑，所以 `Codex Phone` 里应该填写电脑的 ZeroTier IP，例如 `10.147.20.35`。

### 第六步：回到 Codex Phone 配置远程入口

1. 先在电脑上启动 `Codex Phone`。
2. 打开本地管理页：

```text
http://127.0.0.1:8787/admin
```

3. 选择远程访问 / ZeroTier 场景。
4. 在 `ZeroTier IP` 里填写电脑的 ZeroTier IP，例如：

```text
10.147.20.35
```

5. 端口保持默认：

```text
8787
```

6. 选择立即启用。
7. 点击保存并检测。

检测通过后，页面会生成手机入口，类似：

```text
http://10.147.20.35:8787/?token=xxxxxxxx
```

把这个地址复制到手机浏览器里打开，就可以在外面访问电脑上的 `Codex Phone` 了。

### 常见问题

#### 1. 手机已经加入 ZeroTier，为什么还是打不开？

先检查这几件事：

- 电脑端 `Codex Phone` 是否正在运行
- 管理页里的端口是否是 `8787`
- 手机和电脑是否加入的是同一个 `Network ID`
- 手机和电脑是否都在 ZeroTier 后台勾选了授权
- 填进 `Codex Phone` 的是不是电脑的 ZeroTier IP
- Windows 防火墙是否允许 Python / Codex Phone 在网络中通信

#### 2. 我应该填哪个 IP？

填写电脑的 ZeroTier IP。

不要填这些：

```text
127.0.0.1             这是电脑自己访问自己，手机不能用
192.168.x.x           这通常是家里或宿舍 Wi-Fi 的局域网 IP，人在外面不一定能用
手机的 ZeroTier IP    手机是访问者，不是被访问的电脑
```

应该填类似这样的电脑 ZeroTier IP：

```text
10.x.x.x
```

#### 3. ZeroTier 后台里设备显示在线，但仍然打不开？

可能是 Windows 防火墙拦住了。你可以先在电脑浏览器确认本机服务能打开：

```text
http://127.0.0.1:8787/admin
```

如果本机能打开，但手机打不开，重点检查：

- Windows 防火墙
- ZeroTier 是否已连接
- ZeroTier 后台是否已授权
- `Codex Phone` 是否监听在 `0.0.0.0:8787`

#### 4. 使用 ZeroTier 安全吗？

ZeroTier 网络建议保持 `Private`，并且只授权你自己的电脑和手机。

`Codex Phone` 本身也会给手机入口加上 `token`。不要把带 token 的链接发给别人，也不要把 token 提交到 GitHub。

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
