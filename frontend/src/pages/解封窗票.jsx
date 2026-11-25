import React, { useEffect, useState } from "react";
import { api } from "../api.js";

const 日 = "2026-11-22";

export default function 解封窗票页() {
  const [日v, set日v] = useState(日);
  const [票号, set票号] = useState("");
  const [窗起, set窗起] = useState("");
  const [窗止, set窗止] = useState("");
  const [范围, set范围] = useState("");
  const [原因, set原因] = useState("");
  const [发布原因, set发布原因] = useState("");
  const [核证票号, set核证票号] = useState("");
  const [票列表, set票列表] = useState([]);
  const [单票, set单票] = useState(null);
  const [纠偏, set纠偏] = useState([]);
  const [审计, set审计] = useState([]);
  const [讯, set讯] = useState("");
  const [忙, set忙] = useState(false);

  const 刷新 = async () => {
    const [票s, 簿, 审] = await Promise.all([
      api.窗票核证("", 日v),
      api.纠偏簿(`?营业日=${encodeURIComponent(日v)}`),
      api.窗票审计(`?营业日=${encodeURIComponent(日v)}`),
    ]);
    set票列表(Array.isArray(票s) ? 票s : [票s]);
    set纠偏(簿);
    set审计(审);
    if (核证票号.trim()) {
      set单票(await api.窗票核证(核证票号.trim()));
    } else {
      set单票(null);
    }
  };

  useEffect(() => {
    刷新().catch((e) => set讯(String(e.message || e)));
  }, []);

  const 报 = (p) => {
    set忙(true);
    set讯("");
    p()
      .then(async (r) => {
        set讯(`完成：${JSON.stringify(r).slice(0, 180)}`);
        await 刷新();
      })
      .catch((e) => set讯(String(e.message || e)))
      .finally(() => set忙(false));
  };

  const 开窗 = () =>
    报(() =>
      api.开窗({
        营业日: 日v,
        票号: 票号.trim(),
        窗起: 窗起.trim(),
        窗止: 窗止.trim(),
        允许账户: 范围
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
        原因: 原因.trim(),
      })
    );

  const 核证 = () =>
    报(async () => {
      const r = await api.窗票核证(核证票号.trim());
      set单票(r);
      return r;
    });

  const 补抽 = (号) =>
    报(() =>
      api.迟到补抽(
        日v,
        [
          {
            流水号: `流-窗-${Date.now()}`,
            账户键: "户甲",
            营业日: 日v,
            发生时: `${日v}T23:59:00Z`,
            变动额: 500,
            摘要: "窗内迟到补抽",
          },
        ],
        "",
        号
      )
    );

  return (
    <div>
      <h1 className="题">解封窗票</h1>
      <p className="述">
        口径乙（全局唯一）：窗票只开「待发布纠偏簿」，正式指纹永冻；须另办发布解封才并入正式。
        无票 / 过期 / 超范围 → 正式镜与纠偏簿两端皆拒。开窗与补抽在同一写锁内抢锁，失败闭。
      </p>

      <div className="段">
        <h2 className="段题">① 同票开窗（营业日 · 窗起止 · 允许改写范围 · 票号）</h2>
        <div className="行">
          <input value={日v} onChange={(e) => set日v(e.target.value)} placeholder="营业日 YYYY-MM-DD" />
          <input value={票号} onChange={(e) => set票号(e.target.value)} placeholder="票号（空则自动生成）" />
          <input value={窗起} onChange={(e) => set窗起(e.target.value)} placeholder="窗起 2026-11-22T00:00:00Z（空=此刻）" />
          <input value={窗止} onChange={(e) => set窗止(e.target.value)} placeholder="窗止 2026-11-23T00:00:00Z" />
          <input value={范围} onChange={(e) => set范围(e.target.value)} placeholder="允许账户，逗号分隔；空=全部" />
          <input value={原因} onChange={(e) => set原因(e.target.value)} placeholder="开窗原因" />
          <button disabled={忙} onClick={开窗}>开窗</button>
        </div>
        <div className="行">
          <button className="水" disabled={忙} onClick={() => 报(() => api.拨钟("2026-11-23T00:00:01Z"))}>
            过期夹具：拨到窗止后
          </button>
          <button className="水" disabled={忙} onClick={() => 报(() => api.拨钟("2026-11-22T12:00:00Z"))}>
            回到窗内
          </button>
          <button className="次" disabled={忙} onClick={() => 报(() => api.复位钟())}>复位时钟</button>
        </div>
      </div>

      <div className="段">
        <h2 className="段题">② 按票号打开窗 · 只读核证（票号/窗是否有效/正式指纹/纠偏簿/valid）</h2>
        <div className="行">
          <input value={核证票号} onChange={(e) => set核证票号(e.target.value)} placeholder="输入票号核证" />
          <button className="次" disabled={忙} onClick={核证}>核证</button>
          <button className="次" disabled={忙} onClick={() => 刷新().catch((e) => set讯(String(e.message || e)))}>刷新台面</button>
        </div>
        {单票 ? (
          <table>
            <tbody>
              <tr><th>票号</th><td>{单票.票号}</td></tr>
              <tr><th>营业日</th><td>{单票.营业日}</td></tr>
              <tr><th>窗起/窗止</th><td>{单票.窗起} ~ {单票.窗止}</td></tr>
              <tr><th>状态</th><td>{单票.状态}</td></tr>
              <tr>
                <th>窗是否有效</th>
                <td>
                  {单票.窗是否有效 ? <span className="徽章 通">有效</span> : <span className="徽章 败">{单票.窗失效原因 || "失效"}</span>}
                </td>
              </tr>
              <tr><th>允许账户</th><td>{(单票.允许账户列表 || []).join(", ") || "全部账户"}</td></tr>
              <tr><th>正式指纹（永冻）</th><td>{单票.正式指纹}</td></tr>
              <tr><th>当前指纹</th><td>{单票.当前指纹}</td></tr>
              <tr><th>纠偏簿</th><td>{单票.纠偏簿有无 ? `有（待发布 ${单票.待发布行数}/${单票.纠偏簿行数} 行）` : "无"}</td></tr>
              <tr><th>valid</th><td>{单票.valid ? <span className="徽章 通">true</span> : <span className="徽章 败">false</span>}</td></tr>
            </tbody>
          </table>
        ) : (
          <div className="空态">输入票号查看单票核证</div>
        )}
      </div>

      <div className="段">
        <h2 className="段题">③ 窗票清单（按营业日 {日v}）</h2>
        {!票列表.length ? (
          <div className="空态">尚无窗票</div>
        ) : (
          <table>
            <thead>
              <tr><th>票号</th><th>窗止</th><th>状态</th><th>窗有效</th><th>纠偏(待发/总)</th><th>正式指纹</th><th>valid</th><th>动作</th></tr>
            </thead>
            <tbody>
              {票列表.map((t) => (
                <tr key={t.票号}>
                  <td>{t.票号}</td>
                  <td>{t.窗止}</td>
                  <td>{t.状态 === "在窗" ? <span className="徽章 通">在窗</span> : <span className="徽章 败">{t.状态}</span>}</td>
                  <td>{t.窗是否有效 ? <span className="徽章 通">是</span> : <span className="徽章 败">{t.窗失效原因 || "否"}</span>}</td>
                  <td>{t.待发布行数}/{t.纠偏簿行数}</td>
                  <td>{String(t.正式指纹).slice(0, 14)}…</td>
                  <td>{t.valid ? "true" : "false"}</td>
                  <td>
                    <button className="水" disabled={忙 || !t.窗是否有效} onClick={() => 补抽(t.票号)}>持票补抽样例</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="段">
        <h2 className="段题">④ 发布解封（待发布纠偏 → 正式镜，同写锁重算封印指纹）</h2>
        <div className="行">
          <input value={核证票号} onChange={(e) => set核证票号(e.target.value)} placeholder="待发布票号" />
          <input value={发布原因} onChange={(e) => set发布原因(e.target.value)} placeholder="发布原因（必填，留痕）" />
          <button
            disabled={忙}
            onClick={() =>
              报(async () => {
                const r = await api.窗票发布(核证票号.trim(), 发布原因.trim());
                set发布原因("");
                return r;
              })
            }
          >
            发布解封
          </button>
        </div>
      </div>

      <div className="段">
        <h2 className="段题">纠偏簿（只读 · 正式主读不含）</h2>
        {!纠偏.length ? (
          <div className="空态">无纠偏行</div>
        ) : (
          <table>
            <thead>
              <tr><th>票号</th><th>账户</th><th>正式余额</th><th>纠偏余额</th><th>差额</th><th>状态</th><th>批次</th></tr>
            </thead>
            <tbody>
              {纠偏.map((r) => (
                <tr key={r.纠偏键}>
                  <td>{r.票号}</td><td>{r.账户键}</td><td>{r.正式余额}</td><td>{r.纠偏余额}</td>
                  <td>{r.差额}</td>
                  <td>{r.状态 === "待发布" ? <span className="徽章 通">待发布</span> : <span className="徽章 败">{r.状态}</span>}</td>
                  <td>{r.批次编号}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="段">
        <h2 className="段题">窗票改写审计（同票留痕）</h2>
        {!审计.length ? (
          <div className="空态">无审计</div>
        ) : (
          <table>
            <thead>
              <tr><th>时刻</th><th>票号</th><th>账户</th><th>动作</th><th>结果</th><th>细节</th></tr>
            </thead>
            <tbody>
              {审计.map((r) => (
                <tr key={r.编号}>
                  <td>{r.时刻}</td><td>{r.票号 || "—"}</td><td>{r.账户键 || "—"}</td><td>{r.动作}</td>
                  <td>{r.结果 === "通过" ? <span className="徽章 通">通过</span> : <span className="徽章 败">拒绝</span>}</td>
                  <td>{r.细节}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {讯 ? <p className="讯">{讯}</p> : null}
    </div>
  );
}
