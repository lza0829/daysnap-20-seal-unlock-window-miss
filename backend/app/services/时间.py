from datetime import datetime, timedelta, timezone

# 测试/夹具用时钟偏移（秒）。生产恒为 0；仅经 拨钟/复位钟 改动。
_时钟偏移秒 = 0.0


def 此刻() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=_时钟偏移秒)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def 拨钟(iso: str) -> str:
    """把当前时钟拨到指定 ISO 时刻（按 UTC 解释），返回标准化后的时刻串。"""
    global _时钟偏移秒
    t = _解析时刻(iso)
    _时钟偏移秒 = (t - datetime.now(timezone.utc)).total_seconds()
    return 此刻()


def 复位钟() -> None:
    global _时钟偏移秒
    _时钟偏移秒 = 0.0


def _解析时刻(值: str) -> datetime:
    s = (值 or "").strip().replace("Z", "").replace(" ", "T")
    if len(s) >= 19:
        s = s[:19]
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError as e:
        raise ValueError(f"时刻格式须为 YYYY-MM-DDTHH:MM:SSZ：{值}") from e


def 标准化时刻(值: str) -> str:
    return _解析时刻(值).strftime("%Y-%m-%dT%H:%M:%SZ")


def 标准化营业日(值: str) -> str:
    值 = (值 or "").strip()
    if len(值) >= 10:
        return 值[:10]
    raise ValueError("营业日格式须为 YYYY-MM-DD")
