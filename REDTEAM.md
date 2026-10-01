# REDTEAM — Phase 0 独立审查（2026-10-01）

审查人：红队子代理（批判视角）→ 蓝队已修复 → 本文件为最终记录。

## 总 verdict：CONDITIONAL → 修复后 GO（附 M1 待用户决策）

三处 blocker 已在 Phase 0 内修复并回归测试通过；major 已排入 Phase 1–4 计划；
M1 数据源经 A/B/C/D/E/F 评估后，**用户决策 D（2026-10-01）：v1 砍掉 M1**；
M2 重定义为持仓敞口快照，阶段重排为 4 个。

---

## 🔴 Blocker（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | `store/migrate.py` 把多语句 SQL 传给单语句 executor，`ProgrammingError`；零测试 | 引号/注释感知的 `_split_statements` 逐条执行 | `tests/unit/test_migration.py`：真实迁移 apply 两次（2 个文件、8 张表），第二次返回 0 |
| B2 | 架构测试对相对导入 `pass` 忽略，`from ..store import x` 可走私 | `_resolve_relative_import` 解析为绝对包名再查 ALLOWED 表 | `test_relative_imports_are_resolved` 回归测试 |
| B3 | 前端 Panel 消费 freshness，后端无接口吐 freshness | 新增 `GET /api/v1/freshness`（Phase 0 stub：5 模块全 stale） | `test_api_freshness.py` 锁死前后端形状 |

修复中附带发现：`001_init.sql` 漏了 `sector_momentum` 表 → 按"一变更一文件"约定补 `002_sector_momentum.sql`。

## 🟠 Major（Phase 1 计划内排期）

- **M5** CBOE robots/ToS 未验证 → Phase 4 开工前补查 `cboe.com/robots.txt` + 条款并记录；
  Phase 4 加 HTML fixture parser 契约测试。
- **M2** ~~ETFdb 5日汇总只采过一次快照~~ → n/a（M1 已砍，ETFdb 路线作废）。
- **M3** 真实 payload 零存档 → Phase 1 第一个 parser 契约测试起，SSGA XLSX / CBOE HTML / Yahoo JSON 存 `tests/fixtures/` 做 golden fixture。
- **M4** 周末/节假日行为 → PLAN 已加入"非交易日跳过写入"规则；Phase 1 实现 `trading_day` helper。
- **M5** Yahoo 当日未收盘 bar → PLAN 已记：EOD adapter 必须丢弃未完成 bar（Phase 2）。
- **M6** EDGAR → 已关闭：第二出口实测 **HTTP 200**，证实 403 是本机 egress IP 问题。
  VPS 部署后复验一次即可（Phase 3 DoD）。
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

**用户决策（2026-10-01）：D。v1 砍掉 M1。** M2 重定义为持仓敞口快照（原"持仓×板块流"
公式失效），阶段重排为 Phase 1–4。`sector_flow` 表由 `003_drop_m1.sql` 移除。

---

# REDTEAM — Phase 1（M2 持仓敞口面板）独立审查（2026-10-01）

审查人：独立红队子代理（只读，未改任何文件）→ 蓝队修复 → 本节为最终记录。

## 总 verdict：CONDITIONAL → blocker 修复后 GO

2 个 blocker 均为**静默数据损坏路径**（无日志无告警），已按 fail-loud 原则修复并回归；
5 个 major 同批修复；minor 部分修复、部分排期。

## 🔴 Blocker（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| B1 | 11 只 ETF 的 as_of 不一致时被 `Counter.most_common` 多数投票掩盖；滞后文件旧持仓混入快照，`holding` 与 `stock_exposure` 两表口径不一致，全程无告警（`services/m2.py:15-16`） | 删除 `_mode_as_of`；新增 `_validate_batch`：batch 内 as_of 不完全一致 → `ValueError` 列出各 ETF 日期，写入前 fail-loud（面板按现有机制置灰） | `test_run_m2_rejects_mixed_as_of_dates`：混入 9/29 滞后文件 → raise，且两表零写入 |
| B2 | "权重加总≈100%" 不变量只在 golden fixture 测试里，pipeline 运行时无门；SSGA 若把权重列从百分比改成小数（Σ≈0.01），Pydantic 照样通过（`le=1`），静默入库（`services/m2.py` 无运行时校验） | `_validate_batch` 加运行时门：每只 ETF Σweight ∈ [0.95, 1.05]，否则 raise（fail-loud → 置灰） | `test_run_m2_rejects_weight_sum_drift`：模拟 percent→fraction 漂移 → raise，零写入 |

## 🟠 Major（已修复）

| # | 问题 | 修复 | 验证 |
|---|------|------|------|
| M1 | `_fetch_all` 单文件 404 拖垮全部 11 只；all-or-nothing 策略无测试锁定（将来改成"能写几只写几只"会悄悄制造 B1 同类问题） | 策略不变（fail-loud-all 正确），加测试 pin 住 | `test_fetch_failure_writes_nothing`：mock `_fetch_all` 抛错 → 异常向上传播，两表零写入 |
| M2 | 前端 freshness fail-open：`/freshness` 500 而 `/exposure` 仍有旧数据时，面板全透明度展示旧数字、只写 "no data yet"，无置灰无 STALE（`Panel.tsx:17`） | `Panel` 新增 `hasData` prop：`freshness === null && hasData` → 按 stale 处理（置灰 + "freshness unknown · STALE"）；无数据空态保持原样 | `npm run build` 通过（tsc）；`ExposurePanel` 传入 `hasData={rows?.length > 0}` |
| M3 | ECharts tooltip formatter 把原始 ticker 拼进 HTML 字符串 → 反射型 XSS 面（`ExposurePanel.tsx:44-47`） | 新增 5 行 `escapeHtml`，ticker 与 contributing_etfs 拼接前转义 | 同上构建通过；SSGA 为可信源，实际可利用性低 |
| M4 | `"Free, official, no ToS risk"` 无证据法律断言仍在模块 docstring（`ssga.py:13`） | 改为 "fetched at low frequency with descriptive UA; SSGA ToS not independently reviewed" | 文本修改 |
| M5 | 同一文件内重复 ticker 会被 `weights[ticker] += ...` double-count（`compute/exposure.py:19-23`） | parser 内对单文件 ticker 去重-or-raise（fail-loud 优先）；跨 ETF 重复合法（GOOGL 在 XLC+XLY）不受影响 | `test_duplicate_ticker_row_within_file_raises`：fixture 追加 NVDA 重复行 → raise；golden fixture 本身 75 ticker 全唯一，parser 契约测试仍绿 |

## 🟡 Minor（状态）

- **m1** `is_stale` 对未来日期返回"新鲜" → 已修：`as_of > today → stale`（`test_future_as_of_is_stale`）。
- **m2** "As of" 单一日期格式 → 已修：`AS_OF_FMTS = ("%d-%b-%Y", "%Y-%m-%d", "%d %b %Y")` 逐个尝试再 fail-loud（`test_as_of_accepts_iso_fallback_format`）。
- **m3** 长周末无测试 → 已补：`test_long_weekend_monday_holiday`（Labor Day 周一休市，周二视周五数据为 fresh）。
- **m4** `daily.py` 的 `m2` CLI 命令无交易日门控 → 已修：与 `run-all` 同门控，非交易日 echo 跳过。
- **m5** `types.ts:46` 注释漂移（"0..~1" vs 后端允许 -0.01）→ 已同步为 `-0.01..~1`。
- **m6** `test_pure_function_signature` 弱 guard → 保留（架构测试已强制 `compute→models only`，冗余无害）。
- **m7** `StockExposure.total_weight` 下界 -0.01：某 ticker 跨多只 ETF 负权重腿加总跌破 -0.01 时 `run_m2` 会整单 ValidationError → 现实中极不可能（需 -1% 级跨 ETF 空头），记录，Phase 2+ 观察。
- **m8** NYSE 假日表只到 2027 → fail-safe（2028 未登记假日会被当交易日，但写入全按文件 as_of keyed、无日期污染，面板按 T+1 正确 stale）；**排期**：每年 12 月补充假日表，建议加日历更新提醒。

## 回归证据（2026-10-01，修复后）

- `pytest tests`：**45 passed**（38 → 45，新增 B1/B2/M1/M5/m1/m2/m3 测试 7 个）
- `ruff check` / `ruff format --check`：全绿
- 架构测试（`tests/test_architecture.py` AST 层级）：通过，无 god object（所有文件 <160 行）
- React 生产构建：通过（ECharts chunk >500kB 警告为已知 minor，排期做 code-splitting）
- 真实冒烟（修复前已验证，修复不涉及网络路径）：11 只 ETF 全量 516 holdings / 516 exposures，`as_of=2026-09-30`

## 遗留到后续阶段

- Phase 0 M5（CBOE robots/ToS）→ Phase 4 开工前补查。
- Phase 0 M6（EDGAR 403 系本机 egress IP）→ VPS 部署后复验。
- Phase 2 开工前用户需决策：Yahoo chart（非官方）做 EOD 主源 vs 恢复 Tiingo。
