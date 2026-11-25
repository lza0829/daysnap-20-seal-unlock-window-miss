import json
import uuid
from typing import Any

from app.db import 连接
from app.services.时间 import 此刻, 标准化营业日
from app.services import 封印


def _前日(营业日: str) -> str:
    y, m, d = map(int, 营业日.split("-"))
    from datetime import date, timedelta

    return (date(y, m, d) - timedelta(days=1)).isoformat()


def 回放核对(营业日: str, 批次编号: str = "") -> dict[str, Any]:
    """用前日快照+当日流水重算，对照当日周期快照，写入差额/跳变。"""
    日 = 标准化营业日(营业日)
    批 = 批次编号.strip() or f"回放-{日}-{uuid.uuid4().hex[:8]}"
    conn = 连接()
    try:
        封 = 封印.在封(conn, 日)
        影子 = {
            r["账户键"]: int(r["余额"])
            for r in conn.execute(
                "SELECT 账户键, 余额 FROM 影子快照 WHERE 营业日=? AND 状态='在影'", (日,)
            )
        }
        参 = {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 台参")}
        try:
            阈值 = int(参.get("跳变阈值分", "0") or "0")
        except ValueError:
            阈值 = 0
        账户们 = [dict(r) for r in conn.execute("SELECT * FROM 账户 WHERE 状态='正常'")]
        相符 = 0
        差额数 = 0
        跳变数 = 0
        无快照 = 0
        for 户 in 账户们:
            账户键 = 户["账户键"]
            if 日 < 户["开户营业日"]:
                continue
            快照 = conn.execute(
                "SELECT 余额 FROM 周期快照 WHERE 账户键=? AND 营业日=? AND 状态='有效'",
                (账户键, 日),
            ).fetchone()
            if not 快照:
                无快照 += 1
                conn.execute(
                    "INSERT INTO 差额行(回放批次编号, 账户键, 营业日, 快照余额, 回放余额, 差额, 原因, 时刻) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (批, 账户键, 日, None, None, 0, "缺当日快照", 此刻()),
                )
                差额数 += 1
                continue
            前 = _前日(日)
            前日快照 = conn.execute(
                "SELECT 余额 FROM 周期快照 WHERE 账户键=? AND 营业日=? AND 状态='有效'",
                (账户键, 前),
            ).fetchone()
            开端 = 0 if 前日快照 is None else int(前日快照["余额"])
            净额 = int(
                conn.execute(
                    "SELECT COALESCE(SUM(变动额),0) AS s FROM 变动流水 "
                    "WHERE 账户键=? AND 营业日=? AND 命运='已入账'",
                    (账户键, 日),
                ).fetchone()["s"]
            )
            回放余额 = 开端 + 净额
            快照余额 = int(快照["余额"])
            差额 = 快照余额 - 回放余额
            if 差额 == 0:
                相符 += 1
            else:
                原因 = "快照与回放不一致"
                if 封 is not None:
                    原因 = "封印后偏离（正式镜不动，见影子）"
                    conn.execute(
                        "INSERT INTO 旁置簿(原因, 账户键, 营业日, 载荷, 时刻) VALUES (?,?,?,?,?)",
                        (
                            "封印后回放偏离",
                            账户键,
                            日,
                            json.dumps(
                                {"快照余额": 快照余额, "回放余额": 回放余额, "影子余额": 影子.get(账户键)},
                                ensure_ascii=False,
                            ),
                            此刻(),
                        ),
                    )
                conn.execute(
                    "INSERT INTO 差额行(回放批次编号, 账户键, 营业日, 快照余额, 回放余额, 差额, 原因, 时刻) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (批, 账户键, 日, 快照余额, 回放余额, 差额, 原因, 此刻()),
                )
                差额数 += 1
            偏离 = abs(快照余额 - (开端 + 净额))
            if 阈值 > 0 and 偏离 >= 阈值:
                conn.execute(
                    "INSERT INTO 跳变记录(账户键, 营业日, 前日余额, 当日余额, 流水净额, 偏离, 检出批次编号, 时刻) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (账户键, 日, 开端, 快照余额, 净额, 偏离, 批, 此刻()),
                )
                跳变数 += 1
        通过 = 差额数 == 0 and 无快照 == 0
        核 = 封印.核证述(conn, 日)
        窗票行 = [
            dict(r)
            for r in conn.execute(
                "SELECT 票号, 状态, 窗起, 窗止, 封印指纹 FROM 解封窗票表 WHERE 营业日=? ORDER BY 票号",
                (日,),
            )
        ]
        待发布 = [
            dict(r)
            for r in conn.execute(
                "SELECT 票号, 账户键, 正式余额, 纠偏余额, 差额 FROM 纠偏簿 "
                "WHERE 营业日=? AND 状态='待发布' ORDER BY 票号, 账户键",
                (日,),
            )
        ]
        报告 = {
            "营业日": 日,
            "相符": 相符,
            "差额": 差额数,
            "跳变": 跳变数,
            "无快照": 无快照,
            "通过": 通过,
            "已封印": 封 is not None,
            "正式指纹": 核["正式指纹"],
            "指纹有效": 核["valid"],
            "影子行数": len(影子),
            "窗票数": len(窗票行),
            "窗票": 窗票行,
            "待发布纠偏": 待发布,
            "待发布纠偏行数": len(待发布),
        }
        conn.execute(
            "INSERT INTO 回放批次(编号, 营业日, 时刻, 报告) VALUES (?,?,?,?)",
            (批, 日, 此刻(), json.dumps(报告, ensure_ascii=False)),
        )
        conn.commit()
        return {"批次编号": 批, **报告}
    finally:
        conn.close()

