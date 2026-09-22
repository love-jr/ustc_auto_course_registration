"""USTC 教务系统监控式抢课。

模块划分：
  config   配置与 .env 加载
  api      教务接口 HTTP 传输与响应判定
  fields   接口记录字段提取（纯函数）
  courses  目标课程匹配与时间冲突
  pacing   活跃时段与随机间隔
  notify   邮件通知
  login    Playwright 登录与登录态持久化
  runner   登录 → 列课 → 监控抢课主循环
  cli      命令行入口
"""

__version__ = "2.0.0"
