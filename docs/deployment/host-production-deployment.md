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

## 入站依赖与 GPU 约束

- nginx 配置 `/docker/nginx/site/ocr.ai.erix.vip.conf` 当前按
  `proxy_pass http://172.20.0.116:8002` 反代。修改 MCP 静态 IP 或切换网络
  前，必须同步评估并修改 nginx；本任务不修改 nginx/frp 配置。
- 本机 RTX 3080 20GB 同时运行 llama-server 和 paddleocr，实测已有约
  17.9GB 被占用。因此 `/home/eric/projects/mineru_mcp/.env` 必须使用
  `VLLM_GPU_MEMORY_UTILIZATION=0.3`；仓库模板默认值 `0.5` 只服务通用机器，
  在本机重启 VLM 时可能按更高比例预留显存并 OOM。VLM 的实际重启仍由
  Portainer stack 130 负责。
