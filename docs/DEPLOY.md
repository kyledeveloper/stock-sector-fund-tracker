# DEPLOY.md — VPS 部署手册（US Money Flow Tracker v1）

目标机器：用户 VPS（出境 IP 可正常访问 SEC EDGAR 与 CBOE；本机沙盒 SEC 403、CBOE 正常）。

## 1. 部署步骤（从本机迁移）

```bash
# 1) 在 VPS 上 clone repo（目录名保持仓库名，systemd unit 依赖这个路径）
git clone https://github.com/kyledeveloper/stock-sector-fund-tracker ~/stock-sector-fund-tracker

# 2) 建 venv 并安装
cd ~/stock-sector-fund-tracker
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 3) 前端构建（产物被 FastAPI 直接 serve）
cd web && npm ci && npm run build && cd ..

# 4) 回填历史（只需一次；需要 VPS 出境 IP）
.venv/bin/python -m moneyflow.pipeline.daily backfill-m3   # M3 约 6 个月 EOD
.venv/bin/python -m moneyflow.pipeline.daily backfill-m4   # M4 12 家 13F + 7 天 Form 4
.venv/bin/python -m moneyflow.pipeline.daily backfill-m5   # M5 最近 90 天 put/call（串行，间隔 ≥2s，约 3 分钟）
```

> `backfill-m5` 说明：跳过周末/ NYSE 节假日；单请求串行、间隔 ≥2 秒；
> 单日失败只记 errors 继续；按 `trade_date` 主键 upsert，重复跑安全。

## 2. systemd timer（每日美东收盘后跑 run-all）

`run-all` = m2 → m3 → m4 → m5，全幂等；非交易日只 bump `checked_at` 不写数据。

仓库里的 `systemd/moneyflow-daily.service` 和 `systemd/moneyflow-daily.timer` 是**用户级** unit，
以部署用户身份运行，不需要 root，也不需要单独建 `moneyflow` 系统用户。以仓库里的文件为准，不要在这里另抄一份。

先建运行时配置文件。SEC EDGAR 要求 User-Agent 带联系邮箱，`moneyflow-daily.service` 通过
`EnvironmentFile=-%h/.config/moneyflow/env` 读取；不设置的话每天 M4 都会失败（其他模块照常跑）。
请填真实可联系的邮箱，不要用 `example.com` 这类占位地址。

```bash
mkdir -p ~/.config/moneyflow
install -m 600 /dev/null ~/.config/moneyflow/env    # 先建好并设成 600，再写入
echo 'MONEYFLOW_CONTACT_EMAIL=你的邮箱@域名' >> ~/.config/moneyflow/env
ls -l ~/.config/moneyflow/env                       # 应显示 -rw-------
```

```bash
# 1) 安装用户级 unit
mkdir -p ~/.config/systemd/user
cp ~/stock-sector-fund-tracker/systemd/moneyflow-daily.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload

# 2) 允许用户退出登录后定时任务照常运行（必须做，否则 SSH 断开后 timer 不会触发）
sudo loginctl enable-linger "$USER"
loginctl show-user "$USER" --property=Linger   # 应显示 Linger=yes

# 3) 先手动跑一次 service（不等 timer），确认日志干净再启用 timer
systemctl --user start moneyflow-daily.service
journalctl --user -u moneyflow-daily.service -n 50   # 检查 run-all 全绿
systemctl --user enable --now moneyflow-daily.timer
systemctl --user list-timers moneyflow-daily.timer   # 确认下次触发时间
```

触发时间见 `systemd/moneyflow-daily.timer`：
```ini
# 每天美西 15:30 = 美东 18:30（收盘后 2.5 小时，CBOE daily 页已发布）。
# 显式写时区：服务器本地时区不是美西时也不会提前跑；夏令时由 systemd 自动处理。
OnCalendar=America/Los_Angeles *-*-* 15:30:00
Persistent=true
```

clone 到了别的目录：不要改仓库里的文件，用 `systemctl --user edit moneyflow-daily.service`
写 drop-in 覆盖路径（用法见 unit 文件头部注释）。

API 服务（可选常驻，供前端/矩阵产品调用），同样做成用户级 unit：
```ini
# ~/.config/systemd/user/moneyflow-api.service
[Unit]
Description=US Money Flow API

[Service]
Type=simple
WorkingDirectory=%h/stock-sector-fund-tracker
Environment=PYTHONPATH=%h/stock-sector-fund-tracker/src
ExecStart=%h/stock-sector-fund-tracker/.venv/bin/uvicorn moneyflow.api.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=default.target
```
```bash
systemctl --user daemon-reload && systemctl --user enable --now moneyflow-api.service
```
前端 `web/dist` 已由 FastAPI 直接 serve（`WEB_DIST` 存在即挂载），单服务即可。

## 3. SQLite WAL 说明

- `store/db.py` 建 engine 时执行 `PRAGMA journal_mode=WAL`：timer 写库的同时 API 读库不阻塞。
- WAL 产生 `-wal` / `-shm` 伴生文件：**备份/迁移时三者一起拷**，或先 `sqlite3 data/moneyflow.db "PRAGMA wal_checkpoint(TRUNCATE);"` 再拷单个 db 文件。

## 4. 备份建议

```bash
# 每日一次（cron 或另一个 timer），保留 7 天
mkdir -p ~/backups
sqlite3 ~/stock-sector-fund-tracker/data/moneyflow.db \
  ".backup '$HOME/backups/moneyflow-$(date +%F).db'"
find ~/backups -name 'moneyflow-*.db' -mtime +7 -delete
```
`.backup` 是在线热备，WAL 下安全。恢复：停掉 timer/api，把备份文件拷回 `data/moneyflow.db`。

## 5. CBOE 抓取合规（M5）

- 每日只抓一次当日数据（timer 内单请求），backfill 一次性 90 天、间隔 ≥2s。
- 诚实 UA（`us-moneyflow/0.1`），遵守 robots.txt（daily 页不在禁区）。
- 不并发、不压测、不分发原始 HTML；面板只展示聚合比率。
- 若 CBOE 改版导致解析失败：pipeline fail-loud（日志 + 无脏写），面板显示"暂无数据"，修 parser 契约测试后再上线。

---

## 附录 A：端到端冒烟清单（VPS 预上线必跑）

- [ ] `backfill-m3`：12 tickers × ~120 bars 入库，`m3` freshness `as_of` = 最近交易日
- [ ] `backfill-m4`：12 家 13F 有新 quarter 入库；Form 4 7 天扫描 `fetched > 0`
- [ ] EFTS 数量对比：去掉 `q="4"` 后的查询与原查询 filing 数一致（防静默截断）
- [ ] 确认 `forms=4` 包含 4/A（抽查一条 amendment filing）
- [ ] 观察 `volume_warning` 与单 filing/manager `errors`（M4 红队 M1/M6）
- [ ] `backfill-m5`：`cboe_putcall` 行数 ≈ 90 天内交易日数；抽查 `total_put_call` 在 0.3–2.0 合理区间
- [ ] CBOE 连通性：单页抓取 200（`m5` 命令一次）
- [ ] `run-all` 全绿；`/api/v1/freshness` 四个模块 m2–m5 均有 `as_of`
- [ ] 前端 `npm run build` 产物存在；打开页面四个面板（敞口/动量/机构与内幕/期权情绪）均有数据或诚实的"暂无数据"
- [ ] systemd timer dry-run：`systemctl --user start moneyflow-daily.service` 一次性验证，日志干净后再 `systemctl --user enable --now moneyflow-daily.timer`
- [ ] `~/.config/moneyflow/env` 存在、权限 600、含 `MONEYFLOW_CONTACT_EMAIL`；`run-all` 日志里 M4 没有缺邮箱的报错
- [ ] `loginctl show-user "$USER" --property=Linger` 显示 `Linger=yes`（退出登录后 timer 仍会触发）
- [ ] 非交易日跑 `run-all`：返回 skipped，不写新行（防周五数据记到周六）
