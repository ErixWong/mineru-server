# 仓库目录拉平评估

## 背景

当前仓库的核心服务代码位于 `mcp-server/` 下：

```text
mcp-server/
├── pyproject.toml
├── src/mineru_mcp/
├── tests/
├── admin-ui/
├── .env.example
└── README.md
```

但仓库根目录已经承载了产品级入口：

- `Dockerfile` / `Dockerfile.slim`
- `docker-compose.yml`
- `README.md`
- `docs/`
- GitHub Actions Docker 发布流程

这说明项目已经从“一个仓库里放一个 MCP 子项目”演进为“一个完整 mineru-server 产品”。继续保留 `mcp-server/` 这层会让服务根目录、仓库根目录、Docker 工作目录和本地运行目录语义不一致。

## 结论

建议拉平到仓库根目录。

拉平后，仓库根目录就是服务根目录：

```text
mineru-server/
├── pyproject.toml
├── src/mineru_mcp/
├── tests/
├── admin-ui/
├── docs/
├── Dockerfile
├── Dockerfile.slim
├── docker-compose.yml
├── README.md
└── .env.example
```

这样更符合当前产品形态，也能减少新开发者对 `cd mcp-server`、`mcp-server/admin-ui`、`/app/mcp-server` 的理解成本。

## 收益

- 本地开发入口统一：在仓库根执行 `py -3.13 -m pip install -e .`、`py -3.13 -m pytest`。
- Docker 构建路径更自然：`COPY . /app` 或只复制根目录下的 package/source。
- `.env.example` 回到根目录后语义更清晰：它是服务配置模板，不再是外层仓库配置。
- Admin UI 不再被误认为只是 MCP 子模块的一部分。
- 文档可减少大量 `mcp-server/` 前缀，降低维护成本。
- 删除 `mcp-server/mcp-server/output` 这类由错误工作目录造成的历史产物。

## 风险

- 影响面偏广，属于中等风险重构。
- Dockerfile 和 `.dockerignore` 路径需要同步调整，否则镜像构建会失败或上下文过大。
- `.gitignore` 当前对根 `tests/` 和 `test_*.py` 有特殊忽略规则，迁移后必须重写，否则测试文件可能被误忽略。
- 历史文档中有大量 `mcp-server/src/...` 引用，需要区分当前文档和历史资料，避免无意义大改。
- 本地已有 `mcp-server/.env`，迁移时需要提供人工迁移提示，不应自动提交真实 `.env`。

## 推荐策略

分两步做：

1. 目录拉平 PR
   - 移动核心工程文件。
   - 更新 Docker、CI、README、AGENTS、忽略规则。
   - 保证后端测试、前端 build、Docker Compose config 通过。

2. 历史资料清理 PR
   - 整理 `mcp-server/docs` 到 `docs/archive` 或删除过期内容。
   - 处理 `check_*.py`、`debug_*.py`、`test_string.py`、`reassign_task_caller.py` 等本地脚本。
   - 删除错误工作目录产物。

## 当前建议

可以开始执行目录拉平，但建议先提交或暂存当前未提交的配置文档改动，再开一个新的重构分支。目录移动会产生大量 rename diff，和配置口径改动混在一起会降低审查体验。
