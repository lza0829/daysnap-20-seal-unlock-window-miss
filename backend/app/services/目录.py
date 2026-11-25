from app.db import 连接


def 总览() -> dict:
    conn = 连接()
    try:
        def 数(sql: str) -> int:
            return int(conn.execute(sql).fetchone()[0])

        return {
            "账户数": 数("SELECT COUNT(*) FROM 账户"),
            "流水数": 数("SELECT COUNT(*) FROM 变动流水 WHERE 命运='已入账'"),
            "快照数": 数("SELECT COUNT(*) FROM 周期快照 WHERE 状态='有效'"),
            "差额行数": 数("SELECT COUNT(*) FROM 差额行"),
            "断档数": 数("SELECT COUNT(*) FROM 断档记录"),
            "跳变数": 数("SELECT COUNT(*) FROM 跳变记录"),
            "旁置数": 数("SELECT COUNT(*) FROM 旁置簿"),
            "抽取批次数": 数("SELECT COUNT(*) FROM 抽取批次"),
            "回放批次数": 数("SELECT COUNT(*) FROM 回放批次"),
            "封印数": 数("SELECT COUNT(*) FROM 封印 WHERE 状态='在封'"),
            "影子数": 数("SELECT COUNT(*) FROM 影子快照 WHERE 状态='在影'"),
            "窗票数": 数("SELECT COUNT(*) FROM 解封窗票表"),
            "在窗票数": 数("SELECT COUNT(*) FROM 解封窗票表 WHERE 状态='在窗'"),
            "待发布纠偏数": 数("SELECT COUNT(*) FROM 纠偏簿 WHERE 状态='待发布'"),
            "窗票审计数": 数("SELECT COUNT(*) FROM 窗票改写审计"),
        }
    finally:
        conn.close()

