# 中国科学技术大学选课抢课

按优先级自动选课，适配 2026 新版教务系统，Windows / Linux 通用。

## ⚠️ 风险提示

自动抢课可能触发教务系统风控，导致账号受限，**后果自负**。建议先读一遍下面的「保护机制」。

## 核心逻辑

每轮按 `priority` 依次 POST `add-request` → `add-drop-response` 提交选课，由教务系统返回结果决定是否成功。

容量和已选人数**不作为**提交前置条件——真实系统里存在已选人数已超过 `limitCount` 的课程，用人数判断会白白错过。

叠加四道保护：**随机间隔**、**活跃时段**、**失败熔断**、**风控信号即停**；登录态失效时还会尝试自动重登。

## 快速开始

### 1. 安装环境（一次性）

**Windows**
```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

**Linux / macOS**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

### 2. 登录

在有图形界面的机器上执行一次，生成 `auth.json`（Playwright storage_state，含 cookie 与 localStorage）：

```bat
.venv\Scripts\python grabbing.py --login      :: Windows
.venv/bin/python grabbing.py --login          # Linux/macOS
```

`auth.json` 已在 gitignore 中，**不要提交**。

### 3. 配置

配置分两层，后者覆盖前者：

| 文件 | 用途 | 是否提交 |
|---|---|---|
| `config.json` | 通用设置模板 | ✅ |
| `config.local.json` | 你的个人信息：学号、邮箱、目标课程（照 `config.local.example.json` 填写） | ❌ 已忽略 |

建议把个人信息填进 `config.local.json`，让 `config.json` 保持为干净模板，避免误提交隐私。各字段含义见下方[配置字段](#配置字段)。

账号密码放 `.env`（照 `.env.example` 填写，同样已忽略），用于登录态失效后自动重登：

```
USTC_USERNAME=你的学号
USTC_PASSWORD=你的密码
COURSE_BOT_SMTP_PASSWORD=你的QQ邮箱SMTP授权码
```

> 若登录需要验证码、扫码或二次认证，程序会发邮件通知并停止——这些步骤无法也不应绕过。

### 4. 运行

```bat
.venv\Scripts\python grabbing.py              :: Windows
.venv/bin/python grabbing.py                  # Linux/macOS
```

## 配置字段

| 字段 | 说明 |
|---|---|
| `studentAssoc` | 学生关联 id；留空则从选课页 URL 自动解析 |
| `courseSelectTurnAssoc` | 选课轮次 id，**每学期变**。从选课页 URL `.../turn/<数字>/select` 中取 |
| `courses` | 目标课程数组。每项用 `lessonAssoc` 精确指定，或用 `name` + `teacher` 按名字匹配（教师支持逗号分隔多人）；`priority` 越小越优先，`allow_conflict` 控制是否允许已知时间冲突 |
| `batch_interval` | 同一轮内每笔请求的间隔区间（秒），默认 `[5, 15]` |
| `day_hours` | 白天时段 `HH:MM-HH:MM`，支持跨天；默认 `8:00-23:00`，留空 = 全天 |
| `round_interval_day` | 白天每轮之间的等待区间（秒），默认 `[300, 600]` |
| `round_interval_night` | 夜间每轮之间的等待区间（秒），默认 `[1200, 1800]` |
| `refresh_seconds` | 刷新课程元数据与已选状态的周期（秒），最小 300 |
| `max_errors` | 连续异常熔断阈值，最小 3 |
| `mode` | `spam` 直接提交（默认）；`monitor` 仅提醒不提交；`grab` 同 `spam` |
| `email` | 邮件通知配置，密码建议用 `password_env` 指向环境变量 |
| `headless` | 一般不用设，默认按平台自动判断 |

## 命令一览

```bash
python grabbing.py --login            # 登录并生成 auth.json（需图形界面）
python grabbing.py --list             # 列出可选课（查 lessonId / 容量）
python grabbing.py                    # 按配置监控抢课
python grabbing.py --headless         # 强制无头模式
python grabbing.py --mode monitor     # 只监控不提交
python grabbing.py --lesson 123456 -t 60 --log run.log
```

- `-m/--mode`：切换运行模式
- `-t/--interval`：覆盖白天轮间等待，以该值为中心 ±30%
- `--log`：同时写入日志文件

## 保护机制

| 机制 | 作用 |
|---|---|
| 随机间隔 | 轮内每笔请求间隔随机；轮间白天短、夜间长，避免固定节拍 |
| 活跃时段 | `day_hours` 之外按夜间节奏运行 |
| 失败熔断 | 连续异常达 `max_errors` 次后停止；网络类异常不计入，避免断网误停 |
| 风控即停 | 响应出现「请求过于频繁」「账号受限」等信号时立即停止并告警 |
| 登录自愈 | 登录态失效先尝试用 `.env` 账号密码重登，失败则告警停止 |

## 在无图形界面的服务器上运行

1. 在本机执行 `--login` 生成 `auth.json`。
2. 把项目目录连同 `auth.json` 拷到服务器。
3. 按上面的 Linux 命令装环境。
4. 运行 `.venv/bin/python grabbing.py`（Linux 无 `$DISPLAY` 时自动 headless）。

服务器独立运行，本机关机或删除本地文件都不影响。

## 文件说明

| 路径 | 作用 |
|---|---|
| `grabbing.py` | 命令行入口 |
| `jw_login.py` | 登录模块的兼容入口（实现已迁至 `ustcgrab/login.py`） |
| `ustcgrab/` | 主实现，按职责拆分：`config` 配置、`api` 接口传输、`fields` 字段提取、`courses` 匹配与冲突、`pacing` 节奏、`notify` 通知、`login` 登录、`runner` 主循环、`cli` 入口 |
| `config.json` | 通用配置模板（可提交） |
| `config.local.json` | 个人信息覆盖（**已忽略**） |
| `.env` | 账号密码与 SMTP 授权码（**已忽略**） |
| `auth.json` | 登录态 cookie（**已忽略**） |
| `autostart_*.bat` / `autostart_*.ps1` | Windows 开机自启的安装与卸载 |
| `run_bot.pyw` / `start_bot.bat` | Windows 后台静默启动 |
| `run.sh` | Linux / macOS 前台启动 |
| `requirements.txt` | 依赖（仅 `playwright`） |

## 常见问题

- **解析不到 `turnId`**：非选课开放时段常见。等开放后再跑，或手动填 `courseSelectTurnAssoc`。
- **课程匹配失败，匹配数=0**：课程名或教师名与接口返回不一致。先用 `--list` 看实际字段值再改配置。
- **一直失败但提示「人数已满」**：正常，继续蹲守。
- **提示「登录态已过期」**：程序会先尝试自动重登；若需验证码或扫码，回本机 `--login` 刷新 `auth.json`。
- **被风控 / 账号受限**：立即停止，降频或改手动；必要时联系教务说明。
