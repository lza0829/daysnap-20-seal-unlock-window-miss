import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function 日终抽取() {
  const [日, set日] = useState("2026-11-20");
  const [票号, set票号] = useState("");
  const [批, set批] = useState([]);
  const [讯, set讯] = useState("");

  const 刷新 = () => api.抽取批次().then(set批);

  useEffect(() => {
    刷新().catch((e) => set讯(String(e.message || e)));
  }, []);

  return (
    <div>
      <h1 className="题">日终抽取</h1>
      <p className="述">
        按营业日写周期快照：前日余额 + 当日流水净额。封印日正式镜永冻：无票只落影子，
        持有效窗票只写待发布纠偏簿（口径乙），坏票整批失败闭。
      </p>
      <div className="行">
        <input value={日} onChange={(e) => set日(e.target.value)} placeholder="YYYY-MM-DD" />
        <input value={票号} onChange={(e) => set票号(e.target.value)} placeholder="窗票票号（封印日可选；空=无票走影子轨）" />
        <button
          onClick={() =>
            api
              .抽取(日, 票号.trim())
              .then((r) =>
                set讯(
                  `批次 ${r.批次编号} 写入=${r.写入} 盖写=${r.盖写} 断档=${r.断档}` +
                    (r.封印
                      ? `｜已封印：正式拒改=${r.封印拒改} 影子=${r.影子写入 + r.影子覆盖}` +
                        ` 纠偏=${r.纠偏写入 + r.纠偏覆盖}${r.票号 ? `（票 ${r.票号}）` : ""}`
                      : "")
                )
              )
              .then(刷新)
              .catch((e) => set讯(String(e.message || e)))
          }
        >
          执行抽取
        </button>
        <button className="次" onClick={() => 刷新().catch((e) => set讯(String(e.message || e)))}>刷新批次</button>
      </div>
      {讯 ? <p className="讯">{讯}</p> : null}
      <div className="段">
        <h2 className="段题">抽取批次</h2>
        {!批.length ? (
          <div className="空态">尚无抽取</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>编号</th>
                <th>营业日</th>
                <th>时刻</th>
                <th>报告</th>
              </tr>
            </thead>
            <tbody>
              {批.map((r) => (
                <tr key={r.编号}>
                  <td>{r.编号}</td>
                  <td>{r.营业日}</td>
                  <td>{r.时刻}</td>
                  <td>{typeof r.报告 === "object" ? JSON.stringify(r.报告) : r.报告}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
