# encoding=utf8
# USTC 抢课脚本 - 开机自启动安装（由 autostart_install.bat 调用）
# 机制：写入当前用户注册表 Run 键，登录 Windows 后自动后台启动，无需管理员权限。
$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$exe = Join-Path $here '.venv\Scripts\pythonw.exe'
$script = Join-Path $here 'run_bot.pyw'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$name = 'USTC_Course_Grab_Bot'

Write-Host '============================================'
Write-Host '  USTC 抢课脚本 - 开机自启动安装'
Write-Host '============================================'
Write-Host ''

if (-not (Test-Path $exe)) {
    Write-Host "[错误] 未找到虚拟环境解释器：$exe"
    Write-Host '请先按 README 执行：'
    Write-Host '  python -m venv .venv'
    Write-Host '  .venv\Scripts\pip install -r requirements.txt'
    Write-Host '  .venv\Scripts\playwright install chromium'
    exit 1
}
if (-not (Test-Path $script)) {
    Write-Host "[错误] 未找到启动器：$script"
    exit 1
}

$value = '"' + $exe + '" "' + $script + '"'
Set-ItemProperty -Path $runKey -Name $name -Value $value

Write-Host '[成功] 已设置开机自启动。'
Write-Host "  注册表项: $runKey\$name"
Write-Host '  启动方式: 登录 Windows 后自动后台启动（无窗口，headless）'
Write-Host "  日志    : $(Join-Path $here 'run.log')"
Write-Host ''
Write-Host '现在立即启动（可选）：'
Write-Host "  Start-Process -FilePath `"$exe`" -ArgumentList `"`"$script`"`""
Write-Host '取消自启动：'
Write-Host '  双击 autostart_uninstall.bat'
