# 本机生产部署 Runbook

本文是本机生产环境的操作手册。仓库根目录的 `docker-compose.yml` 是通用
模板，本文件对应的 `docker-compose.prod.yml` 只承载本机的网络和宿主机脚本
路径差异；不要再维护 `~/projects/mineru_mcp/docker-compose.yml` 的手改副本。

## 服务拓扑与归属

| 服务 | 归属 | 关键约束 |
| --- | --- | --- |
| `mineru-mcp-all-in-one`（Compose service `mineru-mcp`） | 本仓库的 Compose（base + prod overlay） | 外部网络 `prod`，固定 `172.20.0.116` |
| `mineru-vlm-server`（Compose service `vlm-server`） | Portainer stack `mineru-mcp`，stack ID `130` | 外部网络 `prod`，固定 `172.20.0.118`，网络别名 `vlm-server` |

在 Portainer 的 **Stacks** 页面可查看 stack 名称和 ID；也可以用下面的只读命令
确认 VLM 容器仍由 stack 130 的 compose 文件管理：

```bash
sg docker -c "docker inspect mineru-vlm-server \
  --format '{{ index .Config.Labels \"com.docker.compose.project.config_files\" }}'"
# 预期包含 /data/compose/130/docker-compose.yml
```

`MINERU_VL_SERVER=http://vlm-server:30000/v1` 依赖 `prod` 网络中的服务名解析。
公网 nginx 入口则直接依赖 MCP 容器的静态地址，见下文入站依赖说明。

## `--no-deps` 铁律

虽然仓库 base 为新机器保留了 `vlm-server` 声明和 `depends_on`，本机线上
`mineru-vlm-server` 实际归 Portainer stack 130 管理，不归本仓库 Compose
创建或升级。如果对本仓库执行普通 `up`，Compose 会尝试处理声明的依赖，
可能与 Portainer 已存在的 `mineru-vlm-server` 撞容器名，甚至干扰线上 VLM。

因此本机只允许对 MCP 服务执行带 `--no-deps` 的命令；不要对本机 VLM 执行
`up`、`pull`、`stop`、`restart` 或删除操作。VLM 的生命周期由 Portainer
stack 130 负责。

## 配置与密钥的存放位置

运行配置（含密钥）存放在 **`/home/eric/projects/mineru_mcp/.env`**（权限 `600`，属主 `eric`）。

**不要**把它挪进 `/docker/mineru-mcp/`：那个目录由容器内 root 进程写入，宿主机上是
`root:root`，人类操作者没有写权限，放进去会导致后续改配置必须借助容器才能完成。
约定是：`/docker/mineru-mcp/` 放**数据**（容器读写），部署目录放**配置**（人写、容器只读）。

## 标准部署/升级流程

1. 确认仓库分支和目标镜像，检查 `/home/eric/projects/mineru_mcp/.env` 中至少有：
   `MINERU_DATA_DIR=/docker/mineru-mcp`、CPU 镜像
   `MINERU_IMAGE=ghcr.io/erixwong/mineru-server:latest-slim-cpu`、
   `VLLM_GPU_MEMORY_UTILIZATION=0.3` 和
   `VLLM_HEALTHCHECK_START_PERIOD=120s`，以及真实密钥。
   **自 #43（多用户门户 + 页数预充值额度，2026-10 合入）起还必须有：**
   `MINERU_CALLER_KEY_MASTER_KEY=<Fernet key>`（32 字节 url-safe base64，生成：
   `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`）。
   该密钥用于加密 caller/user 的 API key，**丢失将导致存量 API key 无法解密**，
   务必与 `.env` 一起妥善备份；未设置时新镜像会直接拒绝启动（RuntimeError:
   `MINERU_CALLER_KEY_MASTER_KEY is required`）。
2. 先只渲染配置，确认 `172.20.0.116`、三条数据挂载和镜像 tag 正确：

   ```bash
   docker compose \
     -f docker-compose.yml \
     -f docker-compose.prod.yml \
     --env-file /home/eric/projects/mineru_mcp/.env \
     config
   ```

3. 仅升级本仓库服务：

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     --env-file /home/eric/projects/mineru_mcp/.env up -d --no-deps mineru-mcp
   ```

4. 升级后检查 MCP 健康状态和 nginx 入口；不要因为 MCP 升级而重建
   Portainer 管理的 VLM。

## 回滚

升级前保存本次使用的 compose 文件和环境文件（环境文件只能保存在受限目录，
不要提交到 Git）：

```bash
cp docker-compose.yml /docker/mineru-mcp/docker-compose.yml.<date>
cp docker-compose.prod.yml /docker/mineru-mcp/docker-compose.prod.yml.<date>
cp /home/eric/projects/mineru_mcp/.env /home/eric/projects/mineru_mcp/.env.<date>
```

回滚时将 `MINERU_IMAGE` 覆盖为已验证的镜像回滚 tag（例如
`rollback-<date>`），并用对应的 compose 备份文件渲染、只更新 MCP：

```bash
MINERU_IMAGE=ghcr.io/erixwong/mineru-server:rollback-<date> \
docker compose \
  -f /docker/mineru-mcp/docker-compose.yml.<date> \
  -f /docker/mineru-mcp/docker-compose.prod.yml.<date> \
  --env-file /home/eric/projects/mineru_mcp/.env \
  up -d --no-deps mineru-mcp
```

回滚前后都必须保留 `MINERU_DATA_DIR=/docker/mineru-mcp` 和
`--no-deps`，避免切换数据目录或触碰 Portainer 的 VLM。

## 首次从 fork 迁移到本流程（一次性）

把线上从手改 fork 切到本流程时，compose project 名会从 fork 目录名（`mineru_mcp`）
变为本仓库目录名（`mineru-server`），因此虽然 `container_name` 未变，compose 仍会报
容器名冲突并拒绝创建：

```
Error response from daemon: Conflict. The container name "/mineru-mcp-all-in-one"
 is already in use by container "<旧容器 ID>".
```

处理：先删除**旧 MCP 容器**再执行标准命令。所有状态都在 bind mount 里（`tasks.db`、
输出、模型缓存），删容器不丢数据。

```bash
sg docker -c "docker rm mineru-mcp-all-in-one"   # 只删 MCP；绝对不要删 mineru-vlm-server
```

如果跳过这一步而反复重试 `up`，会一直失败（不会自动替换别的项目的容器）。

## 已知继承项：`mineru-mcp` 的 GPU 预留

base 模板给 `mineru-mcp` 声明了 GPU 预留（`deploy.resources.reservations.devices`，
注释为“GPU 支持（可选）”，服务 full 镜像在容器内跑本地推理/GPU OCR 的场景）。

本机跑的是 **CPU flavor 镜像**，实测无影响：镜像内 torch 无 CUDA
（`torch.cuda.is_available()=False`、`device_count()=0`），宿主机显存无任何增长。
注意 Compose **无法**用 overlay 删除序列项（在 `docker-compose.prod.yml` 写
`devices: []` 会被忽略），所以只能接受它随模板生效。

若日后把 `MINERU_IMAGE` 换成 CUDA flavor（为了本地 OCR 走 GPU），必须重新验证显存：
本机 RTX 3080 20GB 上 llama-server + paddleocr 已占约 17.9GB。

## 数据目录

| 路径 | 容器挂载 | 内容 | 可否丢失 |
| --- | --- | --- | --- |
| `/docker/mineru-mcp/input` | `/app/input:ro` | 待解析的输入文件 | 可重新上传，但未备份的输入会丢失 |
| `/docker/mineru-mcp/output` | `/app/output:rw` | 任务数据库、解析结果和交付物 | **不可丢**；包含任务状态、caller 数据和结果 |
| `/docker/mineru-mcp/models` | `/root/.cache:rw` | MinerU、HuggingFace、ModelScope 模型缓存 | 可重新下载，但恢复时间长、需要外部模型源 |

`/docker/mineru-mcp/output/patches/` 曾用于 bind mount 热修 `app.py`，该机制
已随 #35 入库废止；不要再把它挂载进容器，也不要把它当作升级手段。
归档副本见 `/docker/mineru-mcp/output/retired-patches-260913/`。

`/docker/mineru-mcp/scripts/vlm-entrypoint.sh` 是 **Portainer stack 130 所用的
宿主机副本**（该 stack 的配置不由本仓库管理，因此 `docker-compose.prod.yml`
仍指向这个副本）。它与仓库的 `scripts/vlm-server-entrypoint.sh` 是同一份逻辑，
**修改其一时必须同步另一份**，否则线上 VLM 会跑在与仓库不一致的脚本上。

## 备份与恢复

### 备份对象与一致性

生产数据至少要备份以下内容，并将备份放到与生产数据盘不同的受控位置：

- `/docker/mineru-mcp/output/tasks.db`：任务状态、caller/user、管理会话和额度等数据库数据。
  SQLite 开启 WAL 模式时，旁边可能出现 `tasks.db-wal` 和 `tasks.db-shm`：`-wal`
  是尚未 checkpoint 回主数据库文件的写前日志，`-shm` 是 WAL 的共享内存索引；
  它们是 SQLite 正常运行文件，不代表数据库损坏。
- `/docker/mineru-mcp/output/` 下的解析结果和交付物。只备份数据库不能恢复 PDF、
  Markdown、图片等结果文件。
- `/home/eric/projects/mineru_mcp/.env`：包含运行配置及解密 caller/user API key 所需的
  `MINERU_CALLER_KEY_MASTER_KEY`。该密钥丢失会导致**存量 caller/user API key 全部无法解密**；
  恢复数据库时必须使用与其配套的 `.env` 和主密钥。

不要在服务写入期间直接 `cp tasks.db`：最近提交的事务可能仍只在 `-wal` 中，单拷
主数据库文件会漏掉这些事务，且拷贝过程中的文件不保证对应同一个一致时点。SQLite
的 `-wal` 保存 WAL 模式下的变更，`-shm` 保存 WAL 索引；运行中的数据库实际状态可能由
`tasks.db` 与 `-wal` 共同构成，不能把三个文件当成可随意分开复制的普通文件。
容器**干净停止**后，最后一个 SQLite 连接关闭会 checkpoint，将 WAL 中已提交数据并回
主库；此时直接拷贝 `tasks.db` 是安全的。异常杀进程或主机掉电不等同于干净停止。

### 备份方式

① **推荐：在线脚本备份，不停服务。** 在仓库根目录运行；脚本使用 Python 标准库
`sqlite3.Connection.backup()`，只读打开源库，并校验完整性和关键表行数：

```bash
scripts/backup-db.sh \
  --db /docker/mineru-mcp/output/tasks.db \
  --out /home/eric/backups/mineru-mcp \
  --keep 7
```

`--db` 默认是生产数据库路径，`--out` 默认是
`$MINERU_BACKUP_DIR`（未设置时 `/home/eric/backups/mineru-mcp`），`--keep` 默认保留
最新 7 份且必须大于 0。脚本会创建目标目录；备份文件以 UTC 时间命名。

② **在线执行 `VACUUM INTO`。** 这是一条 SQLite SQL，可生成一致的数据库副本；目标路径
必须对执行 SQL 的进程可写。以下示例在容器 `/tmp` 生成副本，再复制到宿主机备份目录：

```bash
mkdir -p /home/eric/backups/mineru-mcp
docker exec mineru-mcp-all-in-one python3 -c \
  "import sqlite3; c=sqlite3.connect('/app/output/tasks.db'); c.execute(\"VACUUM INTO '/tmp/tasks-vacuum-20261006T000000Z.db'\"); c.close()"
docker cp mineru-mcp-all-in-one:/tmp/tasks-vacuum-20261006T000000Z.db \
  /home/eric/backups/mineru-mcp/
```

③ **停容器后直接复制。** 仅当容器正常、干净停止后才可只拷 `tasks.db`；停止期间不会提供
服务：

```bash
docker stop --time 120 mineru-mcp-all-in-one
docker inspect --format 'ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}' \
  mineru-mcp-all-in-one
mkdir -p /home/eric/backups/mineru-mcp
docker cp mineru-mcp-all-in-one:/app/output/tasks.db \
  /home/eric/backups/mineru-mcp/tasks-$(date -u +%Y%m%dT%H%M%SZ).db
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file /home/eric/projects/mineru_mcp/.env \
  up -d --no-deps mineru-mcp
```

### 恢复流程

1. 停止 MCP 容器并确认其已干净退出（预期 `ExitCode=0` 且 `OOMKilled=false`；若非如此，
   不要假定 WAL 已 checkpoint）。生产数据目录属 root，以下宿主机文件操作需有 root 权限：

   ```bash
   docker stop --time 120 mineru-mcp-all-in-one
   docker inspect --format 'ExitCode={{.State.ExitCode}} OOMKilled={{.State.OOMKilled}}' \
     mineru-mcp-all-in-one
   ```

2. 将现有数据库改名存档，**不要直接覆盖**；同时将仍存在的旧 `-wal`/`-shm` 移出原路径：

   ```bash
   db=/docker/mineru-mcp/output/tasks.db
   stamp=$(date -u +%Y%m%dT%H%M%SZ)-$$
   archive="${db}.before-restore-${stamp}"
   sudo mv -- "$db" "$archive"
   for suffix in -wal -shm; do
     if sudo test -e "${db}${suffix}"; then
       sudo mv -- "${db}${suffix}" "${archive}${suffix}"
     fi
   done
   ```

3. 将备份库放回原路径。以下做法先复制到临时文件，并从存档库继承属主和权限，再原子改名；
   同时恢复与该数据库匹配的 `output/` 交付物和 `.env`（尤其是相同的
   `MINERU_CALLER_KEY_MASTER_KEY`）：

   ```bash
   backup=/home/eric/backups/mineru-mcp/tasks-20261005T153000Z.db  # 替换为实际要恢复的备份文件
   restored="${db}.restore"
   sudo cp -- "$backup" "$restored"
   sudo chown --reference="$archive" "$restored"
   sudo chmod --reference="$archive" "$restored"
   sudo mv -- "$restored" "$db"
   ```

4. 按标准流程启动 MCP：

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.prod.yml \
     --env-file /home/eric/projects/mineru_mcp/.env \
     up -d --no-deps mineru-mcp
   ```

5. 校验 `/health` 返回正常、管理台任务列表可见，并抽查任务数与备份一致。必要时可在
   启动服务前对恢复库运行 SQLite `PRAGMA integrity_check` 和关键表行数核对。

### 恢复演练

定期将备份恢复到**临时路径**，检查 `PRAGMA integrity_check` 为 `ok`、关键表行数与备份
记录一致，并让应用数据库层能打开和查询该副本。**不要拿生产路径练习恢复**，也不要让
演练副本覆盖生产库。

### 数据库选型决策

当前维持 SQLite：单实例是明确设计，写入量极小，SQLite 不增加独立数据库服务的运维成本；
切换数据库需要改写全部 SQL/DDL 并增加部署复杂度，当前收益为零。仅在出现多副本/HA
需要共享状态、外部 BI/报表直连、单实例写入成为瓶颈，或统一运维平台要求时触发迁移评估；
届时选择 PostgreSQL，而不是 MariaDB。

## 入站依赖与 GPU 约束

- nginx 配置 `/docker/nginx/site/ocr.ai.erix.vip.conf` 当前按
  `proxy_pass http://172.20.0.116:8002` 反代。修改 MCP 静态 IP 或切换网络
  前，必须同步评估并修改 nginx；本任务不修改 nginx/frp 配置。
- 本机 RTX 3080 20GB 同时运行 llama-server 和 paddleocr，实测已有约
  17.9GB 被占用。因此 `/home/eric/projects/mineru_mcp/.env` 必须使用
  `VLLM_GPU_MEMORY_UTILIZATION=0.3`；仓库模板默认值 `0.5` 只服务通用机器，
  在本机重启 VLM 时可能按更高比例预留显存并 OOM。VLM 的实际重启仍由
  Portainer stack 130 负责。
