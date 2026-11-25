import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function 封印() {
  const [日, set日] = useState("2026-11-22");
  const [原因, set原因] = useState("");
  const [票号, set票号] = useState("");
  const [核, set核] = useState(null);
  const [影子, set影子] = useState([]);
  const [封印行, set封印行] = useState([]);
  const [讯, set讯] = useState("");
  const [忙, set忙] = useState(false);

  const 刷新 = async () => {
    if (!日.trim()) return;
    const [k, s, f] = await Promise.all([api.封印核证(日), api.影子(`?营业日=${encodeURIComponent(日)}`), api.封印列表()]);
    set核(k);
    set影子(s);
    set封印行(f);
  };

  useEffect(() => {
    刷新().catch((e) => set讯(String(e.message || e)));
  }, []);

  const 执行 = async (动作) => {
    set忙(true);
    set讯("");
    try {
      const r = 动作 === "封印" ? await api.封印(日, 原因) : await api.解封(日, 原因);
      set讯(
        动作 === "封印"
          ? `已封印 ${r.营业日} 指纹 ${String(r.正式指纹).slice(0, 12)}…（${r.重复 ? "重复幂等" : "首次"}）`
          : `已解封 ${r.营业日}（原因：${原因.trim()}）`
      );
      set原因("");
      await 刷新();
    } catch (e) {
      set讯(String(e.message || e));
    } finally {
      set忙(false);
    }
  };

  const 迟到 = async () => {
    set忙(true);
    set讯("");
    try {
      const r = await api.迟到补抽(
        日,
        [
          {
            流水号: `流-迟到-${Date.now()}`,
            账户键: "户甲",
            营业日: 日,
            发生时: `${日}T23:59:00Z`,
            变动额: 500,
            摘要: "封印后迟到补抽",
          },
        ],
        "",
        票号.trim()
      );
      set讯(
        票号.trim()
          ? `持票补抽完成：正式镜不动，纠偏写入/覆盖 ${r.抽取.纠偏写入 + r.抽取.纠偏覆盖} 行（票号 ${r.票号}）`
          : `迟到补抽完成（无票走影子轨）：正式拒改 ${r.抽取.封印拒改}，影子 ${
              r.抽取.影子写入 + r.抽取.影子覆盖
            } 行`
      );
      await 刷新();
    } catch (e) {
      set讯(String(e.message || e));
    } finally {
      set忙(false);
    }
  };

  return (
    <div>
      <h1 className="题">快照封印</h1>
      <p className="述">
        封印后正式有效镜冻结在封印指纹上；再抽/迟到补抽只落影子快照（非有效）。解封窗票（口径乙）只开待发布纠偏簿、正式永冻，须另办发布解封才并入正式；无票迟到补抽两端皆拒。解封须填原因并留痕。
      </p>
      <div className="行">
        <input value={日} onChange={(e) => set日(e.target.value)} placeholder="YYYY-MM-DD" />
        <input value={原因} onChange={(e) => set原因(e.target.value)} placeholder="封印/解封原因（解封必填）" />
        <input value={票号} onChange={(e) => set票号(e.target.value)} placeholder="迟到补抽窗票票号（空=无票将被拒）" />
        <button disabled={忙} onClick={() => 执行("封印")}>执行封印</button>
        <button className="次" disabled={忙} onClick={() => 执行("解封")}>解封手续</button>
        <button className="水" disabled={忙} onClick={迟到}>迟到补抽样例</button>
        <button className="次" onClick={() => 刷新().catch((e) => set讯(String(e.message || e)))}>刷新核证</button>
      </div>
      {讯 ? <p className="讯">{讯}</p> : null}

      <div className="段">
        <h2 className="段题">封印核证（只读）</h2>
        {!核 ? (
          <div className="空态">输入营业日查看核证</div>
        ) : (
          <table>
            <tbody>
              <tr><th>营业日</th><td>{核.营业日}</td></tr>
              <tr><th>状态</th><td>{核.状态}</td></tr>
              <tr><th>已封印</th><td>{核.已封印 ? "是" : "否"}</td></tr>
              <tr><th>正式指纹</th><td>{核.正式指纹 || "—"}</td></tr>
              <tr><th>当前指纹</th><td>{核.当前指纹 || "—"}</td></tr>
              <tr>
                <th>valid</th>
                <td>
                  {核.valid ? <span className="徽章 通">在封且未漂</span> : <span className="徽章 败">指纹漂移</span>}
                </td>
              </tr>
              <tr><th>影子有无</th><td>{核.影子有无 ? `有（${核.影子行数} 行）` : "无"}</td></tr>
              <tr><th>窗票</th><td>{核.窗票数 ? `共 ${核.窗票数} 张，当前有效 ${核.有效窗数} 张` : "无"}</td></tr>
              <tr><th>待发布纠偏</th><td>{核.纠偏簿有无 ? `有（${核.待发布纠偏行数} 行，见解封窗票页）` : "无"}</td></tr>
              <tr><th>封印时刻</th><td>{核.封印时刻 || "—"}</td></tr>
              <tr><th>解封原因</th><td>{核.解封原因 || "—"}</td></tr>
            </tbody>
          </table>
        )}
      </div>

      <div className="段">
        <h2 className="段题">影子快照（只读 · 非有效）</h2>
        {!影子.length ? (
          <div className="空态">无影子行</div>
        ) : (
          <table>
            <thead>
              <tr><th>账户键</th><th>营业日</th><th>影子余额</th><th>正式余额</th><th>差额</th><th>批次</th><th>来源</th><th>状态</th></tr>
            </thead>
            <tbody>
              {影子.map((r) => (
                <tr key={r.快照键}>
                  <td>{r.账户键}</td><td>{r.营业日}</td><td>{r.余额}</td>
                  <td>{r.正式余额 ?? "—"}</td><td>{r.差额 ?? "—"}</td>
                  <td>{r.抽取批次编号}</td><td>{r.来源}</td>
                  <td>{r.状态 === "在影" ? <span className="徽章 通">在影</span> : <span className="徽章 败">已作废</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="段">
        <h2 className="段题">封印记录</h2>
        {!封印行.length ? (
          <div className="空态">尚无封印</div>
        ) : (
          <table>
            <thead>
              <tr><th>营业日</th><th>状态</th><th>正式指纹</th><th>行数</th><th>封印时刻</th><th>封印原因</th><th>解封时刻</th></tr>
            </thead>
            <tbody>
              {封印行.map((r) => (
                <tr key={r.营业日}>
                  <td>{r.营业日}</td>
                  <td>{r.状态 === "在封" ? <span className="徽章 通">在封</span> : <span className="徽章 败">已解封</span>}</td>
                  <td>{String(r.正式指纹).slice(0, 16)}…</td>
                  <td>{r.快照行数}</td>
                  <td>{r.封印时刻}</td>
                  <td>{r.封印原因 || "—"}</td>
                  <td>{r.解封时刻 || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
