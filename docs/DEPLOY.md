# DEPLOY.md — VPS 部署手册（US Money Flow Tracker v1）

目标机器：用户 VPS（出境 IP 可正常访问 SEC EDGAR 与 CBOE；本机沙盒 SEC 403、CBOE 正常）。

## 1. 部署步骤（从本机迁移）

```bash
# 1) 在 VPS 上 clone / 拷 repo（本 repo 无 remote，用 scp/rsync 拷整个目录）
rsync -avz --exclude data/ --exclude web/node_modules \
  ~/workspace/us-moneyflow/ user@vps:~/us-moneyflow/

# 2) 建 venv 并安装
cd ~/us-moneyflow
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

`/etc/systemd/system/moneyflow.service`：
```ini
[Unit]
Description=US Money Flow daily pipeline
After=network-online.target

[Service]
Type=oneshot
User=moneyflow
WorkingDirectory=/home/moneyflow/us-moneyflow
ExecStart=/home/moneyflow/us-moneyflow/.venv/bin/python -m moneyflow.pipeline.daily run-all
# 日志进 journal：journalctl -u moneyflow.service
```

`/etc/systemd/system/moneyflow.timer`：
```ini
[Unit]
Description=Daily money-flow pipeline (after US close)

[Timer]
# 每天 15:05 PDT = 18:05 EDT（美东收盘后 2 小时，CBOE daily 页已发布）
OnCalendar=*-*-* 15:05:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl daemon-reload
# 先 dry-run 一次 service（不等 timer）：确认日志干净再 enable timer
sudo systemctl start moneyflow.service
journalctl -u moneyflow.service -n 50   # 检查 run-all 全绿
sudo systemctl enable --now moneyflow.timer
systemctl list-timers moneyflow.timer   # 确认
```

API 服务（可选常驻，供前端/矩阵产品调用）：
```ini
# /etc/systemd/system/moneyflow-api.service
[Unit]
Description=US Money Flow API
After=network-online.target

[Service]
Type=simple
User=moneyflow
WorkingDirectory=/home/moneyflow/us-moneyflow
ExecStart=/home/moneyflow/us-moneyflow/.venv/bin/uvicorn moneyflow.api.main:app --host 127.0.0.1 --port 8000
Restart=on-failure
```
前端 `web/dist` 已由 FastAPI 直接 serve（`WEB_DIST` 存在即挂载），单服务即可。

## 3. SQLite WAL 说明

- `store/db.py` 建 engine 时执行 `PRAGMA journal_mode=WAL`：timer 写库的同时 API 读库不阻塞。
- WAL 产生 `-wal` / `-shm` 伴生文件：**备份/迁移时三者一起拷**，或先 `sqlite3 data/moneyflow.db "PRAGMA wal_checkpoint(TRUNCATE);"` 再拷单个 db 文件。

## 4. 备份建议

```bash
# 每日一次（cron 或另一个 timer），保留 7 天
sqlite3 /home/moneyflow/us-moneyflow/data/moneyflow.db \
  ".backup '/home/moneyflow/backups/moneyflow-$(date +%F).db'"
find /home/moneyflow/backups -name 'moneyflow-*.db' -mtime +7 -delete
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
- [ ] systemd timer dry-run：`systemctl start moneyflow.service` 一次性验证，日志干净后再 `enable --now` timer
- [ ] 非交易日跑 `run-all`：返回 skipped，不写新行（防周五数据记到周六）
