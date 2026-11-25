import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function 周期快照() {
  const [日, set日] = useState("");
  const [行, set行] = useState([]);
  const [核, set核] = useState(null);
  const [讯, set讯] = useState("");

  const 刷新 = async () => {
    const q = 日 ? `?营业日=${encodeURIComponent(日)}` : "";
    set行(await api.快照(q));
    if (日.trim()) {
      set核(await api.封印核证(日));
    } else {
      set核(null);
    }
  };

  useEffect(() => {
    刷新().catch((e) => set讯(String(e.message || e)));
  }, []);

  return (
    <div>
      <h1 className="题">周期快照</h1>
      <p className="述">每个账户每个营业日一行有效余额镜；封印日的正式镜冻结于封印指纹，再抽只落影子（本页不显示影子）。</p>
      <div className="行">
        <input value={日} onChange={(e) => set日(e.target.value)} placeholder="筛选营业日，可空" />
        <button className="次" onClick={() => 刷新().catch((e) => set讯(String(e.message || e)))}>刷新</button>
      </div>
      {讯 ? <p className="讯">{讯}</p> : null}
      {核 ? (
        <div className="提示条">
          {核.已封印 ? (
            <>
              <span className="徽章 通">在封</span> 正式指纹 {String(核.正式指纹).slice(0, 16)}…
              {核.valid ? <span className="徽章 通">valid</span> : <span className="徽章 败">指纹漂移</span>}
              影子：{核.影子有无 ? `有（${核.影子行数} 行，见快照封印页）` : "无"}
            </>
          ) : (
            <>
              <span className="徽章 败">未封印</span> 当前指纹 {String(核.当前指纹).slice(0, 16)}…
              {核.状态 === "已解封" ? "（已解封，可重抽正式镜）" : ""}
            </>
          )}
        </div>
      ) : null}
      {!行.length ? (
        <div className="空态">暂无快照</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>账户键</th>
              <th>营业日</th>
              <th>余额</th>
              <th>抽取批次</th>
              <th>来源</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {行.map((r) => (
              <tr key={r.快照键}>
                <td>{r.账户键}</td>
                <td>{r.营业日}</td>
                <td>{r.余额}</td>
                <td>{r.抽取批次编号}</td>
                <td>{r.来源}</td>
                <td>{r.状态}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
