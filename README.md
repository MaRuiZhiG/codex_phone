<img width="1254" height="1254" alt="CodexPhonelogo" src="https://github.com/user-attachments/assets/22cdf115-7889-47fe-9d75-75aecab50c5e" />

# Codex Phone

`Codex Phone` 可以让你用手机网页控制 Windows 电脑上的 `Codex Desktop`。

你可以把它理解成：

```text
手机浏览器
  ↓
Codex Phone
  ↓
电脑上的 Codex Desktop
```

适合这些场景：

- 人不在电脑前，但想用手机给 Codex 发消息
- 想把手机里的文字或图片发给电脑上的 Codex
- 想在宿舍、家里、办公室之外远程操作自己的 Codex

如果你只是想先用起来，不需要理解代码，也不需要安装 Python。下载 Windows 安装包后启动即可。

## 先看这个：我应该选哪种连接方式？

Codex Phone 有两种常见用法。
<img width="650" height="325" alt="f10b9fdf-0193-4f2b-95cc-1d90e2c21d36" src="https://github.com/user-attachments/assets/7a617f26-47ce-46c6-b780-2cf06ae01b29" />

### 方式一：手机和电脑在同一个 Wi-Fi 下

这是最简单的方式，推荐第一次使用先选这个。

例如：

```text
电脑连着宿舍 Wi-Fi
手机也连着同一个宿舍 Wi-Fi
```

这时你只需要：

1. 在电脑上启动 `Codex Phone`
2. 打开管理页
3. 选择 `我和电脑就在同一个 Wi-Fi 里`
4. 复制页面给出的手机入口
5. 在手机浏览器里打开

### 方式二：人在外面，想远程访问电脑

例如：

```text
电脑在宿舍或家里
手机在外面，用的是流量或别的 Wi-Fi
```

这时手机通常不能直接访问电脑，需要额外的远程连接方案。

目前 Codex Phone 支持 `ZeroTier` 组网。ZeroTier 会把手机和电脑放进同一个虚拟局域网里，让手机像在同一个 Wi-Fi 下那样访问电脑。

如果你是第一次使用，建议先把同 Wi-Fi 模式跑通，再配置 ZeroTier 远程模式。

## Windows 用户安装和启动

### 第一步：下载

到 GitHub Releases 下载 Windows 安装器：

```text
CodexPhoneSetup-版本号-windows-x64.exe
```

如果同时看到 `.zip` 和 `.exe`，普通用户优先下载 `.exe` 安装器。

### 第二步：安装

双击安装器，按提示下一步即可。

安装器会：

- 安装 Codex Phone
- 创建桌面快捷方式
- 创建开始菜单快捷方式
- 提供卸载入口

### 第三步：启动

安装完成后，双击桌面上的：

```text
Codex Phone
```

程序会在电脑本机启动一个服务，并自动打开管理页。

如果没有自动打开，可以手动访问：

```text
http://127.0.0.1:8787/admin
```

## 第一次使用：同 Wi-Fi 模式

这是最推荐的入门方式。

### 1. 确认电脑和手机连的是同一个 Wi-Fi

例如：

```text
电脑：宿舍 Wi-Fi
手机：宿舍 Wi-Fi
```

不要让手机使用流量，也不要让手机连到另一个 Wi-Fi。

### 2. 打开 Codex Phone 管理页

在电脑上打开：

```text
http://127.0.0.1:8787/admin
```

### 3. 选择使用场景

选择：

```text
我和电脑就在同一个 Wi-Fi 里
```

页面会自动生成一个手机入口，类似：

```text
http://192.168.1.23:8787/?token=xxxxxxxx
```

### 4. 在手机浏览器打开这个入口

把页面里的入口复制到手机浏览器。

打开后，你就可以在手机上：

- 查看 Codex 线程
- 切换线程
- 新建线程
- 发送文字
- 上传图片
- 查看 Codex 回复

## 远程使用：ZeroTier 模式

如果手机和电脑不在同一个 Wi-Fi 下，就需要 ZeroTier。

### ZeroTier 是什么？

普通 Wi-Fi 是这样的：

```text
手机和电脑连到同一个路由器
所以它们能互相访问
```

ZeroTier 是这样的：

```text
手机和电脑虽然不在同一个地方
但它们都加入同一个 ZeroTier 网络
ZeroTier 给它们分配虚拟内网 IP
于是它们就像在同一个路由器下面
```

你可以把 ZeroTier 的 `Network ID` 理解成一个“虚拟房间号”。

只有加入同一个房间，并且被你授权的设备，才能互相访问。

最重要的一句话：

```text
电脑和手机必须加入同一个 ZeroTier Network ID，并且都要在 ZeroTier 后台授权。
```

### 你需要准备

- Windows 电脑上的 Codex Phone
- 电脑端 ZeroTier
- 手机端 ZeroTier One
- 一个 ZeroTier 账号
- 一个 ZeroTier Network ID

Android 用户如果已经拿到了 `ZeroTier One` APK，可以直接安装 APK。

iPhone / iPad 用户需要安装 `ZeroTier One`。

## ZeroTier 详细配置教程

### 第一步：创建 ZeroTier 网络

1. 打开 ZeroTier Central：

```text
https://my.zerotier.com/
```

2. 注册或登录账号。
3. 进入 `Networks` 页面。
4. 点击 `Create A Network`。
5. 创建后复制 `Network ID`。

`Network ID` 通常长这样：

```text
8056c2e21c000001
```

建议保持网络为 `Private`。这样新设备加入后不会自动放行，必须由你手动授权，更安全。

### 第二步：让电脑加入 ZeroTier 网络

1. 在 Windows 电脑上安装并启动 ZeroTier。
2. 找到右下角托盘里的 ZeroTier 图标。
3. 右键 ZeroTier 图标。
4. 选择 `Join New Network...`。
5. 粘贴刚刚复制的 `Network ID`。
6. 点击确认。

注意：这一步只是让电脑“申请加入网络”，还没有真正放行。下一步必须去网页后台授权。

### 第三步：在后台授权电脑

1. 回到：

```text
https://my.zerotier.com/
```

2. 打开刚才创建的网络。
3. 往下找到 `Members` 列表。
4. 找到刚刚加入的 Windows 电脑。
5. 勾选 `Auth` 或 `Authorized`。
6. 可以给电脑改个名字，例如：

```text
dorm-windows-pc
```

授权后，ZeroTier 会给电脑分配一个虚拟 IP，通常像这样：

```text
10.147.20.35
```

这个 IP 很重要。后面 Codex Phone 里要填写的是“电脑的 ZeroTier IP”。

不要填这些：

```text
127.0.0.1             这是电脑自己访问自己，手机不能用
192.168.x.x           这是普通 Wi-Fi 局域网 IP，人在外面通常不能用
手机的 ZeroTier IP    手机是访问者，不是被访问的电脑
```

### 第四步：让手机加入同一个 ZeroTier 网络

#### Android

1. 安装 `ZeroTier One` APK。
2. 打开 `ZeroTier One`。
3. 点击添加网络，通常是 `+`。
4. 填入同一个 `Network ID`。
5. 保存。
6. 打开这个网络的开关。
7. 如果系统提示创建 VPN 连接，选择允许。

Android 上 ZeroTier 会以 VPN 的形式运行，这是正常的。这里的 VPN 不是用来浏览外网，而是用来创建虚拟局域网。

#### iPhone / iPad

1. 安装 `ZeroTier One`。
2. 打开 `ZeroTier One`。
3. 添加网络。
4. 填入同一个 `Network ID`。
5. 打开网络开关。
6. 如果系统提示添加 VPN 配置，选择允许。

### 第五步：在后台授权手机

手机加入网络后，也要授权：

1. 回到 ZeroTier Central。
2. 打开你的网络。
3. 在 `Members` 列表里找到手机。
4. 勾选 `Auth` 或 `Authorized`。
5. 可以给手机改个名字，例如：

```text
my-android-phone
```

到这里，电脑和手机就已经在同一个 ZeroTier 虚拟局域网里了。

它们的关系类似这样：

```text
ZeroTier Network ID
├─ Windows 电脑，已授权，ZeroTier IP：10.147.20.35
└─ 手机，已授权，ZeroTier IP：10.147.20.88
```

手机要访问电脑，所以 Codex Phone 里应该填写：

```text
10.147.20.35
```

也就是电脑的 ZeroTier IP。

### 第六步：回到 Codex Phone 配置远程入口

1. 在电脑上启动 `Codex Phone`。
2. 打开管理页：

```text
http://127.0.0.1:8787/admin
```

3. 选择远程 / ZeroTier 场景。
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

把这个地址复制到手机浏览器里打开，就可以远程访问电脑上的 Codex Phone。

## 常见问题

### 手机打不开入口怎么办？

先按下面顺序检查：

1. 电脑上的 `Codex Phone` 是否正在运行。
2. 电脑浏览器能否打开 `http://127.0.0.1:8787/admin`。
3. 手机和电脑是否在同一个 Wi-Fi，或者是否都加入了同一个 ZeroTier 网络。
4. ZeroTier 后台里电脑和手机是否都已授权。
5. Codex Phone 里填写的是不是电脑的 ZeroTier IP。
6. Windows 防火墙是否允许 Codex Phone 通信。

### 管理页里的 token 是什么？

`token` 是访问密码。

手机入口通常长这样：

```text
http://电脑IP:8787/?token=xxxxxxxx
```

不要把带 token 的链接发给别人，也不要把 token 提交到 GitHub。

### 为什么我填了 ZeroTier IP，手机还是打不开？

最常见原因有三个：

- 填成了手机的 ZeroTier IP
- 手机或电脑没有在 ZeroTier 后台授权
- Windows 防火墙拦住了 8787 端口

你应该填写电脑的 ZeroTier IP。

### 我不想用 ZeroTier，可以吗？

可以。

如果手机和电脑在同一个 Wi-Fi 下，直接用局域网模式即可。

如果你想在国内更简单地远程访问，也可以考虑内网穿透工具。它们通常只需要电脑端配置，手机直接打开公网链接。但不同工具的配置方式不一样，当前 Codex Phone 主要内置的是局域网和 ZeroTier 配置。

## 给开发者看的内容

如果你只是安装使用，下面内容可以不看。

### 从源码运行

要求：

- Windows
- 已安装并至少运行过一次 `Codex Desktop`
- Python 3.11+
- 可访问本地 `~/.codex` 会话目录

安装依赖：

```powershell
python -m pip install -r requirements.txt
```

启动：

```powershell
python -m app.main
```

或者：

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port 8787
```

### 页面地址

- 手机聊天页：

```text
http://127.0.0.1:8787/?token=<token>
```

- 本地管理页：

```text
http://127.0.0.1:8787/admin
```

### 项目结构

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

### 工作原理

整体链路大致如下：

1. 手机网页把文本或图片发给本地 FastAPI 服务。
2. 服务端校验 `token`。
3. 服务端读取本地 Codex 会话数据，确定目标线程。
4. 服务端调用 Windows 自动化，把 `Codex Desktop` 切到前台。
5. 服务端把文本或图片写入系统剪贴板并模拟粘贴、发送。
6. `Codex Desktop` 真正执行任务。
7. 服务端轮询 `.codex/sessions` 中的线程历史和状态。
8. 手机网页同步显示最新回复和运行进度。

### 环境变量

- `CODEX_PHONE_PORT`
- `CODEX_PHONE_HOST`
- `CODEX_PHONE_STATE_DIR`
- `CODEX_PHONE_UPLOAD_DIR`
- `CODEX_PHONE_LOG_FILE`
- `CODEX_PHONE_DESKTOP_LOGS_DIR`
- `CODEX_PHONE_FOCUS_SETTLE_MS`
- `CODEX_PHONE_DEEPLINK_SETTLE_MS`
- `CODEX_PHONE_CLICK_SETTLE_MS`
- `CODEX_PHONE_COMPOSER_BOTTOM_OFFSET
