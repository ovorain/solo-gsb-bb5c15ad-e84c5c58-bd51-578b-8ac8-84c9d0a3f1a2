# 圆桌座位优化 API（Python + FastAPI）

在避开**禁邻宾客对**、满足**固定座位**的前提下，计算 2～12 位宾客围坐圆桌时
整圈（含首尾相邻）相邻得分最高的座位安排；同分时返回从 1 号位起宾客编号序列
**字典序最小**的排列；不存在可行排列时返回具体原因。另提供**座次修复**接口：
临时调整约束时，先最小化换座人数、再最大化得分，尽量保留已通知宾客的原座位。

## 功能与规则

- 宾客人数 `n`：2～12，每人一席，座位从 **1** 顺次编号，1 号位与 `n` 号位相邻。
- **禁邻宾客对**：圆桌上不得相邻（含首尾）。
- **宾客对相邻得分**：未配置的宾客对按 **0 分**计；得分可为负数。
- **固定座位**：指定宾客必须坐在指定座位。
- 优化目标：整圈所有邻接边得分之和最大。
- 同分裁决：比较 `[1号位宾客, 2号位宾客, …, n号位宾客]` 的字典序，取最小者。
- 无可行排列：HTTP 200 响应中 `feasible=false` 并给出中文原因（HTTP 422 仅用于非法入参）。
- 两人（`n=2`）特殊处理：圆桌上两人之间只有一条邻接边，得分只计一次。
- **修复接口** `/api/v1/seating/repair`：活动临时调整约束（新增禁邻、固定座位等）时，
  在所有满足新约束的安排中依次按 **换座人数最少 → 整圈得分最高 → 座次字典序最小** 择优，
  尽量保留已通知宾客的原座位；原座次允许不符合新约束。

算法为位掩码 DP（状态 `(已入座集合, 末位宾客, 首位宾客)`），优化接口在 12 人规模
亚秒级完成；修复接口因需额外追踪换座数，12 人最坏情况下约数秒内完成。

## 单条启动命令

### 方式一：Docker Compose（推荐）

```bash
docker compose up --build
```

启动后服务地址：<http://localhost:8000>

- 在线接口文档（Swagger UI）：<http://localhost:8000/docs>
- 健康检查：<http://localhost:8000/health>

如需改用宿主机其他端口（容器内始终监听 `PORT`）：

```bash
SEATING_PORT=9000 docker compose up --build     # 宿主机访问 http://localhost:9000
```

### 方式二：本地源码（一条命令完成依赖安装与应用初始化）

```bash
./start.sh
```

首次运行自动创建 `.venv` 虚拟环境、安装 `requirements.txt` 中的依赖并启动服务；
之后再次运行直接启动。需要 Python 3.11+ 与 venv 支持（Debian/Ubuntu：
`apt-get install python3-venv`）。

## 必要配置

| 配置项 | 环境变量 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 监听地址 | `HOST` | `0.0.0.0` | 服务绑定地址 |
| 监听端口 | `PORT` | `8000` | 容器/进程内监听端口 |
| 宿主机映射端口 | `SEATING_PORT` | `8000` | 仅 Compose 使用，映射到 `PORT` |

## API

### `POST /api/v1/seating/optimize` — 计算最优排列

请求体：

```json
{
  "guests": 5,
  "forbidden_pairs": [{"a": 1, "b": 2}],
  "pair_scores": [
    {"a": 1, "b": 3, "score": 10},
    {"a": 2, "b": 4, "score": -2}
  ],
  "fixed_seats": [{"seat": 1, "guest": 3}]
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `guests` | int | 是 | 宾客人数，2～12 |
| `forbidden_pairs` | `[{a,b}]` | 否 | 禁邻宾客对，宾客编号 1～n |
| `pair_scores` | `[{a,b,score}]` | 否 | 相邻得分，未配置按 0 分计 |
| `fixed_seats` | `[{seat,guest}]` | 否 | 固定座位指派 |

成功响应（可行）：

```json
{
  "feasible": true,
  "guests": 5,
  "arrangement": [3, 1, 5, 4, 2],
  "total_score": 8.0,
  "edge_scores": [
    {"seats": [1, 2], "guests": [1, 3], "score": 10.0},
    {"seats": [2, 3], "guests": [1, 5], "score": 0.0}
  ],
  "reason": null
}
```

`arrangement[i]` 表示第 `i+1` 号座位上的宾客编号；`edge_scores` 给出每条圆桌邻接边
（座位、宾客、得分）的明细，首尾边同样包含在内。

成功响应（无可行排列，HTTP 200）：

```json
{
  "feasible": false,
  "guests": 4,
  "arrangement": [],
  "total_score": 0.0,
  "edge_scores": [],
  "reason": "固定座位迫使宾客 1（1 号位）与宾客 2（2 号位）相邻，但二人互为禁邻"
}
```

非法入参（编号越界、同一对宾客既禁邻又打分、宾客被固定到多个座位等）返回 HTTP 422。

### `POST /api/v1/seating/repair` — 临时调整约束后修复座次

适用于活动开始前临时调整禁邻或固定座位、但宾客已按原座次收到通知的场景：在满足
**新约束**（新禁邻、新固定座位、沿用的相邻得分）的所有安排中，

1. **先最小化换座人数**（新座次与 `original_arrangement` 不同的座位数，等价于被移动的宾客数）；
2. 换座人数相同时，**最大化整圈得分**；
3. 仍相同时，取从 1 号位起宾客编号序列**字典序最小**的排列。

请求体在优化接口全部字段的基础上增加 `original_arrangement`：

```json
{
  "guests": 5,
  "forbidden_pairs": [{"a": 1, "b": 2}],
  "pair_scores": [
    {"a": 1, "b": 3, "score": 10},
    {"a": 2, "b": 4, "score": -2}
  ],
  "fixed_seats": [{"seat": 1, "guest": 3}],
  "original_arrangement": [5, 1, 3, 4, 2]
}
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `guests` / `forbidden_pairs` / `pair_scores` / `fixed_seats` | — | — | 同优化接口，均以**新约束**为准 |
| `original_arrangement` | int[] | 是 | 原座次：从 1 号位起的宾客编号完整排列。长度必须等于 `guests`，无重复且编号在 1～n 内；**允许不符合新约束**（例如原座次违反新增禁邻或固定座位） |

成功响应（可行）沿用优化接口的 `feasible`、`guests`、`arrangement`、`total_score`、
`edge_scores`、`reason` 字段，并额外返回换座信息：

```json
{
  "feasible": true,
  "guests": 5,
  "arrangement": [3, 1, 5, 4, 2],
  "total_score": 8.0,
  "edge_scores": [
    {"seats": [1, 2], "guests": [1, 3], "score": 10.0}
  ],
  "reason": null,
  "moved_guests": 2,
  "changed_seats": [1, 3]
}
```

| 字段 | 说明 |
| --- | --- |
| `moved_guests` | 换座人数（新座次与原座次不同的座位数量，与被移动的宾客数相等） |
| `changed_seats` | 发生变动的座位号列表（升序）；未变动的宾客保留其原座位 |

说明：

- 原座次本身满足新约束时，`moved_guests=0`、`changed_seats=[]`，原样返回原座次
  （即使存在得分更高的其他排列）。
- 两人（`n=2`）圆桌仍只计一条邻接边；两种座次同边同分时视为零换座，保留原座次。
- 新约束下无可行排列时，语义与优化接口一致：HTTP 200、`feasible=false`、
  `arrangement`/`edge_scores`/`changed_seats` 为空、`moved_guests=0`，并给出 `reason`。
- `original_arrangement` 长度不符、含重复宾客或编号越界时返回 HTTP 422。

### `GET /health`

返回 `{"status": "ok"}`，Compose 健康检查使用该接口。

## 调用示例

```bash
curl -s http://localhost:8000/api/v1/seating/optimize \
  -H 'Content-Type: application/json' \
  -d '{"guests":4,"forbidden_pairs":[{"a":3,"b":4}]}'
```

临时新增禁邻 (3,4)，在保留原座次 `[4,3,2,1]` 尽量多座位的前提下修复：

```bash
curl -s http://localhost:8000/api/v1/seating/repair \
  -H 'Content-Type: application/json' \
  -d '{"guests":4,"forbidden_pairs":[{"a":3,"b":4}],"original_arrangement":[4,3,2,1]}'
```

返回（仅 1、4 号座位互换，换座人数 2）：

```json
{
  "feasible": true,
  "guests": 4,
  "arrangement": [1, 3, 2, 4],
  "total_score": 0.0,
  "edge_scores": [
    {"seats": [1, 2], "guests": [1, 3], "score": 0.0},
    {"seats": [2, 3], "guests": [2, 3], "score": 0.0},
    {"seats": [3, 4], "guests": [2, 4], "score": 0.0},
    {"seats": [1, 4], "guests": [1, 4], "score": 0.0}
  ],
  "reason": null,
  "moved_guests": 2,
  "changed_seats": [1, 4]
}
```

## 运行测试

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

测试包含：禁邻/固定座位/闭合边计分/字典序裁决等场景、2～6 人下与全排列暴力枚举的
随机对拍（优化与修复接口均覆盖，含同分裁决与最少换座裁决），以及 12 人规模的性能校验。

## 项目结构

```
.
├── app/
│   ├── main.py       # FastAPI 应用与路由（optimize / repair）
│   ├── models.py     # 请求/响应模型与入参校验（含原座次完整性校验）
│   ├── service.py    # 业务编排（规范化输入 -> 求解 -> 响应）
│   └── solver.py     # 位掩码 DP：最优排列与最少换座修复、无可行原因诊断
├── tests/            # pytest 测试（算法对拍 + API）
├── start.sh          # 本地单命令启动（自动建 venv、装依赖、启动）
├── Dockerfile        # 容器镜像（构建期安装依赖）
├── docker-compose.yml
└── requirements.txt
```
