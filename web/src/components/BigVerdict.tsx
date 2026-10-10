import { CheckCircle2, AlertTriangle, XCircle } from "lucide-react";
import type { Summary } from "../types";

type Tone = "good" | "mid" | "bad";

function build(s: Summary) {
  const st = s.metrics.strategy;
  const bm = s.metrics.benchmark;
  const clf = s.metrics.classification;

  const auc = clf.roc_auc ?? 0.5;
  const dd = Math.abs(st.max_drawdown ?? 0);
  const bdd = Math.abs(bm.max_drawdown ?? 0);
  const ex = st.total_return ?? 0;
  const bex = bm.total_return ?? 0;

  // 它猜得准吗
  const guess =
    auc >= 0.55
      ? { t: "还行", b: `它猜涨跌的准确度比瞎猜强一些（${auc.toFixed(2)} 分，满分 1 分，0.5 分是瞎猜）。` }
      : auc >= 0.51
      ? { t: "很勉强", b: `它几乎猜不准，只比瞎猜好一丁点（${auc.toFixed(2)} 分，0.5 分就是瞎猜）。` }
      : { t: "基本不会", b: `它猜得跟瞎猜差不多（${auc.toFixed(2)} 分，0.5 分是瞎猜），也就是没什么真本事。` };

  // 会不会亏
  const risk =
    dd <= 0.15
      ? { t: "亏得不多", b: `最惨的时候亏了约 ${(dd * 100).toFixed(0)}%，比一直拿着（${(bdd * 100).toFixed(0)}%）安全。` }
      : dd <= 0.28
      ? { t: "有涨有跌", b: `最惨亏了约 ${(dd * 100).toFixed(0)}%，波动还可以接受。` }
      : { t: "亏得多", b: `最惨亏了约 ${(dd * 100).toFixed(0)}%，起伏很大，心脏要够强。` };

  // 能赚多少
  const gain =
    ex >= bex * 0.6
      ? { t: "还不错", b: `总共赚了 ${(ex * 100).toFixed(0)}%，和一直拿着（${(bex * 100).toFixed(0)}%）差不多。` }
      : { t: "赚得少", b: `总共 ${(ex * 100).toFixed(0)}%，比一直拿着（${(bex * 100).toFixed(0)}%）赚得少。` };

  let tone: Tone = "mid";
  let answer = "这套方法有点靠不住，只能当参考";
  if (auc <= 0.5 && ex < bex) {
    tone = "bad";
    answer = "这套方法不靠谱，别照它买卖";
  } else if (auc > 0.5 && ex >= 0) {
    tone = "good";
    answer = "这套方法表现还不错，可以参考";
  }

  const lead =
    tone === "good"
      ? "用历史数据试了一遍，结果还算过得去。"
      : tone === "mid"
      ? "用历史数据试了一遍，结果只能算一般。"
      : "用历史数据试了一遍，结果不太好。";

  const advice =
    auc <= 0.5
      ? "想让它更靠谱：换成「稳一点」的风格、把「预测未来几天」拉长一点，或者干脆别太依赖它，只当个参考。"
      : "想更放心：换个时间段再测一次，看看它是不是一直这么稳，再决定信不信它。";

  return {
    tone,
    answer,
    lead,
    why: [
      { lead: "它猜得准吗？", ...guess },
      { lead: "会不会亏钱？", ...risk },
      { lead: "能赚多少？", ...gain },
    ],
    advice,
  };
}

export default function BigVerdict({ summary }: { summary: Summary }) {
  const v = build(summary);
  const rec = (summary as any).recommendation;
  const Icon = v.tone === "good" ? CheckCircle2 : v.tone === "mid" ? AlertTriangle : XCircle;
  const actionCls =
    rec?.action === "买入" || rec?.action === "持有"
      ? "up"
      : rec?.action === "卖出"
      ? "down"
      : "muted";

  return (
    <div className={`banner ${v.tone}`}>
      <div className="ic">
        <Icon size={40} strokeWidth={2} />
      </div>
      <div className="main">
        <h2>{v.answer}</h2>
        <div className="lead">{v.lead}</div>
        <div className="why">
          {v.why.map((w) => (
            <div className="li" key={w.lead}>
              <span className="b">{w.lead}</span>
              <span>
                <b style={{ color: "var(--text)" }}>{w.t}</b> —— {w.b}
              </span>
            </div>
          ))}
        </div>

        {rec && (
          <div className="infobox" style={{ background: "rgba(255,255,255,0.65)" }}>
            <div>
              <b>现在怎么做：</b>
              <span className={actionCls} style={{ fontWeight: 700 }}>
                {rec.action}
              </span>
              。{rec.sizing_note}
            </div>
            <div style={{ marginTop: 6 }}>
              <b>为什么是这个结论：</b>
              {rec.reasons.join("；")}。
            </div>
            <div style={{ marginTop: 6 }}>
              <b>什么时候该卖：</b>
            </div>
            <ul style={{ margin: "4px 0 0", paddingLeft: 20 }}>
              {rec.sell_conditions.map((c: string) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        )}

        <div style={{ marginTop: 16, fontSize: 14.5, color: "var(--text-2)" }}>💡 {v.advice}</div>
      </div>
    </div>
  );
}
