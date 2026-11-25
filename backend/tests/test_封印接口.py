"""快照封印写闸 · API 层夹具：封印入口、核证/影子只读接口契约。"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("数据目录", tempfile.mkdtemp(prefix="daysnap-api-"))
os.environ.setdefault("夹具目录", str(Path(__file__).resolve().parents[2] / "fixtures"))

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  
from fastapi.testclient import TestClient  

from app.main import app  


@pytest.fixture()
def 客户(干净库):
    with TestClient(app) as c:
        yield c


def _铺三日(客户):
    assert 客户.post("/api/重置业务库", json={}).status_code == 200
    assert 客户.post("/api/装载夹具", json={"名": "三日连环样例.json"}).status_code == 200
    for 日 in ("2026-11-20", "2026-11-21", "2026-11-22"):
        assert 客户.post("/api/抽取", json={"营业日": 日}).status_code == 200


def test_封印核证_初始未封印(客户):
    _铺三日(客户)
    r = 客户.get("/api/封印核证", params={"营业日": "2026-11-22"})
    assert r.status_code == 200
    d = r.json()
    assert d["已封印"] is False
    assert d["valid"] is True
    assert d["影子有无"] is False


def test_封印入口_核证_影子只读_AND_正式不变(客户):
    _铺三日(客户)
    原快照 = 客户.get("/api/快照", params={"营业日": "2026-11-22"}).json()

    r = 客户.post("/api/封印", json={"营业日": "2026-11-22", "原因": "定版"})
    assert r.status_code == 200
    指纹 = r.json()["正式指纹"]

    assert 客户.post("/api/装载夹具", json={"名": "封印后迟到样例.json"}).status_code == 200
    抽 = 客户.post("/api/抽取", json={"营业日": "2026-11-22"}).json()
    assert 抽["封印"] is True and 抽["盖写"] == 0 and 抽["写入"] == 0

    核 = 客户.get("/api/封印核证", params={"营业日": "2026-11-22"}).json()
    assert 核["正式指纹"] == 指纹
    assert 核["valid"] is True
    assert 核["影子有无"] is True

    assert 客户.get("/api/快照", params={"营业日": "2026-11-22"}).json() == 原快照
    影子 = 客户.get("/api/影子", params={"营业日": "2026-11-22"}).json()
    assert len(影子) == 3
    assert all(x["来源"] == "封印后再抽" for x in 影子)


def test_迟到补抽接口_封印后无票400_持票不改正式(客户):
    _铺三日(客户)
    客户.post("/api/封印", json={"营业日": "2026-11-22"})
    原快照 = 客户.get("/api/快照", params={"营业日": "2026-11-22"}).json()
    r = 客户.post(
        "/api/迟到补抽",
        json={
            "营业日": "2026-11-22",
            "流水": [
                {"流水号": "补-1", "账户键": "户甲", "营业日": "2026-11-22", "变动额": 250, "摘要": "迟到"}
            ],
        },
    )
    assert r.status_code == 400, "封印日无窗票迟到补抽两端皆拒"
    assert 客户.get("/api/窗票/纠偏簿", params={"营业日": "2026-11-22"}).json() == []

    w = 客户.post(
        "/api/窗票/开窗",
        json={"营业日": "2026-11-22", "窗止": "2099-01-01T00:00:00Z", "票号": "票-api-1"},
    )
    assert w.status_code == 200 and w.json()["窗是否有效"] is True
    r2 = 客户.post(
        "/api/迟到补抽",
        json={
            "营业日": "2026-11-22",
            "票号": "票-api-1",
            "流水": [
                {"流水号": "补-2", "账户键": "户甲", "营业日": "2026-11-22", "变动额": 250, "摘要": "迟到"}
            ],
        },
    )
    assert r2.status_code == 200
    assert r2.json()["抽取"]["封印"] is True
    assert 客户.get("/api/快照", params={"营业日": "2026-11-22"}).json() == 原快照
    核 = 客户.get("/api/封印核证", params={"营业日": "2026-11-22"}).json()
    assert 核["valid"] is True and 核["纠偏簿有无"] is True
    簿 = 客户.get("/api/窗票/纠偏簿", params={"票号": "票-api-1"}).json()
    甲行 = next(r for r in 簿 if r["账户键"] == "户甲")
    assert len(簿) == 3 and 甲行["纠偏余额"] == 甲行["正式余额"] + 250


def test_无原因解封_400(客户):
    _铺三日(客户)
    客户.post("/api/封印", json={"营业日": "2026-11-22"})
    r = 客户.post("/api/解封", json={"营业日": "2026-11-22", "原因": ""})
    assert r.status_code == 400


def test_空白营业日封印_400(客户):
    r = 客户.post("/api/封印", json={"营业日": "2031-03-03"})
    assert r.status_code == 400
