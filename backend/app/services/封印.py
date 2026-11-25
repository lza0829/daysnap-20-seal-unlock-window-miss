"""快照封印 / 影子轨。

口径（全局唯一）：
- 封印成功后，正式有效快照（周期快照.状态='有效'）不得再被任何抽取/迟到补抽改动。
- 封印日再抽、迟到补抽只写「影子快照」（非有效），影子仅经 /api/影子 只读接口可见。
- 对外主读仍是正式有效镜；影子永不自动升正式。
- 只有显式「解封手续」（带原因、留痕）解除封印后，才可能重新抽取写正式镜。
"""

import hashlib
import uuid
from typing import Any

from app.db import 连接
from app.services.时间 import 此刻, 标准化营业日


def 计算指纹(conn, 营业日: str) -> tuple[str, int]:
    """正式有效镜指纹：按账户键排序的「账户=余额」行做 SHA-256。"""
    rows = conn.execute(
        "SELECT 账户键, 余额 FROM 周期快照 WHERE 营业日=? AND 状态='有效' ORDER BY 账户键",
        (营业日,),
    ).fetchall()
    h = hashlib.sha256()
    for r in rows:
        h.update(f"{r['账户键']}={int(r['余额'])}\n".encode("utf-8"))
    return h.hexdigest(), len(rows)


def 在封(conn, 营业日: str):
    return conn.execute(
        "SELECT * FROM 封印 WHERE 营业日=? AND 状态='在封'", (营业日,)
    ).fetchone()


def 封印当日(营业日: str, 原因: str = "", 操作人: str = "") -> dict[str, Any]:
    """对某营业日正式有效镜落封印。重复封印同指纹视为幂等。"""
    日 = 标准化营业日(营业日)
    conn = 连接()
    try:
        conn.execute("BEGIN IMMEDIATE")
        指纹, 行数 = 计算指纹(conn, 日)
        if 行数 == 0:
            raise ValueError(f"{日} 无有效快照，不能封印")
        旧 = conn.execute("SELECT * FROM 封印 WHERE 营业日=?", (日,)).fetchone()
        if 旧 is not None and 旧["状态"] == "在封":
            if 旧["正式指纹"] != 指纹:
                raise ValueError(f"{日} 已封印，但正式有效镜指纹已变，拒绝重封")
            conn.commit()
            return {
                "营业日": 日,
                "已封印": True,
                "重复": True,
                "正式指纹": 指纹,
                "快照行数": 行数,
                "封印时刻": 旧["封印时刻"],
            }
        if 旧 is None:
            conn.execute(
                "INSERT INTO 封印(营业日, 正式指纹, 快照行数, 封印时刻, 封印原因, 操作人, 状态) "
                "VALUES (?,?,?,?,?,?,?)",
                (日, 指纹, 行数, 此刻(), 原因.strip(), 操作人.strip(), "在封"),
            )
        else:
            conn.execute(
                "UPDATE 封印 SET 正式指纹=?, 快照行数=?, 封印时刻=?, 封印原因=?, 操作人=?, "
                "状态='在封', 解封时刻='', 解封原因='' WHERE 营业日=?",
                (指纹, 行数, 此刻(), 原因.strip(), 操作人.strip(), 日),
            )
        conn.commit()
        return {
            "营业日": 日,
            "已封印": True,
            "重复": False,
            "正式指纹": 指纹,
            "快照行数": 行数,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 解封当日(营业日: str, 原因: str, 操作人: str = "") -> dict[str, Any]:
    """显式解封手续：必须填写原因并留痕。解封不是影子升正式。

    同事务联动：该日在窗窗票一律作废、其待发布纠偏一并作废（口径乙：无票/失票不得再并正式）。
    """
    from app.modules import 解封窗票 as 窗票

    日 = 标准化营业日(营业日)
    if not (原因 or "").strip():
        raise ValueError("解封须填写原因，禁止无手续解封")
    conn = 连接()
    try:
        conn.execute("BEGIN IMMEDIATE")
        旧 = 在封(conn, 日)
        if 旧 is None:
            raise ValueError(f"{日} 当前未封印")
        作废旧票数 = 窗票.作废日内窗票(conn, 日, f"随解封手续作废：{原因.strip()}")
        conn.execute(
            "UPDATE 封印 SET 状态='已解封', 解封时刻=?, 解封原因=? WHERE 营业日=?",
            (此刻(), 原因.strip(), 日),
        )

        conn.execute(
            "UPDATE 影子快照 SET 状态='已作废' WHERE 营业日=? AND 状态='在影'", (日,)
        )
        conn.commit()
        return {
            "营业日": 日,
            "已解封": True,
            "正式指纹": 旧["正式指纹"],
            "作废旧票数": 作废旧票数,
            "操作人": 操作人.strip(),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def 核证述(conn, 营业日: str) -> dict[str, Any]:
    """在既有连接上做核证（供已持写事务的调用方复用，避免另开连接）。"""
    日 = 标准化营业日(营业日)
    印 = conn.execute("SELECT * FROM 封印 WHERE 营业日=?", (日,)).fetchone()
    当前指纹, 行数 = 计算指纹(conn, 日)
    影子数 = int(
        conn.execute(
            "SELECT COUNT(*) FROM 影子快照 WHERE 营业日=? AND 状态='在影'", (日,)
        ).fetchone()[0]
    )
    状态 = "未封印" if 印 is None else 印["状态"]
    已封印 = 状态 == "在封"
    正式指纹 = "" if 印 is None else 印["正式指纹"]
    valid = (正式指纹 == 当前指纹) if 已封印 else True
    窗票数 = int(
        conn.execute(
            "SELECT COUNT(*) FROM 解封窗票表 WHERE 营业日=?", (日,)
        ).fetchone()[0]
    )
    有效窗数 = int(
        conn.execute(
            "SELECT COUNT(*) FROM 解封窗票表 WHERE 营业日=? AND 状态='在窗' AND 窗起<=? AND 窗止>=?",
            (日, 此刻(), 此刻()),
        ).fetchone()[0]
    )
    待发布数 = int(
        conn.execute(
            "SELECT COUNT(*) FROM 纠偏簿 WHERE 营业日=? AND 状态='待发布'", (日,)
        ).fetchone()[0]
    )
    return {
        "营业日": 日,
        "已封印": 已封印,
        "状态": 状态,
        "正式指纹": 正式指纹,
        "当前指纹": 当前指纹,
        "快照行数": 行数,
        "影子有无": 影子数 > 0,
        "影子行数": 影子数,
        "窗票数": 窗票数,
        "有效窗数": 有效窗数,
        "纠偏簿有无": 待发布数 > 0,
        "待发布纠偏行数": 待发布数,
        "valid": valid,
        "封印时刻": "" if 印 is None else 印["封印时刻"],
        "封印原因": "" if 印 is None else 印["封印原因"],
        "解封时刻": "" if 印 is None else 印["解封时刻"],
        "解封原因": "" if 印 is None else 印["解封原因"],
    }


def 核证(营业日: str) -> dict[str, Any]:
    """只读核证：营业日、正式指纹、影子有无、valid。

    valid 口径：营业日在封时 = 当前正式镜指纹与封印指纹一致（未被盖写）；
    未封印（含已解封）时恒为 True —— 没有封印可失效。
    """
    conn = 连接()
    try:
        return 核证述(conn, 营业日)
    finally:
        conn.close()


def 列封印(营业日: str = "") -> list[dict]:
    conn = 连接()
    try:
        if 营业日:
            rows = conn.execute(
                "SELECT * FROM 封印 WHERE 营业日=? ORDER BY 营业日 DESC",
                (标准化营业日(营业日),),
            )
        else:
            rows = conn.execute("SELECT * FROM 封印 ORDER BY 营业日 DESC LIMIT 200")
        return [dict(r) for r in rows]
    finally:
        conn.close()


def 列影子(营业日: str = "", 账户键: str = "", 含作废: bool = False) -> list[dict]:
    """影子只读出口：主读接口（/快照）永远看不到影子行。"""
    conn = 连接()
    try:
        sql = "SELECT * FROM 影子快照 WHERE 1=1"
        args: list = []
        if not 含作废:
            sql += " AND 状态='在影'"
        if 营业日:
            sql += " AND 营业日=?"
            args.append(标准化营业日(营业日))
        if 账户键:
            sql += " AND 账户键=?"
            args.append(账户键)
        sql += " ORDER BY 营业日 DESC, 账户键 LIMIT 300"
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


def 写影子(conn, 账户键: str, 营业日: str, 余额: int, 批次: str, 正式余额, 来源: str = "封印后再抽") -> str:
    """封印日再抽落影子。返回 '写入' / '覆盖'。影子永远不升正式。"""
    键 = f"{账户键}|{营业日}"
    差额 = None if 正式余额 is None else int(余额) - int(正式余额)
    旧 = conn.execute("SELECT 快照键 FROM 影子快照 WHERE 账户键=? AND 营业日=?", (账户键, 营业日)).fetchone()
    if 旧:
        conn.execute(
            "UPDATE 影子快照 SET 余额=?, 抽取批次编号=?, 来源=?, 正式余额=?, 差额=?, 生成时刻=?, 状态='在影' "
            "WHERE 账户键=? AND 营业日=?",
            (int(余额), 批次, 来源, 正式余额, 差额, 此刻(), 账户键, 营业日),
        )
        return "覆盖"
    conn.execute(
        "INSERT INTO 影子快照(快照键, 账户键, 营业日, 余额, 抽取批次编号, 来源, 正式余额, 差额, 生成时刻, 状态) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (键, 账户键, 营业日, int(余额), 批次, 来源, 正式余额, 差额, 此刻(), "在影"),
    )
    return "写入"


def 迟到补抽(营业日: str, 流水: list[dict[str, Any]], 批次编号: str = "",
             票号: str = "") -> dict[str, Any]:
    """迟到流水补抽：先装载流水，再按营业日抽取（抽取内过封印/窗票写闸）。

    口径乙硬闸（在装载之前先判，失败闭不污染流水）：
    - 营业日在封时必须持有效窗票；无票 / 过期 / 超范围一律拒绝，正式镜与纠偏簿皆不动。
    - 装载这一步只写「变动流水」与「装载批次」，不动快照；真正写闸由日终抽取在写锁内复核。
    """
    from app.modules import 解封窗票 as 窗票
    from app.services.抽取 import 日终抽取
    from app.services.装载 import 装载流水

    日 = 标准化营业日(营业日)
    if not 流水:
        raise ValueError("迟到补抽流水为空")
    for 条 in 流水:
        流日 = 标准化营业日(str(条.get("营业日") or ""))
        if 流日 != 日:
            raise ValueError(f"迟到补抽流水的营业日须为 {日}，实际 {流日}")
    号 = (票号 or "").strip()
    conn = 连接()
    已关 = False
    try:
        封 = 在封(conn, 日)
        if 封 is not None:
            if not 号:
                conn.close()
                已关 = True
                窗票.记审计("", 日, "", "迟到补抽拒改正式", "拒绝",
                            "封印日迟到补抽无窗票：正式镜与纠偏簿皆拒", 批次编号)
                raise ValueError(f"{日} 在封，迟到补抽须持有效解封窗票（无票两端皆拒）")
            判 = 窗票.窗是否有效(conn, 号, 日)
            if not 判["窗有效"]:
                原因 = 判["原因"]
                conn.close()
                已关 = True
                窗票.记审计(号, 日, "", "迟到补抽拒改正式", "拒绝", 原因, 批次编号)
                raise ValueError(f"窗票 {号} 不可用：{原因}")
    finally:
        if not 已关:
            conn.close()
    批 = 批次编号.strip() or f"迟到补抽-{日}-{uuid.uuid4().hex[:8]}"
    装 = 装载流水(流水, 批)
    抽 = 日终抽取(日, 批, 号)
    return {"批次编号": 批, "票号": 号, "装载": 装, "抽取": 抽}
