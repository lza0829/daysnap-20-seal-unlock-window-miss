import json
import uuid
from typing import Any

from app.db import 连接
from app.services.时间 import 此刻, 标准化营业日
from app.services import 封印
from app.modules import 解封窗票 as 窗票


def _台参(conn) -> dict[str, str]:
    return {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 台参")}


def _前日(营业日: str) -> str:
    y, m, d = map(int, 营业日.split("-"))
    from datetime import date, timedelta

    return (date(y, m, d) - timedelta(days=1)).isoformat()


def 日终抽取(营业日: str, 批次编号: str = "", 票号: str = "") -> dict[str, Any]:
    """按营业日为全部正常账户写周期快照。余额=前日快照(或开户零)+当日流水净额。

    封印写闸（口径乙，全局唯一）：
    - 营业日在封时，正式有效镜永冻，任何抽取都不写正式行。
    - 持**有效窗票**且账户在允许范围内：只写「纠偏簿（待发布）」，须另办发布解封才并正式。
    - 无票 / 过期票 / 超范围：正式与纠偏簿皆拒（无票再抽仍落影子轨留痕），失败闭。
    """
    日 = 标准化营业日(营业日)
    批 = 批次编号.strip() or f"抽取-{日}-{uuid.uuid4().hex[:8]}"
    号 = (票号 or "").strip()
    conn = 连接()
    已关 = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        参 = _台参(conn)
        重复 = 参.get("重复抽取", "盖写同日快照")
        缺前日 = 参.get("缺前日策略", "以零为开端")
        封 = 封印.在封(conn, 日)
        # 持票抽取：写锁内先验票，票坏整批失败闭（不落任何影子/纠偏/旁置半吊子行）。
        票判 = None
        if 封 is not None and 号:
            票判 = 窗票.窗是否有效(conn, 号, 日)
            if not 票判["窗有效"]:
                拒因 = 票判["原因"]
                conn.rollback()
                conn.close()
                已关 = True
                # 审计走独立连接，保证拒改留痕不随主事务回滚。
                窗票.记审计(号, 日, "", "日终抽取拒改正式", "拒绝", 拒因, 批)
                raise ValueError(f"窗票 {号} 不可用：{拒因}")
        账户们 = [
            dict(r)
            for r in conn.execute("SELECT * FROM 账户 WHERE 状态='正常' ORDER BY 账户键")
        ]
        写入 = 0
        盖写 = 0
        旁置 = 0
        断档数 = 0
        影子写入 = 0
        影子覆盖 = 0
        封印拒改 = 0
        纠偏写入 = 0
        纠偏覆盖 = 0
        范围 = 窗票._范围解析(票判["票"]["允许账户"]) if 票判 else []
        if 封 is not None and not 号:
            # 无票整批留一条拒改审计（同票号为空，与封印/审计可对账）。
            窗票._审计(conn, "", 日, "", "日终抽取拒改正式", "拒绝",
                       "封印日无窗票：正式镜与纠偏簿皆拒，仅落影子", 批)
        for 户 in 账户们:
            账户键 = 户["账户键"]
            开户日 = 户["开户营业日"]
            if 日 < 开户日:
                continue
            前 = _前日(日)
            前日快照 = conn.execute(
                "SELECT 余额 FROM 周期快照 WHERE 账户键=? AND 营业日=? AND 状态='有效'",
                (账户键, 前),
            ).fetchone()
            if 前日快照 is None:
                if 日 == 开户日 or 缺前日 == "以零为开端":
                    开端 = 0
                elif 封 is None:
                    conn.execute(
                        "INSERT INTO 断档记录(账户键, 缺营业日, 检出批次编号, 处置, 时刻) VALUES (?,?,?,?,?)",
                        (账户键, 前, 批, "记断档并继续", 此刻()),
                    )
                    断档数 += 1
                    开端 = 0
                else:
                    开端 = 0
            else:
                开端 = int(前日快照["余额"])
            净额行 = conn.execute(
                "SELECT COALESCE(SUM(变动额),0) AS s FROM 变动流水 "
                "WHERE 账户键=? AND 营业日=? AND 命运='已入账'",
                (账户键, 日),
            ).fetchone()
            净额 = int(净额行["s"])
            余额 = 开端 + 净额
            快照键 = f"{账户键}|{日}"
            旧 = conn.execute(
                "SELECT 快照键, 余额 FROM 周期快照 WHERE 账户键=? AND 营业日=?",
                (账户键, 日),
            ).fetchone()
            if 封 is not None:
                持票且在范围 = 票判 is not None and (not 范围 or 账户键 in 范围)
                if 持票且在范围:
                    if 旧 is None:
                        # 封印日无正式行：窗票也不得凭空新增，失败闭。
                        conn.execute(
                            "INSERT INTO 旁置簿(原因, 账户键, 营业日, 载荷, 时刻) VALUES (?,?,?,?,?)",
                            (
                                f"封印日无正式行，窗票 {号} 亦拒绝新增",
                                账户键,
                                日,
                                json.dumps({"余额": 余额, "批次": 批}, ensure_ascii=False),
                                此刻(),
                            ),
                        )
                        窗票._审计(conn, 号, 日, 账户键, "写纠偏簿", "拒绝",
                                   "封印日无正式行，不得新增", 批)
                        旁置 += 1
                        封印拒改 += 1
                        continue
                    果 = 窗票.写纠偏(conn, 票判["票"], 账户键, 日, 旧["余额"], 余额, 批)
                    if 果 == "覆盖":
                        纠偏覆盖 += 1
                    else:
                        纠偏写入 += 1
                    封印拒改 += 1
                    continue
                # 无票 / 持票但账户超范围：正式与纠偏皆拒，超范围留审计。
                if 票判 is not None:
                    窗票._审计(conn, 号, 日, 账户键, "写纠偏簿", "拒绝",
                               "账户超出窗票允许改写范围", 批)
                if 旧 is None:
                    封印拒改 += 1
                    conn.execute(
                        "INSERT INTO 旁置簿(原因, 账户键, 营业日, 载荷, 时刻) VALUES (?,?,?,?,?)",
                        (
                            "封印日无正式行，拒绝新增",
                            账户键,
                            日,
                            json.dumps({"余额": 余额, "批次": 批}, ensure_ascii=False),
                            此刻(),
                        ),
                    )
                    旁置 += 1
                    continue
                果 = 封印.写影子(conn, 账户键, 日, 余额, 批, 旧["余额"],
                               来源="窗票超范围再抽" if 票判 is not None else "封印后再抽")
                if 果 == "覆盖":
                    影子覆盖 += 1
                else:
                    影子写入 += 1
                封印拒改 += 1
                continue
            if 旧:
                if 重复 != "盖写同日快照":
                    conn.execute(
                        "INSERT INTO 旁置簿(原因, 账户键, 营业日, 载荷, 时刻) VALUES (?,?,?,?,?)",
                        (
                            "同日已有快照",
                            账户键,
                            日,
                            json.dumps({"余额": 余额}, ensure_ascii=False),
                            此刻(),
                        ),
                    )
                    旁置 += 1
                    continue
                conn.execute(
                    "UPDATE 周期快照 SET 余额=?, 抽取批次编号=?, 来源='日终抽取', 状态='有效' "
                    "WHERE 账户键=? AND 营业日=?",
                    (余额, 批, 账户键, 日),
                )
                盖写 += 1
            else:
                conn.execute(
                    "INSERT INTO 周期快照(快照键, 账户键, 营业日, 余额, 抽取批次编号, 来源, 状态) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (快照键, 账户键, 日, 余额, 批, "日终抽取", "有效"),
                )
                写入 += 1
        报告 = {
            "营业日": 日,
            "写入": 写入,
            "盖写": 盖写,
            "旁置": 旁置,
            "断档": 断档数,
            "账户扫描": len(账户们),
            "封印": 封 is not None,
            "票号": 号,
            "窗有效": bool(票判 and 票判["窗有效"]),
            "封印拒改": 封印拒改,
            "影子写入": 影子写入,
            "影子覆盖": 影子覆盖,
            "纠偏写入": 纠偏写入,
            "纠偏覆盖": 纠偏覆盖,
        }
        conn.execute(
            "INSERT INTO 抽取批次(编号, 营业日, 时刻, 报告) VALUES (?,?,?,?)",
            (批, 日, 此刻(), json.dumps(报告, ensure_ascii=False)),
        )
        conn.commit()
        return {"批次编号": 批, **报告}
    except Exception:
        if not 已关:
            conn.rollback()
        raise
    finally:
        if not 已关:
            conn.close()
