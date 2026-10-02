# US Money Flow Tracker

美股资金追踪网页：$0 数据源，日频 T+1。实施计划见 [PLAN.md](PLAN.md)。

## 快速开始（Phase 0）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"   # 或 pip install ".[dev]"（需构建后端，见下）
```

> 说明：本仓库采用 `src/` 布局但暂未配置构建后端，开发期直接用
> `PYTHONPATH=src` 运行；`pip install -e .` 需要补充 `[build-system]`（Phase 0 待定）。

```bash
export PYTHONPATH=src
pytest            # 后端测试（含架构测试）
ruff check src tests && ruff format --check src tests
PYTHONPATH=src python -m moneyflow.pipeline.daily --help
```

前端（`web/`）：`cd web && npm install && npm run dev`（Phase 1 起联调）。

## 每日任务

`systemd/moneyflow-daily.{service,timer}`：每日 15:00 PDT 后执行
`python -m moneyflow.pipeline.daily run-all`。
