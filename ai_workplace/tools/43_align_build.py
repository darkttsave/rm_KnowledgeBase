#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Task 4 (phase B1) -- step 2: finalise the chapter correspondence.

Inputs
  * align_candidates.json   -- program-generated candidates + evidence
  * the explicit MANUAL decisions below (each one carries its evidence)

Every formal section of both documents is placed in exactly one alignment unit;
the script refuses to run if a section would be silently omitted.

Outputs (ai_workplace/alignment/)
  章节对应关系.json / 章节对齐总览.md / 章节对齐异常清单.md
"""
import os
import json
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRUCT = os.path.join(ROOT, "ai_workplace", "structured")
OUT = os.path.join(ROOT, "ai_workplace", "alignment")
os.makedirs(OUT, exist_ok=True)

REL_CN = {"kept": "保留", "renamed": "重命名", "moved": "迁移", "merged": "合并",
          "split": "拆分", "added": "疑似新增", "deleted": "疑似删除"}

# --------------------------------------------------------------------------- #
# Manual decisions for every section the automatic (identical-title) pass could
# not resolve.  Evidence strings point at the artefacts used:
#   C:align_candidates.json   S:42_search.py<term>   D:section text diff
#   M:2027 §1.2 新赛季主要变更
# --------------------------------------------------------------------------- #
MANUAL = [
    # ---------------- chapter 3: robot types restructured ----------------
    dict(id="A03-01", s2026=["3.1 英雄机器人", "3.2 工程机器人"], s2027=["3.1.1 重装机器人"],
         relation="merged", confidence=0.95, needs_review=True,
         evidence=[
             "M:2027 §1.2「原英雄机器人和工程机器人合并为重装机器人」",
             "D:2027 表3-3 重装机器人的关键特征 = 2026 表3-3 英雄机器人（42mm 发射机构/启动区）"
             " + 表3-4 工程机器人（装配能量单元/经验与性能体系不适用）的合并",
             "D:2027 3.1.1 段落「可以通过获取并装配能量单元…还可以发射42mm弹丸」同时含两者特征",
             "C:content_sim 英雄→重装 0.47、工程→重装 0.49；工程机器人 100% 条款路由到 3.1.1",
         ],
         note="2027 新增「模块化42mm 发射机构」内容；2026「部署模式」在 2027 全文 0 次出现"
              "（S:部署模式），属正文差异，留待 B2 判定，不在 B1 判为删除",
         content_hint="2026 英雄机器人的「部署模式」机制在 2027 中未检出"),
    dict(id="A03-02", s2026=[], s2027=["3.1 机器人"], relation="added",
         confidence=0.9, needs_review=False,
         evidence=[
             "D:该节正文为空（0 字符），仅作为 2027 新增的 L2 层级容器",
             "D:其子节 3.1.1/3.1.2/3.1.3 分别对接 2026 的 3.1+3.2 / 3.3 / 3.5",
         ],
         note="仅新增层级容器，不是全新规则机制；不判为「新机制」"),
    dict(id="A03-03", s2026=["3.4 空中机器人"], s2027=["3.2.1 空中系统"],
         relation="renamed", confidence=0.95, needs_review=True,
         evidence=[
             "M:2027 §1.2「原空中机器人调整为空中系统（包含空中机器人和机库）」",
             "D:2027 3.2.1 含 表3-7 空中机器人关键特征（沿用 2026 表3-6）+ 表3-8 机库的关键特征（新增）",
             "C:content_sim 0.39；2026 3.4 的条款 100% 路由到 3.2.1",
             "S:机库 2026 0 次 / 2027 25 次",
         ],
         note="「空中系统」= 空中机器人 + 机库；机库为新机制，B1 只记录章节对应"),
    dict(id="A03-04", s2026=[], s2027=["3.2 组合系统"], relation="added",
         confidence=0.9, needs_review=False,
         evidence=[
             "D:该节正文为空（0 字符），仅作为 2027 新增的 L2 层级容器",
             "D:其子节 3.2.1/3.2.2/3.2.3 分别对接 2026 的 3.4 / 3.6 / 3.7",
         ], note="仅新增层级容器，不是全新规则机制"),
    dict(id="A03-05", s2026=["3.7 雷达"], s2027=["3.2.3 雷达系统"],
         relation="renamed", confidence=0.95, needs_review=False,
         evidence=[
             "D:正文几乎逐字相同（「雷达可自主获取战场信息…」），仅删去「或反制对方空中机器人的空中支援」",
             "C:content_sim 0.82（本章最高）",
         ],
         note="删除的分句涉及已取消的雷达反制机制，属正文差异"),
    dict(id="A03-06", s2026=[], s2027=["3.3 附属设备"], relation="added",
         confidence=0.9, needs_review=False,
         evidence=[
             "D:该节正文为空（0 字符），仅作为 2027 新增的 L2 层级容器",
             "D:其唯一子节 3.3.1 对接 2026 的 5.7 自定义客户端",
         ], note="仅新增层级容器，不是全新规则机制"),
    dict(id="A03-07", s2026=["5.7 自定义客户端"], s2027=["3.3.1 自定义终端"],
         relation="moved", confidence=0.95, needs_review=True,
         evidence=[
             "M:2027 §1.2「原自定义控制器与自定义客户端合并为自定义终端」",
             "C:content_sim 0.85；2026 5.7 的条款 95% 路由到 3.3.1，反向 100%",
             "D:章节从「5 比赛机制」迁移到「3 机器人与操作手 › 3.3 附属设备」并改名",
         ],
         note="同时是迁移 + 重命名 + 与「自定义控制器」合并；因为 2026 没有独立的「自定义控制器」章节，"
              "合并的 1:n 侧在章节层面不可见，已在正文层面标注"),
    # ---------------- chapter 4: venue ----------------
    dict(id="A04-01", s2026=["4.2.4 停机坪"], s2027=[], relation="deleted",
         confidence=0.85, needs_review=True,
         evidence=[
             "M:2027 §1.2「取消飞行区、无线充电装置放置区、停机坪」",
             "S:停机坪 2026 21 次 / 2027 仅 1 次（且仅出现在 §1.2 变更说明中）",
             "D:2027 4.2.4 是「制高点」，内容与停机坪无关（制高点位于基地区，与梯形高地相连）",
         ], note="2027 同名位置 4.2.4 是新增的「制高点」，不能与停机坪视为对应"),
    dict(id="A04-02", s2026=[], s2027=["4.2.4 制高点"], relation="added",
         confidence=0.9, needs_review=True,
         evidence=[
             "M:2027 §1.2「新增制高点、机库平台、工作台」",
             "S:制高点 2026 0 次 / 2027 21 次",
             "D:新场地要素（基地区内，与梯形高地三级台阶相连），2026 无对应章节",
         ], note="虽然是新增场地要素，但它同时承接了 2026「梯形高地增益点」的 50% 防御机制（见 5.5.3.4 → 5.6.4.3）"),
    dict(id="A04-03", s2026=["4.4.2 飞坡"], s2027=["4.4.2 隧道"], relation="renamed",
         confidence=0.95, needs_review=False,
         evidence=[
             "M:2027 §1.2「原飞坡改为隧道」",
             "C:content_sim 0.51；2026 4.4.2 条款 100% 路由到 4.4.2 隧道",
         ], note="编号相同、位置相同，仅名称与地形形式变化"),
    dict(id="A04-04", s2026=["4.5 飞行区"], s2027=[], relation="deleted",
         confidence=0.9, needs_review=True,
         evidence=[
             "M:2027 §1.2「取消飞行区、无线充电装置放置区、停机坪」",
             "S:飞行区 2026 5 次 / 2027 仅 1 次（§1.2）",
             "D:该节内容为安全绳、回收系统、飞行空域限制；2027 空中系统改为全自动+机库，相应机制整体取消",
         ], note=""),
    dict(id="A04-05", s2026=[], s2027=["4.3.2.2 机库平台"], relation="added",
         confidence=0.95, needs_review=False,
         evidence=[
             "M:2027 §1.2「新增制高点、机库平台、工作台」",
             "S:机库 2026 0 次 / 2027 25 次",
         ], note="空中系统的新部署位置"),
    # ---------------- chapter 5: mechanisms ----------------
    dict(id="A05-01", s2026=["5.1.5.5 激光检测模块离线"], s2027=[], relation="deleted",
         confidence=0.9, needs_review=True,
         evidence=[
             "S:激光检测模块 2026 15 次 / 2027 0 次；激光发射装置 2026 7 次 / 2027 0 次",
             "D:该节内容依赖「空中支援」与雷达激光反制，两者在 2027 均已不存在",
             "D:2027 5.1.5 下只有 4 个子节（异常/装甲或超级电容/测速/定位），无激光检测模块",
         ], note="与 5.6.3 空中机器人特殊机制同属被取消的雷达反制链路"),
    dict(id="A05-02", s2026=["5.6.1 英雄机器人特殊机制", "5.6.2 工程机器人特殊机制"],
         s2027=["5.7.1 重装机器人特殊机制"], relation="merged",
         confidence=0.85, needs_review=True,
         evidence=[
             "M:2027 §1.2「取消英雄机器人特殊机制、工程机器人特殊机制、空中机器人特殊机制」"
             "以及「新增重装机器人特殊机制」",
             "D:2027 5.7.1 首段「比赛的前3 分钟，且未成功安装模块化42mm 发射机构前，重装机器人拥有50%防御增益」"
             "= 2026 5.6.2 工程机器人特殊机制的 50% 防御条款（条件加严）",
             "C:2026 5.6.2 条款 100% 路由到 5.7.1；5.6.1→5.7.1 content_sim 0.18",
             "S:部署模式 2026 17 次 / 2027 0 次 → 2026 5.6.1 的部署模式机制在 2027 未检出",
         ],
         note="章节层面按「重装=英雄+工程」判为 2:1 合并；但内容层面只有工程的 50% 防御被继承，"
              "英雄的部署模式疑似取消 —— 此处保留 needs_review，不直接判定规则删除，留 B2 核实",
         content_hint="2026 5.6.1 部署模式（17 次）在 2027 全文未检出"),
    dict(id="A05-03", s2026=["5.6.3 空中机器人特殊机制"], s2027=[], relation="deleted",
         confidence=0.9, needs_review=True,
         evidence=[
             "M:2027 §1.2「取消空中机器人特殊机制」",
             "S:空中支援 2026 21 次 / 2027 0 次",
             "S:激光发射装置 2026 7 次 / 2027 0 次（该节的「被雷达反制」子机制）",
             "D:该节由「空中支援」+「空中机器人被雷达反制」两部分组成，两者在 2027 均无对应内容",
         ], note="2027 的 3.2.1 空中系统是机型章节，不承载此机制"),
    dict(id="A05-04", s2026=["5.6.6 雷达特殊机制"], s2027=["5.7.4 雷达系统特殊机制"],
         relation="renamed", confidence=0.95, needs_review=False,
         evidence=[
             "S:被标记进度 7/7、识别误差 1/1、双倍易伤 5/5（2026 5.6.6 与 2027 5.7.4 完全对应）",
             "C:content_sim 0.93；2026 5.6.6 条款 90% 路由到 5.7.4，反向 95%",
             "D:章节编号 5.6.6 → 5.7.4 并改名「雷达特殊机制」→「雷达系统特殊机制」",
         ], note=""),
    dict(id="A05-05", s2026=["5.6.7 能量机制"], s2027=[], relation="deleted",
         confidence=0.85, needs_review=True,
         evidence=[
             "S:底盘能量 2026 10 次 / 2027 0 次；节能 2/0；电源管理模块 2/0",
             "D:2027 全文未检出底盘能量体系（初始能量/节能状态/无线充电回能），"
             "且 §1.2「取消无线充电装置放置区」与之相关",
         ], note="判定为章节删除；建议 B2 复核是否以其他表述保留"),
    dict(id="A05-06", s2026=["5.5.3.4 梯形高地增益点机制"], s2027=["5.6.4.3 制高点增益点机制"],
         relation="renamed", confidence=0.8, needs_review=True,
         evidence=[
             "D:2026「所有己方地面机器人均可占领己方梯形高地增益点…获得50%防御增益」"
             "vs 2027「所有己方机器人都可激活己方制高点增益点…获得50%防御增益，且能够非远程兑换允许发弹量」"
             "——机制骨架一致，承载位置由梯形高地改为制高点",
             "S:梯形高地 2027 仅 6 次（均为场地描述），无「梯形高地增益点」章节；"
             "制高点 2026 0 次 / 2027 21 次",
             "M:2027 §1.2「新增制高点」",
         ], note="增益点由梯形高地迁移到新增的制高点，并追加「非远程兑换允许发弹量」；"
                 "同时属重命名与迁移，需人工确认是否按「重命名」处理"),
    dict(id="A05-07", s2026=[], s2027=["5.2 自适应装甲机制"], relation="added",
         confidence=0.95, needs_review=False,
         evidence=[
             "M:2027 §1.2「新增自适应装甲机制」",
             "S:自适应装甲 2026 0 次 / 2027 3 次",
             "D:含新表 表5-5 装甲模块各区域伤害倍率对照表、命中率/可加固面积公式，2026 无对应章节",
         ], note="2027 新增独立机制章节；挤占了原 5.2 回血与复活机制的编号（后者后移到 5.3）"),
    dict(id="A05-08", s2026=[], s2027=["5.6.2 战场控制机制"], relation="added",
         confidence=0.95, needs_review=False,
         evidence=[
             "S:阵地 2026 0 次 / 2027 38 次；控制度 2026 0 次 / 2027 15 次",
             "D:含新表 表5-20 阵地与控制关系、表5-21 阵地控制状态转化机制，2026 无对应机制",
         ], note="新增机制，插在 5.6.1 基地及前哨站机制之后，导致其后各节编号 +1"),
    # ---------------- chapter 7: penalties ----------------
    dict(id="A07-01", s2026=["7.2.2.3 空中机器人", "7.2.2.4 其他机器人"],
         s2027=["7.2.2.3 组合系统"], relation="merged",
         confidence=0.9, needs_review=True,
         evidence=[
             "D:2027 R47/R48/R49 对应 2026 7.2.2.3 的空中机器人条款（R48/R49/R50 顺延重编号）",
             "D:2027 7.2.2.3 中的 R50「除在七分钟比赛阶段，飞镖系统不得处于待发射状态…」"
             "= 2026 7.2.2.4 其他机器人 R56 原文",
             "C:2026 7.2.2.4 条款 75% 路由到 7.2.2.3",
         ], note="判罚条目整体重编号，需在 B2 逐条比对（R 编号不可直接作为对应依据）"),
    dict(id="A07-02", s2026=["7.2.1.1 通用规范"], s2027=["7.2.1.1 通用规范"], relation="kept",
         confidence=1.0, needs_review=False,
         evidence=["C:content_sim 1.00；父路径同为 7.2 判罚细则 › 7.2.1 人员（自动匹配因同名 2 处而跳过，此处消歧）"],
         note=""),
    dict(id="A07-03", s2026=["7.2.2.1 通用规范"], s2027=["7.2.2.1 通用规范"], relation="kept",
         confidence=1.0, needs_review=False,
         evidence=["C:content_sim 0.99；父路径同为 7.2 判罚细则 › 7.2.2 机器人（同名消歧）"], note=""),
    dict(id="A07-04", s2026=["7.2.2 机器人"], s2027=["7.2.2 机器人"], relation="kept",
         confidence=1.0, needs_review=False,
         evidence=["D:两级均为无正文的容器节（0 字符），父路径一致"], note=""),
    # ---------------- appendix ----------------
    dict(id="A08-01", s2026=["附录1 雷达信息波特性"], s2027=[], relation="deleted",
         confidence=0.85, needs_review=True,
         evidence=[
             "S:频谱 2026 3 次 / 2027 0 次；空口 7/0；调制 3/0 —— 该附录的物理层内容在 2027 全文未检出",
             "S:信息波 2027 仅 5 次，其中 3 次在 5.7.4 的「雷达解析信息波」概念表述，无独立附录",
             "D:2027 附录只有「附录1 赛前流程说明」「附录2 未来规则规划」，无雷达附录",
         ], note="疑似整体删除；5.7.4 保留了「解析信息波」的概念但无该附录的频率/空口/调制内容"),
    dict(id="A08-02", s2026=["附录2 赛前流程说明"], s2027=["附录1 赛前流程说明"],
         relation="kept", renumbered=True, confidence=0.95, needs_review=False,
         evidence=[
             "D:三个 L2 子节（预检录/场地道具训练/适应性训练）标题与正文完全对应",
             "C:content_sim 1.00（仅附录编号由 2 变为 1）",
         ], note="附录编号顺延（前一附录被删除导致），附录名称与内容不变，判为保留"),
    dict(id="A08-03", s2026=["附录3 未来规则规划"], s2027=["附录2 未来规则规划"],
         relation="kept", renumbered=True, confidence=0.95, needs_review=False,
         evidence=[
             "D:标题语义一致，正文均为极短说明（2026 36 字 / 2027 3 字）",
             "C:name_sim 0.60；编号由 3 变 2",
         ], note="附录编号顺延，名称与主题不变，判为保留"),
    # ---------------- 2027 only ----------------
    dict(id="A01-01", s2026=[], s2027=["1.2 新赛季主要变更"], relation="added",
         confidence=0.95, needs_review=False,
         evidence=[
             "D:2027 新增章节，2026 §1 只有 1.1 关于比赛 / 1.2 关于比赛规则文件 / 1.3 关于答疑",
             "D:内容是变更摘要，不属于规则机制正文；已作为对齐参考使用但未替代正文比对",
         ], note="新增的「变更说明」章节，建议在差异分析时排除或单独归类"),
]

# Sections that must stay unmatched on the 2026 side (deleted) / 2027 side (added)
# are all declared in MANUAL above; anything left is expected to be a 1:1 auto match.


def key(s):
    return s["no"] or s["title"]


def main():
    cand = json.load(open(os.path.join(OUT, "align_candidates.json"), encoding="utf-8"))
    s26 = {key(x): x for x in cand["sections_2026"]}
    s27 = {key(x): x for x in cand["sections_2027"]}
    auto = cand["auto"]

    # ---- sections consumed by manual units ----
    # MANUAL may refer to a section either by its number ("5.6.2") or by its full
    # title ("5.6.2 工程机器人特殊机制"); both resolve to the canonical key.
    alias26 = {}
    for x in cand["sections_2026"]:
        alias26[key(x)] = key(x)
        alias26[x["title"]] = key(x)
    alias27 = {}
    for x in cand["sections_2027"]:
        alias27[key(x)] = key(x)
        alias27[x["title"]] = key(x)

    def canon(raw, alias, side_name):
        if raw not in alias:
            raise SystemExit("manual: %s section not found: %r" % (side_name, raw))
        return alias[raw]

    used26, used27 = set(), set()
    for u in MANUAL:
        u["s2026"] = [canon(k, alias26, "2026") for k in u["s2026"]]
        u["s2027"] = [canon(k, alias27, "2027") for k in u["s2027"]]
        for k in u["s2026"]:
            assert k not in used26, "manual: 2026 section listed twice: %s" % k
            used26.add(k)
        for k in u["s2027"]:
            assert k not in used27, "manual: 2027 section listed twice: %s" % k
            used27.add(k)

    # ---- auto 1:1 units ----
    by_id26 = {x["id"]: x for x in cand["sections_2026"]}
    by_id27 = {x["id"]: x for x in cand["sections_2027"]}
    units = []
    for a in auto:
        a26 = by_id26[a["a"]]
        a27 = by_id27[a["b"]]
        k26, k27 = key(a26), key(a27)
        if k26 in used26 or k27 in used27:
            continue
        used26.add(k26)
        used27.add(k27)
        units.append(dict(
            id=None,
            s2026=[k26], s2027=[k27],
            relation="kept",
            renumbered=a26["no"] != a27["no"],
            confidence=0.9 if a26["no"] == a27["no"] else 0.85,
            needs_review=False,
            evidence=["P:标题去掉编号后完全相同（%r）" % a26["name"],
                      "C:content_sim %s、name_sim %s" % (a["content_sim"], a["name_sim"]),
                      "P:编号 %s → %s%s" % (a26["no"] or "-", a27["no"] or "-",
                                            "" if a26["no"] == a27["no"] else "（顺延位移，标题未变）")],
            note="",
        ))
    units += MANUAL

    # ---- coverage check ----
    missing26 = [k for k in s26 if k not in used26]
    missing27 = [k for k in s27 if k not in used27]
    if missing26 or missing27:
        print("UNCOVERED 2026:", missing26)
        print("UNCOVERED 2027:", missing27)
        raise SystemExit("alignment incomplete -- refusing to write output")

    # ---- sort units by the 2026 order (added units go where their 2027 section sits) ----
    order26 = {key(x): i for i, x in enumerate(cand["sections_2026"])}
    order27 = {key(x): i for i, x in enumerate(cand["sections_2027"])}
    units.sort(key=lambda u: (order26[u["s2026"][0]] if u["s2026"]
                              else 1000 + order27[u["s2027"][0]]))
    for i, u in enumerate(units, 1):
        u["id"] = "AL-%03d" % i

    # ---- match_type / relation sanity ----
    for u in units:
        n26, n27 = len(u["s2026"]), len(u["s2027"])
        u["match_type"] = "%d:%d" % (n26, n27)
        if n27 == 0:
            assert u["relation"] == "deleted", u
        elif n26 == 0:
            assert u["relation"] == "added", u
        elif n26 > 1 and n27 == 1:
            assert u["relation"] == "merged", u
        elif n26 == 1 and n27 > 1:
            assert u["relation"] == "split", u
        else:
            assert n26 == 1 and n27 == 1, u

    def side(key_, d, doc):
        x = d[key_]
        return dict(id=x["id"], no=x["no"], title=x["title"], name=x["name"],
                    level=x["level"], path=x["path"],
                    physical_pages=x["pages"], printed_pages=x["printed"],
                    chars=x["chars"], tables=x["tables"], figures=x["figures"])

    out = OrderedDict()
    out["meta"] = dict(
        task="阶段 B1 章节对齐",
        generated=__import__("datetime").datetime.now().isoformat(timespec="seconds"),
        documents=dict(
            doc_2026=dict(id="RMUC2026", version="V2.2.0", source_file=cand["sections_2026"][0] and
                          "2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf", sections=len(s26)),
            doc_2027=dict(id="RMUC2027", version="V1.0.0",
                          source_file="RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf",
                          sections=len(s27)),
        ),
        inputs=["ai_workplace/structured/2026_章节骨架.json",
                "ai_workplace/structured/2027_章节骨架.json",
                "ai_workplace/structured/2026_结构化.jsonl",
                "ai_workplace/structured/2027_结构化.jsonl"],
        method=dict(
            step1="程序生成候选：标题字符二元组 Jaccard + 正文（含表格单元格）字符二元组余弦 + 弱编号先验",
            step2="程序做条款级路由（每个 ≥10 字条款按二元组包含度路由到最相似章节），用份额矩阵暴露合并/拆分",
            step3="LLM（本 agent）依据上述量化证据 + 2027 §1.2「新赛季主要变更」逐条裁断，判断依据逐条写入 evidence",
            notes="2027 §1.2 只作为佐证，不作为唯一依据；编号相同不作为对应依据"),
        relations=REL_CN,
        unmatched_policy="无法对应的一律进入「疑似新增 / 疑似删除」单元并标 needs_review，不强制匹配")
    out["alignments"] = []
    for u in units:
        out["alignments"].append(OrderedDict([
            ("align_id", u["id"]),
            ("relation", u["relation"]),
            ("relation_cn", REL_CN[u["relation"]]),
            ("match_type", u["match_type"]),
            ("renumbered", bool(u.get("renumbered")) or (len(u["s2026"]) == 1 and len(u["s2027"]) == 1 and u["s2026"][0] != u["s2027"][0])),
            ("confidence", u["confidence"]),
            ("needs_review", u["needs_review"]),
            ("sections_2026", [side(k, s26, "2026") for k in u["s2026"]]),
            ("sections_2027", [side(k, s27, "2027") for k in u["s2027"]]),
            ("evidence", u["evidence"]),
            ("note", u.get("note", "")),
            ("content_delta_hint", u.get("content_hint", "")),
        ]))

    idx26 = {k: u["id"] for u in units for k in u["s2026"]}
    idx27 = {k: u["id"] for u in units for k in u["s2027"]}
    out["section_index"] = OrderedDict([
        ("2026", OrderedDict((key(x), idx26[key(x)]) for x in cand["sections_2026"])),
        ("2027", OrderedDict((key(x), idx27[key(x)]) for x in cand["sections_2027"])),
    ])
    cnt = {}
    for u in units:
        cnt[u["relation"]] = cnt.get(u["relation"], 0) + 1
    out["coverage"] = OrderedDict([
        ("sections_2026", len(s26)), ("sections_2027", len(s27)),
        ("units", len(units)),
        ("units_by_relation", {REL_CN[k]: v for k, v in sorted(cnt.items())}),
        ("sections_2026_mapped", len(used26)), ("sections_2027_mapped", len(used27)),
        ("sections_2026_unmapped", sorted(k for k in s26 if k not in used26)),
        ("sections_2027_unmapped", sorted(k for k in s27 if k not in used27)),
        ("needs_review_units", [u["id"] for u in units if u["needs_review"]]),
        ("deleted_sections", [k for u in units if u["relation"] == "deleted" for k in u["s2026"]]),
        ("added_sections", [k for u in units if u["relation"] == "added" for k in u["s2027"]]),
    ])

    json.dump(out, open(os.path.join(OUT, "章节对应关系.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("units:", len(units), " by relation:", cnt)
    print("2026 sections:", len(s26), " mapped:", len(used26))
    print("2027 sections:", len(s27), " mapped:", len(used27))
    print("needs_review:", sum(1 for u in units if u["needs_review"]))
    print("written 章节对应关系.json")


if __name__ == "__main__":
    main()
