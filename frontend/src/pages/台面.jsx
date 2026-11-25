import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

export default function 台面() {
  const [总览, set总览] = useState(null);
  const [讯, set讯] = useState("");
  const [忙, set忙] = useState(false);

  const 刷新 = async () => {
    set总览(await api.总览());
  };

  useEffect(() => {
    刷新().catch((e) => set讯(String(e.message || e)));
  }, []);

  const 冒烟 = async () => {
    set忙(true);
    set讯("");
    try {
      await api.重置();
      await api.装载夹具("三日连环样例.json");
      const a = await api.抽取("2026-11-20");
      const b = await api.抽取("2026-11-21");
      const c = await api.抽取("2026-11-22");
      const r = await api.回放("2026-11-22");
      await 刷新();
      set讯(
        `冒烟完成：抽取 ${a.写入 + a.盖写}/${b.写入 + b.盖写}/${c.写入 + c.盖写}；回放通过=${r.通过} 差额=${r.差额}`
      );
    } catch (e) {
      set讯(String(e.message || e));
    } finally {
      set忙(false);
    }
  };

  const 封印冒烟 = async () => {
    set忙(true);
    set讯("");
    try {
      await api.重置();
      await api.装载夹具("三日连环样例.json");
      await api.抽取("2026-11-20");
      await api.抽取("2026-11-21");
      await api.抽取("2026-11-22");
      const 封 = await api.封印("2026-11-22", "冒烟封印");
      await api.装载夹具("封印后迟到样例.json");
      const 再抽 = await api.抽取("2026-11-22");
      const 核 = await api.封印核证("2026-11-22");
      刷新();
      set讯(
        `封印冒烟：封印指纹未变=${核.正式指纹 === 封.正式指纹} valid=${核.valid}；` +
          `再抽正式拒改=${再抽.封印拒改} 影子=${再抽.影子写入 + 再抽.影子覆盖} 盖写=${再抽.盖写}`
      );
    } catch (e) {
      set讯(String(e.message || e));
    } finally {
      set忙(false);
    }
  };

  const o = 总览 || {};
  return (
    <div>
      <h1 className="题">台面</h1>
      <p className="述">先装流水，再按营业日做日终抽取写周期快照，最后回放核对看差额清单是否清空。</p>
      <div className="提示条">
        最短路径：点「一键冒烟」→ 打开 <Link to="/周期快照">周期快照</Link> 与 <Link to="/差额清单">差额清单</Link>。
      </div>
      <div className="阶条">
        <div className="阶"><div className="序">账户</div><b>{o.账户数 ?? "—"}</b><span>册内户数</span></div>
        <div className="阶"><div className="序">流水</div><b>{o.流水数 ?? "—"}</b><span>已入账</span></div>
        <div className="阶"><div className="序">快照</div><b>{o.快照数 ?? "—"}</b><span>有效行</span></div>
        <div className="阶"><div className="序">差额</div><b>{o.差额行数 ?? "—"}</b><span>清单行</span></div>
        <div className="阶"><div className="序">旁置</div><b>{o.旁置数 ?? "—"}</b><span>未入账</span></div>
      </div>
      <div className="行">
        <button disabled={忙} onClick={冒烟}>{忙 ? "跑着…" : "一键冒烟"}</button>
        <button className="水" disabled={忙} onClick={封印冒烟}>封印后再抽冒烟</button>
        <button className="次" onClick={() => 刷新().catch((e) => set讯(String(e.message || e)))}>刷新总览</button>
        <button
          className="次"
          onClick={() =>
            api.重置().then(刷新).then(() => set讯("已清空业务表")).catch((e) => set讯(String(e.message || e)))
          }
        >
          清空业务表
        </button>
      </div>
      {讯 ? <p className="讯">{讯}</p> : null}
    </div>
  );
}
