"""最小化测试端点"""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"status": "ok", "app": "mongolia-drug-intel"}

@app.get("/api/stats")
async def stats():
    return {"total": 0}
