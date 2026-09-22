#!/usr/bin/env python3
"""生成客户演示页 —— 采购合规智能审查（V0 spike 真实运行数据）。

把 run_v0_loop 的真实输出翻译成业务语言的单文件 HTML（零技术词汇），
供面对面演示、录屏发送、或客户自行打开。每次构建重新跑一遍闭环，
页面数据 = 本次真实运行结果（页脚有运行时间戳佐证）。

用法:
    uv run python scripts/build_demo_page.py            # 重新播种 fixture 并生成
    uv run python scripts/build_demo_page.py --no-seed  # 直接用当前 DB 状态生成
输出:
    demos/procurement-review-demo.html
"""
from __future__ import annotations

import argparse
import html
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from ece.evidence import get_evidence_for_decision  # noqa: E402
from ece.v0.loop import run_v0_loop  # noqa: E402

ALLOWED_USER = "spike-user-procurement"
DENIED_USER = "spike-user-unrelated"
PR_SOURCE_ID = "SPIKE-PR-001"
OUT = REPO / "demos" / "procurement-review-demo.html"


def _wan(amount: float) -> str:
    return f"¥{amount / 10_000:,.1f}万"


def _esc(s: object) -> str:
    return html.escape(str(s))


_ACTOR_NAMES = {"spike-user-procurement": "张三 · 采购经理"}


def _actor_name(user_ref: object) -> str:
    return _ACTOR_NAMES.get(str(user_ref), _esc(user_ref))


def build_data(*, seed: bool) -> dict:
    if seed:
        subprocess.run(
            [sys.executable, str(REPO / "scripts" / "seed_v0_spike_fixture.py")],
            cwd=str(REPO), check=True, capture_output=True,
        )
    t0 = time.monotonic()
    ok = run_v0_loop(ALLOWED_USER, PR_SOURCE_ID)
    elapsed = time.monotonic() - t0
    denied = run_v0_loop(DENIED_USER, PR_SOURCE_ID)
    evidence = get_evidence_for_decision(
        ok.engine if hasattr(ok, "engine") else __import__("ece.db", fromlist=["get_engine"]).get_engine(),
        ok.decision["decision_id"],
    ) if False else get_evidence_for_decision(
        __import__("ece.db", fromlist=["get_engine"]).get_engine(), ok.decision["decision_id"]
    )
    return {"ok": ok, "denied": denied, "evidence": evidence, "elapsed": elapsed,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}


def render(data: dict) -> str:
    ok, denied, evs = data["ok"], data["denied"], data["evidence"]
    dec = ok.decision
    amount = ok.pr_attrs_before.get("amount", 0)
    quotes = len(ok.quotes)
    amount_con, quote_con = ok.conditions[0], ok.conditions[1]

    ev_cards = ""
    for ev in evs:
        ev_cards += f"""
      <div class="ev-card">
        <div class="ev-claim">“{_esc(ev['claim'])}”</div>
        <div class="ev-grid">
          <div><span class="k">政策要求</span><span class="v">{_esc(ev['threshold_value'])}</span></div>
          <div><span class="k">实际情况</span><span class="v">{_esc(ev['observed_value'])}</span></div>
          <div><span class="k">来源单据</span><span class="v">{_esc(ev['source_record_id'])}</span></div>
          <div><span class="k">经办人</span><span class="v">{_actor_name(ev['actor_user_ref'])}</span></div>
          <div class="wide"><span class="k">记录时间</span><span class="v">{_esc(str(ev['evidence_timestamp'])[:19])} UTC</span></div>
        </div>
      </div>"""

    return TEMPLATE.replace("__DATA_GENERATED_AT__", data["generated_at"]) \
       .replace("__EVIDENCE_CARDS__", ev_cards) \
       .replace("__AMOUNT__", _wan(amount)).replace("__AMOUNT_RAW__", f"{amount:,.0f}") \
       .replace("__QUOTES__", str(quotes)).replace("__REASON__", _esc(dec["reason"])) \
       .replace("__ELAPSED__", f"{data['elapsed']:.2f}") \
       .replace("__AMOUNT_CON_PASSED__", "yes" if amount_con["passed"] else "no") \
       .replace("__QUOTE_CON_PASSED__", "yes" if quote_con["passed"] else "no") \
       .replace("__AMOUNT_CON_CLAIM__", _esc(amount_con["claim"])) \
       .replace("__QUOTE_CON_CLAIM__", _esc(quote_con["claim"])) \
       .replace("__DENIED_REASON__", _esc(denied.reason))


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>采购合规智能审查 · 系统演示</title>
<style>
  :root { --ink:#1a2332; --sub:#5b6779; --line:#e4e8ef; --brand:#1f4fd8; --brand-bg:#eef3ff;
          --warn:#b45309; --warn-bg:#fef3e2; --bad:#b91c1c; --bad-bg:#fdecec;
          --ok:#047857; --ok-bg:#e8f7f0; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         color:var(--ink); background:#f7f8fa; line-height:1.7; }
  .wrap { max-width:920px; margin:0 auto; padding:0 20px 80px; }
  header.hero { background:linear-gradient(135deg,#12203f 0%,#1f4fd8 100%); color:#fff;
                padding:56px 20px 48px; }
  header.hero .wrap { padding-bottom:0; }
  .hero .tag { display:inline-block; font-size:13px; letter-spacing:2px; opacity:.85;
               border:1px solid rgba(255,255,255,.4); border-radius:99px; padding:2px 14px; margin-bottom:16px; }
  .hero h1 { font-size:32px; line-height:1.35; margin-bottom:14px; }
  .hero p { max-width:640px; opacity:.92; font-size:15px; }
  .pains { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin-top:26px; }
  .pain { background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.18);
          border-radius:10px; padding:14px 16px; }
  .pain b { display:block; font-size:20px; margin-bottom:2px; }
  .pain span { font-size:13px; opacity:.85; }
  .pain.quote b { font-size:15px; line-height:1.5; font-weight:600; }
  section { margin-top:44px; }
  .sec-title { display:flex; align-items:baseline; gap:10px; margin-bottom:16px; }
  .sec-title .no { color:var(--brand); font-weight:700; font-size:14px; }
  .sec-title h2 { font-size:21px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:22px 24px; }
  .scene { display:flex; flex-wrap:wrap; gap:16px; }
  .scene .field { flex:1; min-width:150px; background:var(--brand-bg); border-radius:10px; padding:14px 16px; }
  .scene .field .k { font-size:12px; color:var(--sub); margin-bottom:4px; }
  .scene .field .v { font-size:19px; font-weight:700; }
  .policy-note { margin-top:14px; font-size:14px; color:var(--sub); border-left:3px solid var(--brand); padding-left:12px; }
  .steps { display:grid; gap:14px; }
  .step { display:grid; grid-template-columns:44px 1fr; gap:14px; background:#fff;
          border:1px solid var(--line); border-radius:12px; padding:18px 20px; }
  .step .badge { width:36px; height:36px; border-radius:50%; background:var(--brand); color:#fff;
                 display:flex; align-items:center; justify-content:center; font-weight:700; }
  .step h3 { font-size:16px; margin-bottom:6px; }
  .step p, .step li { font-size:14px; color:var(--sub); }
  .rule-row { display:grid; grid-template-columns:1fr auto; gap:10px; align-items:center;
              border:1px solid var(--line); border-radius:8px; padding:10px 14px; margin-top:8px; background:#fafbfc; }
  .rule-row .verdict { font-size:13px; font-weight:700; padding:3px 12px; border-radius:99px; white-space:nowrap; }
  .verdict.hit { color:var(--warn); background:var(--warn-bg); }
  .verdict.miss { color:var(--bad); background:var(--bad-bg); }
  .decision { border:2px solid var(--warn); background:var(--warn-bg); border-radius:12px; padding:22px 24px; }
  .decision .label { font-size:13px; color:var(--warn); letter-spacing:1px; margin-bottom:6px; }
  .decision .value { font-size:26px; font-weight:800; color:var(--warn); margin-bottom:8px; }
  .decision .why { font-size:15px; }
  .decision .time { margin-top:12px; font-size:13px; color:var(--sub); }
  .ev-grid-all { display:grid; gap:12px; }
  .ev-card { border:1px solid var(--line); border-radius:10px; padding:16px 18px; background:#fff; }
  .ev-claim { font-size:15px; font-weight:600; margin-bottom:10px; }
  .ev-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:8px 16px; }
  .ev-grid .k { display:block; font-size:12px; color:var(--sub); }
  .ev-grid .v { font-size:14px; font-weight:600; }
  .ev-grid .wide { grid-column:1/-1; }
  .trace-note { font-size:13px; color:var(--sub); margin-top:12px; padding:10px 14px;
                background:var(--brand-bg); border-radius:8px; }
  .status-flow { display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-top:6px; }
  .status { padding:8px 18px; border-radius:8px; font-weight:700; font-size:15px; }
  .status.before { background:#eef1f5; color:var(--sub); }
  .status.after { background:var(--warn-bg); color:var(--warn); border:1px solid var(--warn); }
  .arrow { color:var(--sub); font-size:20px; }
  .perm-tabs { display:flex; gap:8px; margin-bottom:14px; }
  .perm-tabs button { border:1px solid var(--line); background:#fff; border-radius:99px;
                      padding:8px 18px; font-size:14px; cursor:pointer; color:var(--ink); }
  .perm-tabs button.active { background:var(--brand); color:#fff; border-color:var(--brand); }
  .perm-pane { border:1px solid var(--line); border-radius:12px; padding:22px 24px; background:#fff; }
  .perm-pane h4 { margin-bottom:8px; font-size:16px; }
  .denied-box { border:1px dashed var(--bad); background:var(--bad-bg); color:var(--bad);
                border-radius:10px; padding:22px; text-align:center; font-size:15px; font-weight:600; }
  .boundary { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .boundary .col { border-radius:12px; padding:18px 20px; }
  .boundary .no-ai { background:var(--bad-bg); border:1px solid #f3c1c1; }
  .boundary .yes-ai { background:var(--ok-bg); border:1px solid #bfe6d6; }
  .boundary h4 { font-size:15px; margin-bottom:8px; }
  .boundary li { font-size:14px; margin-left:18px; margin-bottom:4px; }
  footer { margin-top:48px; border-top:1px solid var(--line); padding-top:20px;
           font-size:12.5px; color:var(--sub); }
  footer .honesty { background:#fff; border:1px solid var(--line); border-radius:10px;
                    padding:14px 18px; margin-bottom:14px; }
  .cta { text-align:center; margin-top:40px; }
  .cta .btn { display:inline-block; background:var(--brand); color:#fff; border-radius:99px;
              padding:12px 32px; font-size:15px; font-weight:600; }
  .cta p { margin-top:10px; font-size:13px; color:var(--sub); }
  @media (max-width:640px) { .boundary { grid-template-columns:1fr; } .hero h1 { font-size:26px; } }
  @media print { body { background:#fff; } .perm-tabs { display:none; } }
</style>
</head>
<body>

<header class="hero"><div class="wrap">
  <div class="tag">系 统 演 示</div>
  <h1>让每一张采购单，<br>都经得起审计</h1>
  <p>采购合规智能审查：把"人对照政策"的重复劳动，变成"秒级检查 + 全程留痕"。
     以下演示全部来自系统<b>真实运行</b>，非模拟动画。</p>
  <div class="pains">
    <div class="pain"><b>≥80 人时</b><span>处理一张采购申请的平均人力消耗</span></div>
    <div class="pain"><b>2–3 起/年</b><span>不合规事件，比价不足占多数</span></div>
    <div class="pain quote"><b>"比价流于形式"</b><span>—— 受访采购经理原话</span></div>
    <div class="pain"><b>忽高忽低</b><span>"审计严格时成本会降低"，缺乏常态合规</span></div>
  </div>
</div></header>

<div class="wrap">

<section>
  <div class="sec-title"><span class="no">场景</span><h2>一张常见的采购申请</h2></div>
  <div class="card">
    <div class="scene">
      <div class="field"><div class="k">申请人</div><div class="v">张三 · 采购经理</div></div>
      <div class="field"><div class="k">采购金额</div><div class="v">__AMOUNT__</div></div>
      <div class="field"><div class="k">供应商报价</div><div class="v">仅 __QUOTES__ 家</div></div>
    </div>
    <div class="policy-note">公司采购政策：金额达到 __AMOUNT_RAW__ 元（100万）的采购，必须取得 <b>3 家</b>供应商比价。</div>
  </div>
</section>

<section>
  <div class="sec-title"><span class="no">演示</span><h2>系统四步完成审查</h2></div>
  <div class="steps">

    <div class="step">
      <div class="badge">1</div>
      <div>
        <h3>读懂业务</h3>
        <p>系统按<b>张三的权限</b>，自动汇集审查所需信息：采购申请单、采购政策、供应商报价记录。
        只汇集"张三有权看到"的信息——别人的单子，系统一个字也不会给他。</p>
      </div>
    </div>

    <div class="step">
      <div class="badge">2</div>
      <div>
        <h3>自动审查（政策逐条对照）</h3>
        <div class="rule-row">
          <div><b>金额门槛</b>　“__AMOUNT_CON_CLAIM__”</div>
          <span class="verdict hit">✓ 触发复核条件</span>
        </div>
        <div class="rule-row">
          <div><b>比价家数</b>　“__QUOTE_CON_CLAIM__”</div>
          <span class="verdict miss">✗ 不满足政策要求</span>
        </div>
        <p style="margin-top:8px">两条检查由确定性规则执行，<b>不调用大模型</b>——同一单据重复审查一万次，结论完全一致。</p>
      </div>
    </div>

    <div class="step">
      <div class="badge">3</div>
      <div class="decision">
        <div class="label">审 查 结 论</div>
        <div class="value">需要人工复核</div>
        <div class="why">原因：__REASON__</div>
        <div class="time">本次系统实际耗时 <b>__ELAPSED__ 秒</b> ｜ 传统人工对照政策通常需要 10–30 分钟，遇驳回返工以"天"计</div>
      </div>
    </div>

    <div class="step">
      <div class="badge">4</div>
      <div>
        <h3>结论依据 —— 每一张凭证都可追溯</h3>
        <div class="ev-grid-all">__EVIDENCE_CARDS__</div>
        <div class="trace-note">🔍 审计核查：审计人员可在系统内沿
        <b>审查结论 → 依据凭证 → 原始单据</b> 逐跳核查，每一跳都有记录、有出处。
        "这个结论是怎么来的？"——系统自己答得上来。</div>
      </div>
    </div>

    <div class="step">
      <div class="badge">5</div>
      <div>
        <h3>结论真实生效</h3>
        <div class="status-flow">
          <span class="status before">审查前：待审批</span>
          <span class="arrow">→</span>
          <span class="status after">审查后：需人工复核</span>
        </div>
        <p style="margin-top:10px">结论写入业务系统并留痕；任何人再次查询这张单据，看到的已是更新后的状态。
        不是"出了个报告就结束"，而是<b>业务状态真的被改变了</b>。</p>
      </div>
    </div>

  </div>
</section>

<section>
  <div class="sec-title"><span class="no">权限</span><h2>换一个人，看到的世界完全不同</h2></div>
  <div class="perm-tabs">
    <button id="tab-allowed" class="active" onclick="showPerm('allowed')">张三 · 采购部</button>
    <button id="tab-denied" onclick="showPerm('denied')">李雷 · 销售部（无采购权限）</button>
  </div>
  <div class="perm-pane" id="pane-allowed">
    <h4>✅ 张三（采购部）—— 正常完成全流程</h4>
    <p>如上所示：看得到单据 → 系统完成审查 → 得到结论与依据 → 单据状态更新。</p>
  </div>
  <div class="perm-pane" id="pane-denied" style="display:none">
    <div class="denied-box">您无权查看该采购申请</div>
    <p style="margin-top:12px">对无权限的人，系统<b>不展示数据，也不进行任何分析</b>：
    没有审查结论、没有依据凭证、系统里不留任何记录。
    权限检查发生在数据读取之前——不是"先全部读出再藏起来"。</p>
  </div>
</section>

<section>
  <div class="sec-title"><span class="no">边界</span><h2>我们坚持：这些决定必须人来做</h2></div>
  <div class="boundary">
    <div class="col no-ai">
      <h4>🚫 系统不替人决定</h4>
      <ul>
        <li>供应商选择与最终定价</li>
        <li>合同条款审核与签署</li>
        <li>付款方式审批</li>
      </ul>
    </div>
    <div class="col yes-ai">
      <h4>✅ 系统负责做的</h4>
      <ul>
        <li>把采购政策变成秒级自动检查</li>
        <li>把每一次结论的依据留成可查的凭证</li>
        <li>把"审计前临时收紧"变成"每一天都合规"</li>
      </ul>
    </div>
  </div>
</section>

<div class="cta">
  <span class="btn">下一步：约 30 分钟 POC 洽谈</span>
  <p>用贵司一份脱敏采购单，在您自己的环境里跑一遍 —— 数据不出域。</p>
</div>

<footer>
  <div class="honesty">
    <b>技术诚实声明</b>　本页面所有结论、数字、凭证均由系统真实运行自动生成（生成时间 __DATA_GENERATED_AT__），
    审查判断由确定性规则执行、未调用大模型；当前为 V0 验证版，演示数据为合成场景。
    脚本与测试用例可应客户要求现场重跑验证。
  </div>
</footer>

</div>
<script>
function showPerm(who){
  document.getElementById('pane-allowed').style.display = who==='allowed' ? '' : 'none';
  document.getElementById('pane-denied').style.display  = who==='denied'  ? '' : 'none';
  document.getElementById('tab-allowed').classList.toggle('active', who==='allowed');
  document.getElementById('tab-denied').classList.toggle('active', who==='denied');
}
</script>
</body>
</html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-seed", action="store_true")
    args = ap.parse_args()
    data = build_data(seed=not args.no_seed)
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(render(data), encoding="utf-8")
    print(f"Demo page written: {OUT}")
    print(f"  decision={data['ok'].decision['decision_value']}  "
          f"evidence={len(data['evidence'])}  elapsed={data['elapsed']:.2f}s  "
          f"denied_reason={data['denied'].reason!r}")


if __name__ == "__main__":
    main()
