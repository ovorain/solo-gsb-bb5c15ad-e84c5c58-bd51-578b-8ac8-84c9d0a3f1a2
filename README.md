# 圆桌座位优化 API（Python + FastAPI）

在避开**禁邻宾客对**、满足**固定座位**的前提下，计算 2～12 位宾客围坐圆桌时
整圈（含首尾相邻）相邻得分最高的座位安排；同分时返回从 1 号位起宾客编号序列
**字典序最小**的排列；不存在可行排列时返回具体原因。

## 功能与规则

- 宾客人数 `n`：2～12，每人一席，座位从 **1** 顺次编号，1 号位与 `n` 号位相邻。
- **禁邻宾客对**：圆桌上不得相邻（含首尾）。
- **宾客对相邻得分**：未配置的宾客对按 **0 分**计；得分可为负数。
- **固定座位**：指定宾客必须坐在指定座位。
- 优化目标：整圈所有邻接边得分之和最大。
- 同分裁决：比较 `[1号位宾客, 2号位宾客, …, n号位宾客]` 的字典序，取最小者。
- **临时调整修复**（`/api/v1/seating/repair`）：在活动临时增删禁邻或固定座位后，
  以原座次为基准，先最小化**换座人数**（同座位宾客不同即计一人次），
  再最大化整圈得分，仍同分取字典序最小；原座次允许不满足新约束。
- 无可行排列：HTTP 200 响应中 `feasible=false` 并给出中文原因（HTTP 422 仅用于非法入参）。
- 两人（`n=2`）特殊处理：圆桌上两人之间只有一条邻接边，得分只计一次。

算法为位掩码 DP（状态 `(已入座集合, 末位宾客, 首位宾客)`），12 人规模亚秒级完成。
修复接口在同一 DP 上把状态值扩展为 `(换座人数, 得分, 后缀序列)`。

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

### `POST /api/v1/seating/repair` — 临时调整约束后修复排列

活动临时新增/取消禁邻或固定座位时使用。请求体在优化接口字段之外，额外携带
**原座次** `original_arrangement`（从 1 号位起的宾客编号完整排列）。
原座次须与 `guests` 同规模、无重复且编号合法（即 `1～n` 的一个排列）；
原座次**允许**不满足新的禁邻与固定座位约束。

```json
{
  "guests": 5,
  "forbidden_pairs": [{"a": 1, "b": 2}],
  "pair_scores": [{"a": 2, "b": 5, "score": 9}],
  "fixed_seats": [],
  "original_arrangement": [1, 2, 3, 4, 5]
}
```

服务端只在满足**新**禁邻与固定座位的安排中，依次优化：

1. **换座人数最少**：与原座次逐位比较，宾客不同的座位数最少（尽量保留已通知宾客的座位）；
2. **整圈得分最高**：换座人数相同时，最大化邻接得分之和；
3. **字典序最小**：仍相同时取从 1 号位起宾客编号序列字典序最小者。

成功响应沿用 `feasible / guests / arrangement / total_score / edge_scores / reason`
字段，并额外返回：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `changed_count` | int | 与原座次相比宾客发生变动的座位数 |
| `changed_seats` | [int] | 宾客发生变动的座位号（1 起，升序） |

```json
{
  "feasible": true,
  "guests": 5,
  "arrangement": [1, 4, 3, 2, 5],
  "total_score": 9.0,
  "edge_scores": [
    {"seats": [1, 2], "guests": [1, 4], "score": 0.0},
    {"seats": [2, 3], "guests": [3, 4], "score": 0.0},
    {"seats": [3, 4], "guests": [2, 3], "score": 0.0},
    {"seats": [4, 5], "guests": [2, 5], "score": 9.0},
    {"seats": [1, 5], "guests": [1, 5], "score": 0.0}
  ],
  "reason": null,
  "changed_count": 2,
  "changed_seats": [2, 4]
}
```

不存在满足新约束的排列时，与优化接口语义一致：HTTP 200 且
`feasible=false`、`arrangement` 为空并给出 `reason`，
此时 `changed_count` 与 `changed_seats` 均为 `null`。
`original_arrangement` 长度不符、编号越界或有重复宾客时返回 HTTP 422。

### `GET /health`

返回 `{"status": "ok"}`，Compose 健康检查使用该接口。

## 调用示例

```bash
curl -s http://localhost:8000/api/v1/seating/optimize \
  -H 'Content-Type: application/json' \
  -d '{"guests":4,"forbidden_pairs":[{"a":3,"b":4}]}'
```

临时新增禁邻 (1,2) 后，基于原座次 `[1,2,3,4,5]` 做最小换座修复：

```bash
curl -s http://localhost:8000/api/v1/seating/repair \
  -H 'Content-Type: application/json' \
  -d '{
    "guests": 5,
    "forbidden_pairs": [{"a": 1, "b": 2}],
    "pair_scores": [{"a": 2, "b": 5, "score": 9}],
    "original_arrangement": [1, 2, 3, 4, 5]
  }'
```

## 运行测试

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

测试包含：禁邻/固定座位/闭合边计分/字典序裁决等场景、2～6 人下与全排列暴力枚举的
随机对拍（含同分裁决），以及 12 人规模的性能校验。

## 项目结构

```
.
├── app/
│   ├── main.py       # FastAPI 应用与路由
│   ├── models.py     # 请求/响应模型与入参校验
│   ├── service.py    # 业务编排（规范化输入 -> 求解 -> 响应）
│   └── solver.py     # 位掩码 DP 优化算法与无可行原因诊断
├── tests/            # pytest 测试（算法对拍 + API）
├── start.sh          # 本地单命令启动（自动建 venv、装依赖、启动）
├── Dockerfile        # 容器镜像（构建期安装依赖）
├── docker-compose.yml
└── requirements.txt
```
