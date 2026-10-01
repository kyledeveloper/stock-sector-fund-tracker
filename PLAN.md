# US Money Flow Tracker — 实施计划（已批准，2026-10-01）

> 目标：美股资金追踪网页，数据源全部 $0，日频 T+1（v1 明确无盘中实时）。
> 流程：每阶段 TDD/契约测试 → 蓝军自测 → 红队攻击 → 修复 → 红队复验签字（REDTEAM.md）→ 下一阶段。
> 复验不通过不得进入下一阶段。commit 本地化，push 需明确指令。

## 技术栈（2026-10-01 修订：前端改为 React）

- 后端：Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2.0 / httpx / pandas+openpyxl / typer
- 数据库：SQLite（WAL 模式）+ 版本化 SQL migration（手写 runner，不引入 Alembic）
- 调度：systemd timer，每日 15:00 PDT 后跑（美股收盘 13:00 PDT，EOD 数据约 14:30 PDT 可得）
- 交易日历（红队 M4）：timer 每天都会触发，但 pipeline 入口必须先判断是否为美股交易日；
  非交易日（周末/节假日）直接跳过写入，只更新 `freshness.checked_at`。
  禁止把周五的数据按周六日期入库（静默污染时间序列）。Phase 1 实现 `trading_day` helper。
- 前端：React + TypeScript + Vite + ECharts；独立静态应用，后端仅 serve 构建产物
- 产品矩阵预留：API 统一版本化 `/api/v1`，前后端完全解耦（无 SSR、无模板耦合），将来可整体迁入 monorepo 或独立域名
- 测试：pytest + vcrpy（外部 API 录制回放）+ freezegun + ruff（lint+format）
- 时区：全部时间统一存 ET，展示 "as of [ET 日期]"

## 架构（防 god object）

```
src/moneyflow/
  models.py        # Pydantic v2 全系统唯一契约
  ingest/          # 一源一 adapter，实现 SourceAdapter 协议（fetch→raw→parse→canonical）
  compute/         # 纯函数，无 I/O（exposure / momentum）
  store/           # Repository 模式，SQLite；换 Postgres 只改这一层
  services/        # 薄编排，按模块
  api/routers/     # 一模块一 router，只做校验+转发，~300 行软上限
  pipeline/        # 每日任务 CLI 入口（typer），幂等可单独重跑
  common/http.py   # 共享 httpx 客户端：合规 UA、重试、限流
```

- 依赖方向：`ingest` → `models`/`common`；`compute` → 仅 `models`（纯函数，
  连 `common` 都不许碰，杜绝 I/O 旁路）；`api` 只调 `services`。
  由 `tests/test_architecture.py` 强制断言（含相对导入解析），违规即红灯。
- 单文件软上限 ~300 行；DoD 用三类硬性测试（parser 契约 / 幂等重跑 / 新鲜度告警），覆盖率数字仅参考。

## 模块

- ~~M1 板块资金流~~ ❌ **v1 砍掉**（用户决策 2026-10-01，选项 D）。
  Phase 0 PoC 裁决：$0 无认证条件下无逐日资金流数据源（见 docs/POC.md）；
  备选 A（ETFdb 近5日净流入）一并否决。v2 再议（付费源/官方 API）。
- M2 持仓敞口快照（v1 重定义）：SSGA 11 只 ETF 每日官方持仓 → 个股跨板块敞口汇总
  （Σ权重；同一股票在多只板块 ETF 同时出现时加总，如 GOOGL 在 XLC/XLY）→ 敞口排名、
  板块集中度、权重日变化。面板强制标注"持仓快照、非资金流；权重日变化主要来自价格波动"；
  禁用"主力/聪明钱"标签。（原"持仓×板块流"公式因 M1 被砍而失效，此为 v1 诚实替代。）
- M3 板块动量/轮动：11 板块 ETF vs SPY 的 20/60 日相对强弱，简化 RRG 四象限。
  EOD 源用 Yahoo chart API（T+1 日频）；adapter 必须丢弃未收盘的当日 bar（红队 M5），
  不得以盘中价污染日 K 动量。
- M4 聪明钱（收缩版）：自选机构观察名单的 13F-HR（45 天滞后）+ Form 4（2 天滞后），双子面板
- M5 期权情绪：CBOE total + equity 双口径 put/call ratio（附解读注释）

## 分阶段

### Phase 0 — 数据源 PoC + 项目骨架
- 5 个源逐一 spike（ETF.com / SSGA 持仓 XLSX / EOD 行情源 / CBOE put-call CSV / EDGAR），
  输出 go/no-go；M1 主源失败当场定备选（VettaFi / ETFdb / ETF 单 profile 页）
- 骨架：仓库结构、数据契约、pytest+vcrpy、EDGAR 客户端（合规 UA+限流）、运维约定
- DoD：PoC 报告全绿 + 骨架测试全绿 + REDTEAM.md

### Phase 1 — M2 持仓敞口面板
- SSGA 11 只 ETF 日持仓 ingest → 跨板块敞口汇总（compute 纯函数）→ 面板；
  trading_day helper（非交易日跳过写入）；"每只 ETF 权重加总≈100%" 数据质量不变量测试
- DoD：面板可见可交互 + 三类硬性测试 + 新鲜度三件套（as-of 标注 / T+2 置灰告警 / 幂等写入）+ 红队签字

### Phase 2 — M3 板块动量/轮动面板
- EOD 源回填 90 天；adapter 丢弃未收盘当日 bar（红队 M5）
- DoD：面板 + 回填脚本 + 三类测试 + 红队签字

### Phase 3 — M4 聪明钱面板
- 观察名单在 Phase 3 开工前确定（用户确认）；EDGAR 合规（UA 含联系方式、≤10 req/s）
- DoD：双面板 + 滞后标注 + 三类测试 + 红队签字

### Phase 4 — M5 期权情绪 + hardening + 部署
- CBOE HTML parser 契约测试（golden fixture；Phase 4 开工前补 robots/ToS 检查）
- 部署目标：用户 VPS + systemd timer + SQLite WAL；部署文档 + CHANGELOG
- DoD：部署成功 + 端到端冒烟测试 + 最终红队签字

## 明确非目标（v1）

无盘中实时；全站日频 T+1；无实时期权流；13F 45 天滞后；不做 A 股；v1 无板块资金流（M1 已砍）。

## 阶段攻击清单（红队每阶段用）

坏数据/空值、API 宕机、上游 schema 漂移、限流 429、时区/日期对齐错误、
重复计算、ToS 违规、静默过期数据（新鲜度）。
