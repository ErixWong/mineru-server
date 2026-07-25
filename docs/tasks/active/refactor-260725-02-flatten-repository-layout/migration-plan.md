# 迁移执行清单

## 目标结构

```text
.
├── pyproject.toml
├── src/
├── tests/
├── admin-ui/
├── docs/
├── Dockerfile
├── Dockerfile.slim
├── docker-compose.yml
├── README.md
├── AGENTS.md
└── .env.example
```

## 文件移动

- `mcp-server/pyproject.toml` -> `pyproject.toml`
- `mcp-server/src/` -> `src/`
- `mcp-server/tests/` -> `tests/`
- `mcp-server/admin-ui/` -> `admin-ui/`
- `mcp-server/.env.example` -> `.env.example`
- `mcp-server/README.md` -> 评估后删除、合并进根 `README.md`，或改名为 `docs/python-package.md`

不迁移真实本地文件：

- `mcp-server/.env`
- `mcp-server/output/`
- `mcp-server/.pytest_cache/`
- `mcp-server/mcp-server/output/`

## Docker 调整

`Dockerfile` 和 `Dockerfile.slim`：

- `COPY mcp-server/admin-ui/...` 改为 `COPY admin-ui/...`
- `COPY mcp-server/ /app/mcp-server/` 改为复制根工程到 `/app`
- `COPY --from=admin-ui-builder ... /app/mcp-server/admin-ui/dist/` 改为 `/app/admin-ui/dist/`
- `WORKDIR /app/mcp-server` 改为 `WORKDIR /app`
- `pip install --no-cache-dir -e .` 保持不变

`docker-compose.yml`：

- 不需要依赖源码目录路径。
- 保持运行时配置从宿主环境变量、CI secret 或外部 `--env-file` 注入。

`.dockerignore`：

- `!mcp-server/README.md` 改为保留必要根文件。
- `mcp-server/admin-ui/node_modules/` 改为 `admin-ui/node_modules/`。
- 确认不要把 `src/`、`pyproject.toml`、`admin-ui/package*.json` 排除出 Docker build context。

## Python 调整

- 根目录执行 `py -3.13 -m pip install -e .`。
- 根目录执行 `py -3.13 -m pytest`。
- `pyproject.toml` 中 `readme = "README.md"` 保持可用。
- `Documentation` URL 从 `/tree/main/mcp-server` 改为仓库根或 docs 页面。

## 前端调整

- 前端目录从 `mcp-server/admin-ui` 改为 `admin-ui`。
- 本地命令改为：

```bash
cd admin-ui
npm install
npm run dev
npm run build
```

## 文档调整

必须更新：

- `README.md`
- `docs/README.md`
- `AGENTS.md`

按需更新：

- `docs/mineru/config_flow.md`
- `docs/mineru/llm_requirements.md`
- `docs/mineru/container_usage.md`
- `docs/design/git-version-control-workflow.md`

历史文档可以保留旧路径，但应加注“迁移前路径”，避免误导当前开发。

## 验证命令

```bash
py -3.13 -m pip install -e ".[test]"
py -3.13 -m pytest
cd admin-ui
npm run build
cd ..
$env:MINERU_CALLER_KEY_MASTER_KEY='AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
docker compose config
docker build -f Dockerfile.slim -t mineru-mcp:flatten-smoke .
```

Docker build 体积和耗时较高，可在本地先跑 `docker compose config`，完整镜像构建放到 PR CI 或用户确认后执行。

## 回滚策略

- 使用单独分支执行。
- 每一类移动尽量让 Git 识别为 rename。
- 不删除真实 `.env` 和本地产物，只从 Git 跟踪范围和文档口径中移除。
- 若 Docker 或测试失败，可以先回退 Docker 路径调整，不影响 Python 包移动的判断。
