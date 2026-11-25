import os
import sys
import tempfile
from pathlib import Path

import pytest


_临时 = tempfile.mkdtemp(prefix="daysnap-封印-")
os.environ["数据目录"] = _临时
os.environ["夹具目录"] = str(Path(__file__).resolve().parents[2] / "fixtures")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import seed  
from app.db import 连接  


@pytest.fixture(autouse=True)
def 干净库():
    seed.初始化库()
    conn = 连接()
    try:
        for t in (
            "变动流水",
            "抽取批次",
            "周期快照",
            "回放批次",
            "差额行",
            "断档记录",
            "跳变记录",
            "旁置簿",
            "装载批次",
            "封印",
            "影子快照",
        ):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    finally:
        conn.close()
    yield
