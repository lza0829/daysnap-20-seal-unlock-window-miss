"""快照封印写闸 · 影子轨 夹具。

覆盖：
1. 抽后封印，再抽 → 正式指纹不变；影子可读；主读 /快照 不含影子。
2. 封印后迟到补抽 → 不得改正式镜，只落影子。
3. 封印与抽取并发 → 正式镜不得被盖写，最终指纹等于封印指纹。
4. 封印日无正式行 → 拒绝新增正式行。
5. 解封须原因（无手续解封失败），解封后方可再抽正式。
6. 回放报告带封印指纹与 valid。
"""

import json
import threading
from pathlib import Path

import pytest

from app.db import 连接
from app.services import 回放, 抽取, 封印

夹具 = Path(__file__).resolve().parents[2] / "fixtures"


def _装夹具(名: str, 批: str = "") -> dict:
    data = json.loads((夹具 / 名).read_text(encoding="utf-8"))
    from app.services.装载 import 装载流水

    return 装载流水(data["流水"], 批 or data.get("批次编号") or name_batch(名))


def name_batch(名: str) -> str:
    return 名.replace(".json", "")


def _准备三日() -> None:
    _装夹具("三日连环样例.json")
    for 日 in ("2026-11-20", "2026-11-21", "2026-11-22"):
        抽取.日终抽取(日)
    回放.回放核对("2026-11-22")


def _正式指纹(日: str) -> str:
    return 封印.核证(日)["正式指纹"]


def _正式行(日: str) -> list[dict]:
    conn = 连接()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT 账户键, 余额, 抽取批次编号 FROM 周期快照 "
                "WHERE 营业日=? AND 状态='有效' ORDER BY 账户键",
                (日,),
            )
        ]
    finally:
        conn.close()


def _总快照行(日: str) -> int:
    conn = 连接()
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM 周期快照 WHERE 营业日=?", (日,)
            ).fetchone()[0]
        )
    finally:
        conn.close()





def test_封印后重抽_正式指纹不变_影子可读_主读不含影子():
    _准备三日()
    日 = "2026-11-22"
    封 = 封印.封印当日(日, 原因="日终定版")
    assert 封["已封印"] is True
    原指纹 = _正式指纹(日)
    原正式 = _正式行(日)
    原总行 = _总快照行(日)

    
    _装夹具("封印后迟到样例.json", "夹具-封印后迟到-装载")
    果 = 抽取.日终抽取(日, "重抽-封印后")

    
    assert _正式指纹(日) == 原指纹
    assert _正式行(日) == 原正式
    assert _总快照行(日) == 原总行, "封印日不得新增正式行"
    assert 果["封印"] is True
    assert 果["影子写入"] + 果["影子覆盖"] > 0
    assert 果["盖写"] == 0 and 果["写入"] == 0

    核 = 封印.核证(日)
    assert 核["已封印"] is True
    assert 核["影子有无"] is True
    assert 核["valid"] is True

    影子 = 封印.列影子(日)
    assert 影子, "封印后重抽应产生影子行"
    
    assert all(r["来源"] == "封印后再抽" for r in 影子)
    
    conn = 连接()
    try:
        主读 = conn.execute(
            "SELECT COUNT(*) FROM 周期快照 WHERE 营业日=? AND 状态='有效'", (日,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert int(主读) == len(原正式)


def test_封印后重抽_影子余额反映迟到流水_与正式差额可区分():
    _准备三日()
    日 = "2026-11-22"
    封印.封印当日(日)
    _装夹具("封印后迟到样例.json", "夹具-封印后迟到-装载")
    抽取.日终抽取(日)

    影子 = {r["账户键"]: r for r in 封印.列影子(日)}
    assert "户甲" in 影子
    
    assert 影子["户甲"]["正式余额"] == 9000
    assert 影子["户甲"]["余额"] == 9700
    assert 影子["户甲"]["差额"] == 700





def test_封印后迟到补抽_无票两端皆拒_持票只落纠偏簿():
    """口径乙：封印日迟到补抽无窗票 → 正式镜与纠偏簿皆拒；
    持有效窗票 → 正式镜仍不动，纠偏簿可读（见 test_解封窗票 全套）。"""
    from app.modules import 解封窗票 as 窗票

    _准备三日()
    日 = "2026-11-22"
    封印.封印当日(日)
    原指纹 = _正式指纹(日)
    原正式 = _正式行(日)

    data = json.loads((夹具 / "封印后迟到样例.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        封印.迟到补抽(日, data["流水"], "迟到-无票")
    # 失败闭：流水未装载、正式未动、纠偏簿为空、审计留痕
    assert _正式指纹(日) == 原指纹
    assert _正式行(日) == 原正式
    assert 窗票.列纠偏(日) == []
    assert 窗票.列审计(营业日=日)[0]["结果"] == "拒绝"

    票 = 窗票.开窗(日, 窗止="2099-01-01T00:00:00Z", 票号="票-迟到-1", 原因="迟到补入")
    assert 票["窗是否有效"] is True
    果 = 封印.迟到补抽(日, data["流水"], "迟到-持票", "票-迟到-1")
    assert 果["抽取"]["封印"] is True
    assert 果["抽取"]["票号"] == "票-迟到-1"
    assert 果["抽取"]["纠偏写入"] >= 1
    assert 果["抽取"]["盖写"] == 0 and 果["抽取"]["写入"] == 0
    assert _正式指纹(日) == 原指纹, "口径乙：窗票不得直改正式"
    assert _正式行(日) == 原正式
    簿 = 窗票.列纠偏(日, "票-迟到-1")
    assert 簿 and all(r["状态"] == "待发布" for r in 簿), "纠偏簿须可读且待发布"


def test_迟到补抽流水营业日不符被拒():
    with pytest.raises(ValueError):
        封印.迟到补抽("2026-11-22", [{"流水号": "x", "账户键": "户甲", "营业日": "2026-11-21", "变动额": 1}])





def test_封印与抽取并发_正式不得被盖写():
    """并发多线程：一半线程封印、一半线程重抽；无论交错如何，
    最终正式指纹必须等于某一次封印落下的指纹；且核证 valid。"""
    _准备三日()
    日 = "2026-11-22"
    结果: list = []
    错误: list = []
    闸 = threading.Barrier(8)

    def 抽() -> None:
        try:
            闸.wait()
            结果.append(抽取.日终抽取(日, f"并发抽-{threading.get_ident()}"))
        except Exception as e:  
            错误.append(e)

    def 封() -> None:
        try:
            闸.wait()
            结果.append(封印.封印当日(日, 原因="并发封印"))
        except Exception as e:  
            错误.append(e)

    
    基准 = 封印.封印当日(日, 原因="基准封印")
    基准指纹 = 基准["正式指纹"]

    threads = [threading.Thread(target=封) for _ in range(4)] + [
        threading.Thread(target=抽) for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not 错误, f"并发过程不应报错: {错误}"
    核 = 封印.核证(日)
    assert 核["已封印"] is True
    assert 核["正式指纹"] == 基准指纹, "并发封印/抽取不得改写封印指纹"
    assert 核["valid"] is True, "正式镜不得被盖写"
    assert 核["当前指纹"] == 基准指纹


def test_首次封印与重抽并发_无基准封印():
    """更硬的交错：开始时封印尚未落，封印线程与重抽线程同时冲入。
    允许封印先行（之后抽取只能落影子）或抽取先完成（随后封印则指纹取新值）；
    但不允许出现「封印时刻已写、正式镜随后仍被覆盖」——最终 valid 必须为真，
    且正式有效行必须与封印可核证指纹一致。"""
    _准备三日()
    日 = "2026-11-22"
    错误: list = []
    闸 = threading.Barrier(6)

    def 抽() -> None:
        try:
            闸.wait()
            抽取.日终抽取(日, f"首封并发抽-{threading.get_ident()}")
        except Exception as e:  
            错误.append(e)

    def 封() -> None:
        try:
            闸.wait()
            封印.封印当日(日, 原因="首封并发")
        except Exception as e:  
            错误.append(e)

    threads = [threading.Thread(target=封) for _ in range(3)] + [
        threading.Thread(target=抽) for _ in range(3)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not 错误, f"并发过程不应报错: {错误}"
    核 = 封印.核证(日)
    assert 核["已封印"] is True
    assert 核["valid"] is True, "封印已成后正式镜不得再被盖写"
    assert 核["当前指纹"] == 核["正式指纹"]





def test_封印日无正式行_拒绝新增正式行():
    _装夹具("三日连环样例.json")
    for 日 in ("2026-11-20", "2026-11-21"):
        抽取.日终抽取(日)
    
    with pytest.raises(ValueError):
        封印.封印当日("2026-11-22")


def test_空白日不能封印():
    with pytest.raises(ValueError):
        封印.封印当日("2030-01-01")





def test_无原因解封被拒():
    _准备三日()
    封印.封印当日("2026-11-22")
    with pytest.raises(ValueError):
        封印.解封当日("2026-11-22", "  ")


def test_解封后方可再抽正式():
    _准备三日()
    日 = "2026-11-22"
    封印.封印当日(日)
    原指纹 = _正式指纹(日)
    封印.解封当日(日, 原因="差错更正")
    核 = 封印.核证(日)
    assert 核["已封印"] is False
    assert 核["状态"] == "已解封"

    _装夹具("封印后迟到样例.json", "夹具-解封后装载")
    果 = 抽取.日终抽取(日, "解封后重抽")
    assert 果["封印"] is False
    assert 果["盖写"] == 3, "解封后三户均重抽盖写正式镜"
    assert 果["影子写入"] + 果["影子覆盖"] == 0
    assert 封印.核证(日)["当前指纹"] != 原指纹, "解封后重抽允许改正式镜"





def test_解封后影子作废_不混入正式也不可读():
    _准备三日()
    日 = "2026-11-22"
    封印.封印当日(日)
    _装夹具("封印后迟到样例.json", "夹具-解封前装载")
    抽取.日终抽取(日)  
    assert 封印.核证(日)["影子有无"] is True

    封印.解封当日(日, 原因="差错更正")
    assert 封印.核证(日)["影子有无"] is False
    assert 封印.列影子(日) == [], "解封后影子作废，默认不可读"
    assert len(封印.列影子(日, 含作废=True)) == 3, "留痕可审计"


def test_回放报告带封印指纹与valid():
    _准备三日()
    日 = "2026-11-22"
    封印.封印当日(日)
    印 = 封印.核证(日)
    _装夹具("封印后迟到样例.json", "夹具-回放后装载")
    抽取.日终抽取(日)  
    果 = 回放.回放核对(日)
    assert 果["已封印"] is True
    assert 果["正式指纹"] == 印["正式指纹"]
    assert 果["指纹有效"] is True
    assert 果["影子行数"] >= 1
