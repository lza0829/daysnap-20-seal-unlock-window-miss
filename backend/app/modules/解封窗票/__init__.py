"""解封窗票 · 口径乙（全局唯一口径）。

- 封印后正式有效镜（周期快照.状态='有效'）永冻；持未过期窗票也**不得直改正式**，
  只能把纠偏值写入「纠偏簿」（状态='待发布'），纠偏簿只读可查。
- 须另办「发布解封」手续（POST /api/窗票/发布，必填原因、留痕），才在同一写锁内
  把待发布纠偏并入正式镜、重算并更新封印指纹、票转「已发布」。
- 无票 / 过期票 / 超范围票：纠偏簿与正式镜两端皆拒（失败闭，写审计）。
- 票号贯穿：窗票、封印标记、正式指纹、迟到补抽、日终抽取、纠偏簿、回放、审计同票。
"""

import uuid
from typing import Any

from app.db import 连接
from app.services.时间 import 此刻, 标准化营业日, 标准化时刻
from app.services import 封印

状态 = "已落地"
口径 = "乙：窗票只开待发布纠偏簿，正式指纹永冻；须另办发布解封才并入正式"


# ---------- 基础 ----------

def 表名() -> str:
    return "解封窗票表"


def _票号() -> str:
    return f"窗-{标准化营业日(此刻())}-{uuid.uuid4().hex[:8]}"


def _范围解析(允许账户) -> list[str]:
    if not 允许账户:
        return []
    if isinstance(允许账户, str):
        return [x.strip() for x in 允许账户.split(",") if x.strip()]
    return [str(x).strip() for x in 允许账户 if str(x).strip()]


def 取票(conn, 票号: str):
    if not 票号:
        return None
    return conn.execute("SELECT * FROM 解封窗票表 WHERE 票号=?", (票号.strip(),)).fetchone()


def _审计(conn, 票号: str, 营业日: str, 账户键: str, 动作: str, 结果: str,
          细节: str = "", 批次编号: str = "") -> None:
    conn.execute(
        "INSERT INTO 窗票改写审计(时刻, 票号, 营业日, 账户键, 动作, 结果, 细节, 批次编号) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (此刻(), 票号 or "", 标准化营业日(营业日), 账户键 or "", 动作, 结果, 细节, 批次编号 or ""),
    )


def 记审计(票号: str, 营业日: str, 账户键: str, 动作: str, 结果: str,
           细节: str = "", 批次编号: str = "") -> None:
    """被拒路径用：短连接独立落审计，不随主事务回滚。"""
    conn = 连接()
    try:
        _审计(conn, 票号, 营业日, 账户键, 动作, 结果, 细节, 批次编号)
        conn.commit()
    finally:
        conn.close()


# ---------- 开窗 ----------

def 开窗(营业日: str, 窗止: str, 窗起: str = "", 允许账户=None, 允许来源: str = "",
         票号: str = "", 原因: str = "", 操作人: str = "") -> dict[str, Any]:
    """同票开窗票：营业日、窗起止、允许改写范围、票号。仅在封且指纹未漂的营业日可开。"""
    日 = 标准化营业日(营业日)
    起 = 标准化时刻(窗起 or 此刻())
    止 = 标准化时刻(窗止)
    if not (起 < 止):
        raise ValueError("窗起止非法：须 窗起 < 窗止")
    范围 = _范围解析(允许账户)
    conn = 连接()
    try:
        conn.execute("BEGIN IMMEDIATE")
        封 = 封印.在封(conn, 日)
        if 封 is None:
            raise ValueError(f"{日} 未在封，不能开解封窗票")
        当前指纹, 行数 = 封印.计算指纹(conn, 日)
        if 当前指纹 != 封["正式指纹"]:
            raise ValueError(f"{日} 正式镜指纹已漂，拒绝开窗票")
        号 = (票号 or "").strip() or _票号()
        if 取票(conn, 号) is not None:
            raise ValueError(f"票号重复：{号}")
        conn.execute(
            "INSERT INTO 解封窗票表(票号, 营业日, 窗起, 窗止, 允许账户, 允许来源, 开窗时刻, "
            "封印指纹, 状态, 操作人, 原因) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (号, 日, 起, 止, ",".join(范围), (允许来源 or "").strip(), 此刻(),
             封["正式指纹"], "在窗", (操作人 or "").strip(), (原因 or "").strip()),
        )
        _审计(conn, 号, 日, "", "开窗", "通过",
              f"窗 {起}~{止} 范围={','.join(范围) or '全日全部账户'}")
        conn.commit()
        return 票述(conn, 号)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- 窗有效性判定（写闸核心，须在持写事务的连接上调用） ----------

def 窗是否有效(conn, 票号: str = "", 营业日: str = "", 账户键: str = "",
              来源: str = "") -> dict[str, Any]:
    日 = 标准化营业日(营业日) if 营业日 else ""
    票 = 取票(conn, 票号)
    if not 票号:
        return {"窗有效": False, "原因": "无窗票", "票": None}
    if 票 is None:
        return {"窗有效": False, "原因": "窗票不存在", "票": None}
    if 日 and 票["营业日"] != 日:
        return {"窗有效": False, "原因": f"窗票营业日 {票['营业日']} 与 {日} 不符", "票": dict(票)}
    if 票["状态"] != "在窗":
        return {"窗有效": False, "原因": f"窗票已{票['状态']}", "票": dict(票)}
    now = 此刻()
    if now < 票["窗起"]:
        return {"窗有效": False, "原因": "窗未到起时", "票": dict(票)}
    if now > 票["窗止"]:
        return {"窗有效": False, "原因": "窗票已过期", "票": dict(票)}
    封 = 封印.在封(conn, 票["营业日"])
    if 封 is None:
        return {"窗有效": False, "原因": "营业日已不在封", "票": dict(票)}
    if 封["正式指纹"] != 票["封印指纹"]:
        return {"窗有效": False, "原因": "封印指纹与票载指纹不符", "票": dict(票)}
    if 账户键:
        范围 = _范围解析(票["允许账户"])
        if 范围 and 账户键 not in 范围:
            return {"窗有效": False, "原因": f"账户 {账户键} 超出窗票允许改写范围", "票": dict(票)}
    if 来源 and 票["允许来源"] and 来源 not in _范围解析(票["允许来源"]):
        return {"窗有效": False, "原因": f"来源 {来源} 超出窗票允许范围", "票": dict(票)}
    return {"窗有效": True, "原因": "", "票": dict(票)}


def 迟到可否改正式(conn, 营业日: str) -> bool:
    """口径乙：任何窗票都不允许直改正式，恒为 False。"""
    return False


def 过期窗仍放行(conn, 营业日: str) -> bool:
    """过期窗永不放行，恒为 False。"""
    return False


# ---------- 纠偏簿 ----------

def 写纠偏(conn, 票: dict, 账户键: str, 营业日: str, 正式余额: int,
           纠偏余额: int, 批次: str) -> str:
    """持有效窗票把纠偏值落待发布纠偏簿（正式镜不动）。同票同户覆盖，返回 写入/覆盖。"""
    日 = 标准化营业日(营业日)
    键 = f"{票['票号']}|{账户键}|{日}"
    旧 = conn.execute(
        "SELECT 纠偏键 FROM 纠偏簿 WHERE 票号=? AND 账户键=? AND 营业日=?",
        (票["票号"], 账户键, 日),
    ).fetchone()
    if 旧:
        conn.execute(
            "UPDATE 纠偏簿 SET 正式余额=?, 纠偏余额=?, 差额=?, 批次编号=?, 写入时刻=?, 状态='待发布' "
            "WHERE 票号=? AND 账户键=? AND 营业日=?",
            (int(正式余额), int(纠偏余额), int(纠偏余额) - int(正式余额), 批次, 此刻(),
             票["票号"], 账户键, 日),
        )
        果 = "覆盖"
    else:
        conn.execute(
            "INSERT INTO 纠偏簿(纠偏键, 票号, 账户键, 营业日, 正式余额, 纠偏余额, 差额, "
            "批次编号, 写入时刻, 状态) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (键, 票["票号"], 账户键, 日, int(正式余额), int(纠偏余额),
             int(纠偏余额) - int(正式余额), 批次, 此刻(), "待发布"),
        )
        果 = "写入"
    _审计(conn, 票["票号"], 日, 账户键, "写纠偏簿", "通过",
          f"正式 {正式余额} → 纠偏 {纠偏余额}", 批次)
    return 果


def 列纠偏(营业日: str = "", 票号: str = "", 含发布: bool = True) -> list[dict]:
    conn = 连接()
    try:
        sql = "SELECT * FROM 纠偏簿 WHERE 1=1"
        args: list = []
        if not 含发布:
            sql += " AND 状态='待发布'"
        if 营业日:
            sql += " AND 营业日=?"
            args.append(标准化营业日(营业日))
        if 票号:
            sql += " AND 票号=?"
            args.append(票号.strip())
        sql += " ORDER BY 营业日 DESC, 票号, 账户键 LIMIT 300"
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def 列审计(票号: str = "", 营业日: str = "") -> list[dict]:
    conn = 连接()
    try:
        sql = "SELECT * FROM 窗票改写审计 WHERE 1=1"
        args: list = []
        if 票号:
            sql += " AND 票号=?"
            args.append(票号.strip())
        if 营业日:
            sql += " AND 营业日=?"
            args.append(标准化营业日(营业日))
        sql += " ORDER BY 编号 DESC LIMIT 200"
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


# ---------- 作废（解封手续联动） ----------

def 作废日内窗票(conn, 营业日: str, 原因: str) -> int:
    """在调用方持有的写事务内：把该日全部在窗票作废，其待发布纠偏一并作废。返回作废票数。"""
    日 = 标准化营业日(营业日)
    票们 = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM 解封窗票表 WHERE 营业日=? AND 状态='在窗'", (日,)
        )
    ]
    for 票 in 票们:
        conn.execute(
            "UPDATE 解封窗票表 SET 状态='已作废', 作废时刻=?, 作废原因=? WHERE 票号=?",
            (此刻(), 原因, 票["票号"]),
        )
        conn.execute(
            "UPDATE 纠偏簿 SET 状态='已作废' WHERE 票号=? AND 状态='待发布'", (票["票号"],)
        )
        _审计(conn, 票["票号"], 日, "", "窗票作废", "通过", 原因)
    return len(票们)


# ---------- 发布解封（口径乙的唯一并正式路径） ----------

def 发布(票号: str, 原因: str, 操作人: str = "") -> dict[str, Any]:
    """持票办发布解封：待发布纠偏在同一写锁内并入正式镜，封印指纹随之重算。"""
    号 = (票号 or "").strip()
    if not 号:
        raise ValueError("发布解封须提供票号")
    if not (原因 or "").strip():
        raise ValueError("发布解封须填写原因，禁止无手续发布")
    conn = 连接()
    try:
        conn.execute("BEGIN IMMEDIATE")
        票 = 取票(conn, 号)
        if 票 is None:
            raise ValueError(f"窗票不存在：{号}")
        if 票["状态"] != "在窗":
            raise ValueError(f"窗票状态为 {票['状态']}，不能发布")
        日 = 票["营业日"]
        封 = 封印.在封(conn, 日)
        if 封 is None:
            raise ValueError(f"{日} 已不在封，发布前提消失")
        if 封["正式指纹"] != 票["封印指纹"]:
            raise ValueError("正式镜指纹与票载封印指纹不符，拒绝发布")
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM 纠偏簿 WHERE 票号=? AND 状态='待发布' ORDER BY 账户键", (号,)
            )
        ]
        if not rows:
            raise ValueError("纠偏簿无待发布行，无物可发布")
        批 = f"窗票发布-{日}-{uuid.uuid4().hex[:8]}"
        并入 = 0
        for r in rows:
            正式 = conn.execute(
                "SELECT 快照键 FROM 周期快照 WHERE 账户键=? AND 营业日=? AND 状态='有效'",
                (r["账户键"], 日),
            ).fetchone()
            if 正式 is None:
                raise ValueError(f"正式镜缺 {r['账户键']}@{日} 有效行，失败闭：整票回滚")
            conn.execute(
                "UPDATE 周期快照 SET 余额=?, 抽取批次编号=?, 来源='窗票发布', 状态='有效' "
                "WHERE 账户键=? AND 营业日=?",
                (int(r["纠偏余额"]), 批, r["账户键"], 日),
            )
            并入 += 1
        新指纹, 行数 = 封印.计算指纹(conn, 日)
        conn.execute(
            "UPDATE 封印 SET 正式指纹=?, 快照行数=? WHERE 营业日=?", (新指纹, 行数, 日)
        )
        conn.execute(
            "UPDATE 纠偏簿 SET 状态='已发布' WHERE 票号=? AND 状态='待发布'", (号,)
        )
        conn.execute(
            "UPDATE 解封窗票表 SET 状态='已发布', 发布时刻=?, 发布批次=? WHERE 票号=?",
            (此刻(), 批, 号),
        )
        _审计(conn, 号, 日, "", "发布解封", "通过",
              f"并入 {并入} 行；新指纹 {新指纹[:12]}…；原因：{原因.strip()}", 批)
        conn.commit()
        return {
            "票号": 号,
            "营业日": 日,
            "已发布": True,
            "并入行数": 并入,
            "发布批次": 批,
            "原封印指纹": 票["封印指纹"],
            "新正式指纹": 新指纹,
            "操作人": (操作人 or "").strip(),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------- 只读核证 ----------

def 票述(conn, 票号: str) -> dict[str, Any]:
    票 = 取票(conn, 票号)
    if 票 is None:
        raise ValueError(f"窗票不存在：{票号}")
    d = dict(票)
    日 = 票["营业日"]
    判 = 窗是否有效(conn, 票号, 日)
    当前指纹, 行数 = 封印.计算指纹(conn, 日)
    纠偏 = conn.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(CASE WHEN 状态='待发布' THEN 1 ELSE 0 END),0) AS p "
        "FROM 纠偏簿 WHERE 票号=?",
        (票号,),
    ).fetchone()
    总数, 待发 = int(纠偏["c"]), int(纠偏["p"])
    封 = 封印.在封(conn, 日)
    d.update(
        {
            "窗是否有效": 判["窗有效"],
            "窗失效原因": 判["原因"],
            "正式指纹": 票["封印指纹"],
            "当前指纹": 当前指纹,
            "封印在封": 封 is not None,
            "纠偏簿有无": 总数 > 0,
            "纠偏簿行数": 总数,
            "待发布行数": 待发,
            "允许账户列表": _范围解析(票["允许账户"]),
            "valid": 判["窗有效"] and 封 is not None and 当前指纹 == 票["封印指纹"],
        }
    )
    return d


def 核证(票号: str = "", 营业日: str = "") -> dict[str, Any] | list[dict]:
    """解封窗票核证只读接口：票号、窗是否有效、正式指纹、纠偏簿有无、valid。"""
    conn = 连接()
    try:
        if (票号 or "").strip():
            return 票述(conn, 票号.strip())
        sql = "SELECT 票号 FROM 解封窗票表 WHERE 1=1"
        args: list = []
        if 营业日:
            sql += " AND 营业日=?"
            args.append(标准化营业日(营业日))
        sql += " ORDER BY 开窗时刻 DESC, 票号 DESC LIMIT 100"
        return [票述(conn, r["票号"]) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def 查现场(conn, 键: str | None = None, 营业日: str = "") -> dict[str, Any]:
    """路由适配：单票给核证述，无键给该日/全部票的核证列表。"""
    if (键 or "").strip():
        return 票述(conn, 键.strip())
    sql = "SELECT 票号 FROM 解封窗票表 WHERE 1=1"
    args: list = []
    if 营业日:
        sql += " AND 营业日=?"
        args.append(标准化营业日(营业日))
    sql += " ORDER BY 开窗时刻 DESC, 票号 DESC LIMIT 100"
    票们 = [票述(conn, r["票号"]) for r in conn.execute(sql, args)]
    return {
        "口径": 口径,
        "解封窗": 票们,
        "票数": len(票们),
        "有效窗数": sum(1 for t in 票们 if t["窗是否有效"]),
        "纠偏簿强制": True,
        "valid": all(t["valid"] for t in 票们) if 票们 else True,
    }


def 巡检包(payload: dict | None = None) -> dict[str, Any]:
    payload = payload or {}
    日 = str(payload.get("营业日") or "")
    conn = 连接()
    try:
        现场 = 查现场(conn, None, 日)
        过期 = [
            dict(r)
            for r in conn.execute(
                "SELECT 票号, 营业日, 窗止, 状态 FROM 解封窗票表 WHERE 状态='在窗' AND 窗止<?",
                (此刻(),),
            )
        ]
        现场.update(
            {
                "kind": "unlock-window",
                "口径": 口径,
                "formal_mutable": False,
                "过期在窗票数": len(过期),
                "巡检时刻": 此刻(),
            }
        )
        return 现场
    finally:
        conn.close()
