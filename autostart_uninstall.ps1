# encoding=utf8
# USTC 抢课脚本 - 彻底删除自启动 / 停止运行（由 autostart_uninstall.bat 调用）
# 清理范围：
#   1) 停止所有抢课 python/pythonw 进程
#   2) 注册表自启动项（HKCU Run / RunOnce，按任务名或项目路径匹配）
#   3) 计划任务（按动作路径匹配）
#   4) 启动文件夹快捷方式（用户 + 公共）
#   5) 可选：删除登录态 auth.json 与日志
$ErrorActionPreference = 'SilentlyContinue'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'USTC_Course_Grab_Bot'

Write-Host '============================================'
Write-Host '  USTC 抢课脚本 - 彻底删除自启动 / 停止运行'
Write-Host '============================================'
Write-Host ''

$removed = 0

# ---------- 1) 停止进程 ----------
Write-Host '[1/5] 停止抢课进程...'
$procs = Get-CimInstance Win32_Process -Filter "name='python.exe' or name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match 'grabbing\.py|run_bot\.pyw' -or ($_.CommandLine -and $_.CommandLine -like "*$here*") }
if ($procs) {
    foreach ($p in $procs) {
        Write-Host "      停止进程 PID=$($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        $removed++
    }
    Start-Sleep -Seconds 2
} else {
    Write-Host '      无正在运行的抢课进程。'
}

# ---------- 2) 注册表自启动 ----------
Write-Host '[2/5] 清理注册表自启动项...'
$runKeys = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce'
)
$foundReg = $false
foreach ($key in $runKeys) {
    $props = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
    if ($null -eq $props) { continue }
    foreach ($prop in $props.PSObject.Properties) {
        if ($prop.Name -like 'PS*') { continue }
        $val = [string]$prop.Value
        if ($prop.Name -eq $taskName -or $val -like "*run_bot.pyw*" -or $val -like "*grabbing.py*" -or $val -like "*$here*") {
            Remove-ItemProperty -Path $key -Name $prop.Name -Force -ErrorAction SilentlyContinue
            Write-Host "      已删除: $key\$($prop.Name)"
            $foundReg = $true
            $removed++
        }
    }
}
if (-not $foundReg) { Write-Host '      未发现注册表自启动项。' }

# ---------- 3) 计划任务 ----------
Write-Host '[3/5] 清理计划任务...'
$foundTask = $false
Get-ScheduledTask -ErrorAction SilentlyContinue | ForEach-Object {
    $t = $_
    $hit = ($t.TaskName -eq $taskName)
    foreach ($a in @($t.Actions)) {
        $ex = [string]$a.Execute
        $ar = [string]$a.Arguments
        if ($ex -like "*run_bot.pyw*" -or $ar -like "*run_bot.pyw*" -or $ar -like "*grabbing.py*" -or $ex -like "*$here*") {
            $hit = $true
        }
    }
    if ($hit) {
        Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "      已删除计划任务: $($t.TaskName)"
        $script:foundTask = $true
        $script:removed++
    }
}
if (-not $foundTask) { Write-Host '      未发现计划任务。' }

# ---------- 4) 启动文件夹 ----------
Write-Host '[4/5] 清理启动文件夹...'
$foundStartup = $false
$startupDirs = @(
    [Environment]::GetFolderPath('Startup'),
    [Environment]::GetFolderPath('CommonStartup')
)
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in $startupDirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -Path $dir -ErrorAction SilentlyContinue | ForEach-Object {
        $f = $_
        $target = ''
        if ($f.Extension -eq '.lnk') {
            try {
                $lnk = $shell.CreateShortcut($f.FullName)
                $target = "$($lnk.TargetPath) $($lnk.Arguments)"
            } catch { }
        }
        if ($f.Name -like '*USTC*' -or $f.Name -like '*run_bot*' -or $f.Name -like '*grabbing*' `
                -or $target -like "*run_bot.pyw*" -or $target -like "*grabbing.py*" -or $target -like "*$here*") {
            Remove-Item -LiteralPath $f.FullName -Force -ErrorAction SilentlyContinue
            Write-Host "      已删除启动项: $($f.FullName)"
            $script:foundStartup = $true
            $script:removed++
        }
    }
}
if (-not $foundStartup) { Write-Host '      未发现启动文件夹项目。' }

# ---------- 5) 可选：删除登录态与日志 ----------
Write-Host '[5/5] 清理登录态与日志...'
Write-Host '      提示：auth.json 保存了你的教务登录 cookie。'
$ans = Read-Host '      是否同时删除 auth.json 和 run.log？(Y/N)'
if ($ans -match '^[Yy]') {
    $targets = @('auth.json', 'run.log', 'run.err.log', 'run.out.log', '.browser_data')
    foreach ($t in $targets) {
        $full = Join-Path $here $t
        if (Test-Path $full) {
            Remove-Item -LiteralPath $full -Recurse -Force -ErrorAction SilentlyContinue
            Write-Host "      已删除: $t"
        }
    }
    Write-Host '      建议同时检查 .env（内含账号密码/邮箱授权码），如不再使用请手动删除。'
} else {
    Write-Host '      已保留 auth.json 和日志（下次可直接继续使用）。'
}

# ---------- 结果确认 ----------
Write-Host ''
$leftProcs = Get-CimInstance Win32_Process -Filter "name='python.exe' or name='pythonw.exe'" |
    Where-Object { $_.CommandLine -match 'grabbing\.py|run_bot\.pyw' }
$leftReg = @()
foreach ($key in $runKeys) {
    $props = Get-ItemProperty -Path $key -ErrorAction SilentlyContinue
    if ($null -eq $props) { continue }
    foreach ($prop in $props.PSObject.Properties) {
        if ($prop.Name -like 'PS*') { continue }
        $val = [string]$prop.Value
        if ($prop.Name -eq $taskName -or $val -like "*run_bot.pyw*" -or $val -like "*grabbing.py*") {
            $leftReg += "$key\$($prop.Name)"
        }
    }
}
if ($leftProcs.Count -eq 0 -and $leftReg.Count -eq 0) {
    Write-Host '[完成] 已彻底清理：无抢课进程、无自启动残留。'
} else {
    Write-Host '[注意] 仍有残留，请检查：'
    $leftProcs | ForEach-Object { Write-Host "  进程 PID=$($_.ProcessId): $($_.CommandLine)" }
    $leftReg | ForEach-Object { Write-Host "  注册表: $_" }
}
Write-Host '如需彻底删除本项目，直接删除整个文件夹即可。'
