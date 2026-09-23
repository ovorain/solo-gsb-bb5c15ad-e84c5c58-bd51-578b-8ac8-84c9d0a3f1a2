"""圆桌座位优化 FastAPI 应用。

启动（本地源码方式）：

    ./start.sh

启动（容器方式）：

    docker compose up --build

默认服务地址 http://0.0.0.0:8000，可通过环境变量 ``PORT`` 修改端口。
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models import SeatingRequest
from app.service import optimize

app = FastAPI(
    title="圆桌座位优化 API",
    description=(
        "在避开禁邻宾客对、满足固定座位的前提下，"
        "最大化圆桌整圈（含首尾相邻）的相邻得分；"
        "同分时返回从 1 号位起宾客编号序列字典序最小的排列。"
    ),
    version="1.0.0",
)


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/seating/optimize",
    tags=["座位优化"],
    summary="计算圆桌最优座位排列",
)
def optimize_seating(request: SeatingRequest) -> dict:
    return optimize(request).model_dump()


@app.exception_handler(ValidationError)
def _validation_exception_handler(_request, exc: ValidationError) -> JSONResponse:
    # 业务校验器中以 ValueError 抛出的错误在此转成标准 422 响应
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
