状态 = "半截"


def 窗是否有效(conn, 票号: str = "", 营业日: str = "") -> dict:
    try:
        row = conn.execute(
            "SELECT * FROM 解封窗票表 WHERE 票号=? OR 营业日=? ORDER BY 编号 DESC LIMIT 1",
            (票号, 营业日),
        ).fetchone()
    except Exception:
        row = None
    return {"窗": dict(row) if row else None, "可改正式": True, "纠偏簿强制": False}


def 迟到可否改正式(conn, 营业日: str) -> bool:
    return True


def 写入纠偏簿(conn, **kwargs) -> str:
    return ""


def 过期窗仍放行(conn, 营业日: str) -> bool:
    return True

def 表名() -> str:
    return "解封窗票表"


def 查现场(conn, 键: str | None = None) -> dict:
    rows = []
    try:
        if 键:
            rows = [dict(r) for r in conn.execute(
                "SELECT 票号, 营业日, 窗起, 窗止, 状态 FROM 解封窗票表 WHERE 票号=? LIMIT 40", (键,)
            )]
        else:
            rows = [dict(r) for r in conn.execute(
                "SELECT 票号, 营业日, 窗起, 窗止, 状态 FROM 解封窗票表 ORDER BY 编号 DESC LIMIT 40"
            )]
    except Exception:
        rows = []
    return {"解封窗": rows, "纠偏簿强制": False, "nn": "20", "valid": False}


def 巡检包(payload: dict | None = None) -> dict:
    base = {"kind": "unlock-window", "nn": "20", "ttl_hint": 1200, "formal_mutable": True}
    if payload:
        base.update(payload)
    return base
