# USTC 教务系统监控式抢课

按优先级自动提交选课请求，适配现行教务系统（jw.ustc.edu.cn），Windows / Linux / macOS 通用。

## ⚠️ 风险提示

自动抢课可能触发教务系统风控，导致账号受限，**后果自负**。建议先读一遍下面的[保护机制](#保护机制)。

## 工作原理

登录后从选课页解析出 `studentId` 与 `turnId`，拉取全部可选课并绑定到配置里的目标课程，然后进入监控循环：

```
每轮：
  ├─ 查询已选课程，更新每门目标课的「已选 / 被冲突阻止」状态
  ├─ 每 15 分钟（refresh_seconds）刷新一次课程元数据
  ├─ 按 priority 依次提交每门未成功的课：
  │    POST add-request        → 返回 requestId
  │    POST add-drop-response  → 由教务系统裁决成功/失败
  └─ 轮间等待（白天短、夜间长，随机）
```

几个和直觉不同、但经实际抓包确认的设定：

- **容量和已选人数不作为提交前置条件。** 真实系统里存在已选人数已超过 `limitCount` 的课程，用人数判断会白白错过；候选课一律直接提交，由教务系统裁决。历史版本曾先查 `std-count`、有空位才选，现已移除。
- **提交是两段式。** `add-request` 拿到 `requestId` 后，必须再用 `add-drop-response` 确认才算完成。
- **`add-drop-response` 偶发返回 `success=false` 但文案是「已选上」。** 这种矛盾响应按成功处理（见 `api.parse_add_result`）。
- **课程名按子串匹配。** 接口返回的名字常带「（英文名）」「-01班」等后缀，配置里写关键片段即可。

## 快速开始

### 1. 安装（一次性）

需要 Python 3.8+。

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

`auth.json` 已在 `.gitignore` 中，**不要提交**。若 `.env` 里配了账号密码，登录态失效时程序也会自动重登。

### 3. 配置

配置分两层，后者覆盖前者：

| 文件 | 用途 | 是否提交 |
|---|---|---|
| `config.json` | 通用设置模板 | ✅ |
| `config.local.json` | 你的个人信息：学号、邮箱、目标课程（照 `config.local.example.json` 填写） | ❌ 已忽略 |

把个人信息填进 `config.local.json`，让 `config.json` 保持为干净模板，避免误提交隐私。各字段含义见[配置字段](#配置字段)。

账号密码放 `.env`（照 `.env.example` 填写，同样已忽略）：

```
USTC_USERNAME=你的学号
USTC_PASSWORD=你的密码
COURSE_BOT_SMTP_PASSWORD=你的QQ邮箱SMTP授权码
```

不建 `.env` 也能跑，只是没有自动重登和邮件通知。

> 若登录需要验证码、扫码或二次认证，程序会发邮件通知并停止——这些步骤无法也不应绕过。

### 4. 运行

```bat
.venv\Scripts\python grabbing.py              :: Windows
.venv/bin/python grabbing.py                  # Linux/macOS
```

## 配置字段

| 字段 | 默认 | 说明 |
|---|---|---|
| `studentAssoc` | `""` | 学生关联 id；留空则从选课页 URL 自动解析 |
| `courseSelectTurnAssoc` | `""` | 选课轮次 id，**每学期变**。从选课页 URL `.../turn/<数字>/select` 取 |
| `courses` | `[]` | 目标课程数组，见下 |
| `batch_interval` | `[5, 15]` | 同一轮内每笔请求的间隔区间（秒） |
| `day_hours` | `"8:00-23:00"` | 白天时段 `HH:MM-HH:MM`，支持跨天；留空 = 全天按白天 |
| `round_interval_day` | `[300, 600]` | 白天每轮之间的等待区间（秒） |
| `round_interval_night` | `[1200, 1800]` | 夜间每轮之间的等待区间（秒） |
| `refresh_seconds` | `900` | 刷新课程元数据与已选状态的周期（秒），**最小 300** |
| `max_errors` | `20` | 连续异常熔断阈值，**最小 3** |
| `mode` | `"spam"` | `spam` 直接提交；`monitor` 仅刷新不提交；`grab` 同 `spam` |
| `email` | 关闭 | 邮件通知配置，密码建议用 `password_env` 指向环境变量 |
| `headless` | 按平台 | 一般不用设，默认见[无图形界面的服务器](#在无图形界面的服务器上运行) |

`courses` 每项：

| 键 | 说明 |
|---|---|
| `lessonAssoc` | 精确指定课程 id（最可靠，可用 `--list` 查） |
| `name` | 课程名关键词，**子串匹配**；与 `lessonAssoc` 同时写则都需满足 |
| `teacher` | 教师名，多人用逗号分隔；写多人时要求**都**出现在该课教师列表中 |
| `priority` | 越小越优先 |
| `allow_conflict` | 是否允许与已选/已中课程时间冲突 |

匹配到 0 门或 2 门以上都会直接报错退出，不会瞎猜。

## 命令一览

```bash
python grabbing.py --login                   # 登录并生成 auth.json（需图形界面）
python grabbing.py --list                    # 列出可选课（查 lessonId / 容量），默认显示 20 条
python grabbing.py                           # 按配置监控抢课
python grabbing.py --name 数据结构            # 临时指定课程名关键词，覆盖配置文件
python grabbing.py --lesson 123456           # 临时指定 lessonId
python grabbing.py --mode monitor            # 只监控不提交
python grabbing.py --headless                # 强制无头模式
python grabbing.py -t 60 --log run.log       # 白天轮间等待基准 60s，并写日志
```

`-t/--interval` 以给定值为中心取 ±30% 作为白天轮间随机区间（最小基准 30 秒）。

监控循环的退出原因有四种：`done`（目标课程都已处理完）、`risk`（疑似风控）、`login-expired`（登录态失效且自动重登失败）、`circuit-breaker`（连续异常熔断）。

## 保护机制

| 机制 | 作用 |
|---|---|
| 随机间隔 | 轮内每笔请求间隔随机（`batch_interval`）；轮间白天短、夜间长。选课确认步骤关闭节流以保持事务连续 |
| 活跃时段 | `day_hours` 之外按夜间节奏运行 |
| 失败熔断 | 连续异常达 `max_errors` 次后停止；**网络类异常不计入**，避免断网久了被误停 |
| 风控即停 | 响应出现 429 或「请求过于频繁」「账号受限」等信号时立即停止并告警 |
| 登录自愈 | 登录态失效先尝试用 `.env` 账号密码重登，成功后不打扰用户 |
| 网络等待 | 启动时先等教务域名可解析（开机自启常早于网络就绪）；网络类错误最多重试 60 次 |

## 在无图形界面的服务器上运行

1. 在本机执行 `--login` 生成 `auth.json`。
2. 把项目目录连同 `auth.json` 拷到服务器。
3. 按上面的 Linux 命令装环境。
4. 运行 `.venv/bin/python grabbing.py`（Linux 无 `$DISPLAY` 时自动 headless）。

服务器独立运行，本机关机或删除本地文件都不影响。

## Windows 后台运行与开机自启

| 文件 | 作用 |
|---|---|
| `start_bot.bat` | 双击后台启动（无窗口）。已在运行则不会重复启动 |
| `run_bot.pyw` | 后台启动器本体：等价于 `python grabbing.py --headless --log run.log` |
| `autostart_install.bat` / `.ps1` | 写入当前用户注册表 `Run` 键，登录后自动后台启动（无需管理员） |
| `autostart_uninstall.bat` / `.ps1` | 停止进程、清理注册表 / 计划任务 / 启动文件夹，可选删除 `auth.json` 与日志 |

## 文件说明

| 路径 | 作用 |
|---|---|
| `grabbing.py` | 命令行入口 |
| `jw_login.py` | 登录模块的兼容入口（实现已迁至 `ustcgrab/login.py`） |
| `ustcgrab/` | 主实现，见下方模块划分 |
| `config.json` / `config.local.json` | 通用模板 / 个人信息覆盖（后者**已忽略**） |
| `.env` | 账号密码与 SMTP 授权码（**已忽略**） |
| `auth.json` | 登录态 cookie（**已忽略**） |
| `run.sh` | Linux / macOS 前台启动（输出同时写 `run.log`） |
| `requirements.txt` | 依赖（仅 `playwright`） |

### 模块划分

| 模块 | 职责 |
|---|---|
| `config` | 分层配置加载（默认值 < `config.json` < `config.local.json`）与 `.env` |
| `api` | 教务接口 HTTP 传输、响应判定、请求节流 |
| `fields` | 接口记录字段提取（纯函数，字段名变化只需改这里） |
| `courses` | 目标课程匹配与时间冲突判定 |
| `pacing` | 活跃时段与随机间隔 |
| `notify` | 邮件通知（相同内容 10 分钟内不重发） |
| `login` | Playwright 登录与登录态持久化 |
| `runner` | 登录 → 列课 → 监控抢课主循环 |
| `cli` | 命令行入口与日志分流 |

## 常见问题

- **解析不到 `turnId`**：非选课开放时段常见。等开放后再跑，或手动填 `courseSelectTurnAssoc`。
- **提示「课程匹配失败，匹配数=0」**：课程名或教师名与接口返回不一致。先用 `--list` 看实际字段值再改配置。注意 `name` 是子串匹配，写得太短可能命中多门课（匹配数 >1 也会报错）。
- **一直失败但提示「人数已满」**：正常，继续蹲守。
- **提示「登录态已过期」**：程序会先尝试自动重登；若需验证码或扫码，回本机 `--login` 刷新 `auth.json`。
- **被风控 / 账号受限**：程序会立即停止并告警。降频或改手动；必要时联系教务说明。

## 许可

MIT，见 `LICENSE`。
