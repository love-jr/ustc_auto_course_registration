"""配置加载。

优先级（后者覆盖前者）：内置默认值 < config.json < config.local.json。

个人信息（学号、校园邮箱、SMTP 账号）放 config.local.json，该文件已被
.gitignore 忽略，因此 config.json 可以作为不含隐私的模板提交。账号密码等
凭据放 .env，同样不进入版本控制。
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(HERE, "config.json")
LOCAL_CONFIG_PATH = os.path.join(HERE, "config.local.json")
ENV_PATH = os.path.join(HERE, ".env")
AUTH_JSON = os.path.join(HERE, "auth.json")

DEFAULTS = {
    "studentAssoc": "",             # 学生关联 id；留空自动解析
    "courseSelectTurnAssoc": "",    # 选课轮次 id，每学期变
    "courses": [],                  # [{lessonAssoc/name/teacher/priority/allow_conflict}]
    "batch_interval": [5, 15],      # 同一轮内每笔请求的间隔（秒）
    "day_hours": "8:00-23:00",      # 白天时段，支持跨天；空=全天按白天
    "round_interval_day": [300, 600],      # 白天每轮之间等待（秒）
    "round_interval_night": [1200, 1800],  # 夜间每轮之间等待（秒）
    "refresh_seconds": 900,         # 运行中刷新课程元数据和已选状态的周期
    "max_errors": 20,               # 连续异常熔断阈值
    "mode": "spam",                 # spam 直接提交(推荐) | monitor 仅提醒 | grab 同 spam
    "email": {},                    # QQ SMTP 配置，密码建议使用 password_env
    # headless 不在此硬编码：默认按平台自动判断
}


def load_env(path=ENV_PATH):
    """读取 .env 中的简单 KEY=VALUE 配置，不引入额外依赖。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_config():
    cfg = dict(DEFAULTS)
    cfg.update(_read_json(CONFIG_PATH))
    cfg.update(_read_json(LOCAL_CONFIG_PATH))
    return cfg


load_env()
