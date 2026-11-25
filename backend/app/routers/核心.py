import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import 夹具目录, 连接
from app.services import 回放, 抽取, 封印, 目录, 装载
from app.services import 时间
from app.modules import 解封窗票 as 窗票

路由 = APIRouter(prefix="/api")


class 装载请求(BaseModel):
    批次编号: str = ""
    流水: list = Field(default_factory=list)


class 营业日请求(BaseModel):
    营业日: str
    批次编号: str = ""
    票号: str = ""


class 封印请求(BaseModel):
    营业日: str
    原因: str = ""
    操作人: str = ""


class 解封请求(BaseModel):
    营业日: str
    原因: str
    操作人: str = ""


class 迟到补抽请求(BaseModel):
    营业日: str
    批次编号: str = ""
    票号: str = ""
    流水: list = Field(default_factory=list)


class 开窗请求(BaseModel):
    营业日: str
    窗止: str
    窗起: str = ""
    允许账户: list[str] = Field(default_factory=list)
    允许来源: str = ""
    票号: str = ""
    原因: str = ""
    操作人: str = ""


class 发布请求(BaseModel):
    票号: str
    原因: str
    操作人: str = ""


@路由.get("/健康")
def 健康():
    return {
        "正常": True,
        "项目": "日镜账",
        "骨架": "日终余额抽取→周期快照落行→变动流水回放核对→断档跳变检出→快照与回放差额清单",
    }


@路由.get("/总览")
def 取总览():
    return 目录.总览()


@路由.get("/台参")
def 取台参():
    conn = 连接()
    try:
        return {r["键"]: r["值"] for r in conn.execute("SELECT 键, 值 FROM 台参")}
    finally:
        conn.close()


@路由.get("/账户")
def 列账户():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 账户 ORDER BY 账户键")]
    finally:
        conn.close()


@路由.get("/流水")
def 列流水(营业日: str = "", 账户键: str = ""):
    conn = 连接()
    try:
        sql = "SELECT * FROM 变动流水 WHERE 1=1"
        args: list = []
        if 营业日:
            sql += " AND 营业日=?"
            args.append(营业日)
        if 账户键:
            sql += " AND 账户键=?"
            args.append(账户键)
        sql += " ORDER BY 营业日 DESC, 发生时 DESC LIMIT 300"
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


@路由.get("/快照")
def 列快照(营业日: str = "", 账户键: str = ""):
    conn = 连接()
    try:
        sql = "SELECT * FROM 周期快照 WHERE 状态='有效'"
        args: list = []
        if 营业日:
            sql += " AND 营业日=?"
            args.append(营业日)
        if 账户键:
            sql += " AND 账户键=?"
            args.append(账户键)
        sql += " ORDER BY 营业日 DESC, 账户键 LIMIT 300"
        return [dict(r) for r in conn.execute(sql, args)]
    finally:
        conn.close()


@路由.get("/差额")
def 列差额(回放批次编号: str = ""):
    conn = 连接()
    try:
        if 回放批次编号:
            rows = conn.execute(
                "SELECT * FROM 差额行 WHERE 回放批次编号=? ORDER BY 编号 DESC",
                (回放批次编号,),
            )
        else:
            rows = conn.execute("SELECT * FROM 差额行 ORDER BY 编号 DESC LIMIT 200")
        return [dict(r) for r in rows]
    finally:
        conn.close()


@路由.get("/断档")
def 列断档():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 断档记录 ORDER BY 编号 DESC LIMIT 200")]
    finally:
        conn.close()


@路由.get("/跳变")
def 列跳变():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 跳变记录 ORDER BY 编号 DESC LIMIT 200")]
    finally:
        conn.close()


@路由.get("/旁置")
def 列旁置():
    conn = 连接()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM 旁置簿 ORDER BY 编号 DESC LIMIT 100")]
    finally:
        conn.close()


def _列批(表: str):
    conn = 连接()
    try:
        out = []
        for r in conn.execute(f"SELECT * FROM {表} ORDER BY 时刻 DESC LIMIT 40"):
            d = dict(r)
            try:
                d["报告"] = json.loads(d.get("报告") or "{}")
            except Exception:
                pass
            out.append(d)
        return out
    finally:
        conn.close()


@路由.get("/装载批次")
def 列装载批():
    return _列批("装载批次")


@路由.get("/抽取批次")
def 列抽取批():
    return _列批("抽取批次")


@路由.get("/回放批次")
def 列回放批():
    return _列批("回放批次")


@路由.get("/夹具")
def 列夹具():
    if not 夹具目录.exists():
        return []
    return sorted(p.name for p in 夹具目录.glob("*.json"))


@路由.post("/装载")
def 执行装载(体: 装载请求):
    try:
        return 装载.装载流水(体.流水, 体.批次编号)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class 夹具请求(BaseModel):
    名: str


@路由.post("/装载夹具/{名}")
def 装载夹具路径(名: str):
    return _装载夹具文件(名)


@路由.post("/装载夹具")
def 装载夹具体(体: 夹具请求):
    return _装载夹具文件(体.名)


def _装载夹具文件(名: str):
    path = 夹具目录 / 名
    if not path.exists():
        raise HTTPException(404, f"夹具不存在: {名}")
    data = json.loads(path.read_text(encoding="utf-8"))
    流水 = data.get("流水") or data.get("事件") or []
    return 装载.装载流水(流水, str(data.get("批次编号") or ""))


@路由.post("/抽取")
def 执行抽取(体: 营业日请求):
    try:
        return 抽取.日终抽取(体.营业日, 体.批次编号, 体.票号)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/回放")
def 执行回放(体: 营业日请求):
    try:
        return 回放.回放核对(体.营业日, 体.批次编号)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/封印")
def 执行封印(体: 封印请求):
    try:
        return 封印.封印当日(体.营业日, 体.原因, 体.操作人)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/解封")
def 执行解封(体: 解封请求):
    try:
        return 封印.解封当日(体.营业日, 体.原因, 体.操作人)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.get("/封印")
def 列封印(营业日: str = ""):
    try:
        return 封印.列封印(营业日)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.get("/封印核证")
def 取封印核证(营业日: str):
    """封印/影子只读核证：营业日、正式指纹、影子有无、valid。"""
    try:
        return 封印.核证(营业日)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.get("/影子")
def 列影子(营业日: str = "", 账户键: str = "", 含作废: bool = False):
    """影子只读出口；影子永不升正式，对外主读仍是 /快照。"""
    try:
        return 封印.列影子(营业日, 账户键, 含作废)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/迟到补抽")
def 执行迟到补抽(体: 迟到补抽请求):
    try:
        return 封印.迟到补抽(体.营业日, 体.流水, 体.批次编号, 体.票号)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/窗票/开窗")
def 执行开窗(体: 开窗请求):
    """解封入口①：同票开窗票（营业日、窗起止、允许改写范围、票号）。"""
    try:
        return 窗票.开窗(
            体.营业日, 体.窗止, 体.窗起, 体.允许账户, 体.允许来源,
            体.票号, 体.原因, 体.操作人,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/窗票/发布")
def 执行窗票发布(体: 发布请求):
    """解封入口②：发布解封——待发布纠偏并入正式镜，封印指纹随之重算（口径乙唯一并正式路径）。"""
    try:
        return 窗票.发布(体.票号, 体.原因, 体.操作人)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.get("/窗票/核证")
def 取窗票核证(票号: str = "", 营业日: str = ""):
    """解封窗票核证只读接口：票号、窗是否有效、正式指纹、纠偏簿有无、valid。"""
    try:
        return 窗票.核证(票号, 营业日)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.get("/窗票/纠偏簿")
def 取纠偏簿(营业日: str = "", 票号: str = "", 含发布: bool = True):
    """纠偏簿只读出口：正式主读 /快照 永远不含纠偏值。"""
    try:
        return 窗票.列纠偏(营业日, 票号, 含发布)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.get("/窗票/审计")
def 取窗票审计(票号: str = "", 营业日: str = ""):
    try:
        return 窗票.列审计(票号, 营业日)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/时钟/拨")
def 拨钟(payload: dict):
    """夹具用：把时钟拨到指定 ISO 时刻（过期窗测试）。"""
    try:
        return {"当前时刻": 时间.拨钟(str(payload.get("时刻") or ""))}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@路由.post("/时钟/复位")
def 复位钟():
    时间.复位钟()
    return {"当前时刻": 时间.此刻()}


@路由.post("/重置业务库")
def 重置():
    """开发冒烟用：清业务表并保留账户与台参。"""
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
            "窗票改写审计",
            "纠偏簿",
            "解封窗票表",
        ):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
        return {"完成": True, **目录.总览()}
    finally:
        conn.close()


# 基线兼容别名：/核证/解封窗票 即窗票核证只读接口。
@路由.get("/核证/解封窗票")
def 取核证_别名(键: str | None = None, 营业日: str = ""):
    conn = 连接()
    try:
        return 窗票.查现场(conn, 键, 营业日)
    finally:
        conn.close()


@路由.post("/核证/解封窗票/巡检")
def 巡检核证(payload: dict | None = None):
    return 窗票.巡检包(payload or {})

