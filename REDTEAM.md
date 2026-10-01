# REDTEAM — Phase 0 独立审查（2026-10-01）

审查人：红队子代理（批判视角）→ 蓝队已修复 → 本文件为最终记录。

## 总 verdict：CONDITIONAL → 修复后 GO（附 M1 待用户决策）

三处 blocker 已在 Phase 0 内修复并回归测试通过；major 已排入 Phase 1 计划；
M1 数据源走 A/B/C/D/E/F 评估后收敛为 **A（ETFdb 近5日净流入）vs D（砍 M1）**，待用户拍板。

---

## 🔴 Blocker（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | `store/migrate.py` 把多语句 SQL 传给单语句 executor，`ProgrammingError`；零测试 | 引号/注释感知的 `_split_statements` 逐条执行 | `tests/unit/test_migration.py`：真实迁移 apply 两次（2 个文件、8 张表），第二次返回 0 |
| B2 | 架构测试对相对导入 `pass` 忽略，`from ..store import x` 可走私 | `_resolve_relative_import` 解析为绝对包名再查 ALLOWED 表 | `test_relative_imports_are_resolved` 回归测试 |
| B3 | 前端 Panel 消费 freshness，后端无接口吐 freshness | 新增 `GET /api/v1/freshness`（Phase 0 stub：5 模块全 stale） | `test_api_freshness.py` 锁死前后端形状 |

修复中附带发现：`001_init.sql` 漏了 `sector_momentum` 表 → 按"一变更一文件"约定补 `002_sector_momentum.sql`。

## 🟠 Major（Phase 1 计划内排期）

- **M1** CBOE robots/ToS 未验证 → Phase 1 开工前补查 `cboe.com/robots.txt` + 条款并记录；Phase 5 加 HTML fixture parser 契约测试。
- **M2** ETFdb 5日汇总只采过一次快照 → Phase 1 开工前连采两天验证数字会动 + 读 ToS；robots 已查：`/etf/` 未被 Disallow，但 `Crawl-delay: 3` 必须遵守。
- **M3** 真实 payload 零存档 → Phase 1 第一个 parser 契约测试起，SSGA XLSX / CBOE HTML / Yahoo JSON 存 `tests/fixtures/` 做 golden fixture。
- **M4** 周末/节假日行为 → PLAN 已加入"非交易日跳过写入"规则；Phase 1 实现 `trading_day` helper。
- **M5** Yahoo 当日未收盘 bar → PLAN 已记：EOD adapter 必须丢弃未完成 bar（Phase 3）。
- **M6** EDGAR "VPS 复验"往后推风险 → 已关闭：第二出口（浏览器）实测
  `data.sec.gov/submissions/CIK0001067983.json` 返回 **HTTP 200**（Berkshire Hathaway 标准 submissions JSON），
  证实 403 是本机 egress IP 问题而非源不可用。VPS 部署后复验一次即可（Phase 4 DoD）。
- **M7** PLAN 与 ALLOWED 表矛盾 → 已收紧为 PLAN 口径：`compute` 仅依赖 `models`（`ingest` 保留 `common` 给共享 HTTP 客户端，测试与 PLAN 已对齐）。

## 🟡 Minor（状态）

- m1 `_package_of` 恒等三元 → 已清理；m2 scope 补 `vix`/`etp`（前后端同步）；
  m3 `checked_at: str` → `datetime`（API 序列化为 ISO 字符串，前端保持 string 镜像）；
  m4 systemd 硬编码 `/home/hatch` → 改为 `%h` 用户级 unit 模板；
  m5 `npm run build` → 已验证通过（tsc + vite，32 modules）；
  m6 11 只 SSGA URL → 全部 200；
  m7 vcrpy/freezegun 零使用 → Phase 1 parser 契约测试起必须用起来，否则从依赖移除；
  m8 `types.ts` 手写镜像 → 第一个真实接口（Phase 1）起加 CI 对拍或转 OpenAPI 生成。

## M1 数据源最终评估

| 选项 | 结论 |
|------|------|
| ETF.com 免费 Top-10 | ❌ 证伪：只有全市场榜，无 11 只逐日流 |
| ETF.com 个股页 | ❌ 证伪：Fund Flows tab 登录墙，无公开 XHR |
| ETFdb 免费页 | ⚠️ 仅 5日/1月…汇总，无逐日序列 → 备选 A |
| stockanalysis | ❌ 免费页无 fund-flow 数据 |
| Nasdaq 免费 API（E spike） | ❌ `api/quote/XLK/info` 无 flow/shares 字段 |
| SSGA 同目录 shares outstanding（F spike） | ❌ 目录无 listing |
| B（份额推导） | 源不存在，不可 commit |
| C（付费） | 违反 $0 约束，死选项 |

**收敛为二选一（用户决策）：A. M1 用 ETFdb 近5日净流入（诚实标注口径）/ D. v1 砍掉 M1。推荐 A。**
