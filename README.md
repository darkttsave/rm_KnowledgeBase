# rm_KnowledgeBase —— RMUC 2026 / 2027 官方规则对比知识库

RoboMaster 超级对抗赛（RMUC）**2026 V2.2.0** 与 **2027 V1.0.0** 两版官方规则手册的
结构化、章节对齐、全文差异发现与语义分析成果仓库。

> 当前状态：**阶段 A / B1 / B2 / C / C 补充核验 已完成**，停在 **阶段 D 人工审核入口**。
> 所有差异与规则变更事件都是**候选**（`verify_status = unverified`），尚未经人工确认，
> 不得直接当作官方规则事实使用。

---

## 1. 数据来源（只读）

| 文件 | 版本 | 物理页 | SHA256 | 是否入库 |
|---|---|---|---|---|
| `原始材料/2026 机甲大师超级对抗赛比赛规则手册V2.2.0.pdf` | V2.2.0 | 159 | `88AE3C7D0BBD7312C8095EFF2603910437E292A0B53F46C9378F26144C09A6F5` | ✅ |
| `原始材料/RoboMaster 2027 机甲大师超级对抗赛比赛规则手册V1.0.0（20261015）-官方版.pdf` | V1.0.0 | 144 | `9E2EED9295536C6FD547B62D634DF1D5E70A2E1E2250E5DFF3521D557E5D54BE` | ✅ |
| 2027 笔记版（个人批注版） | V1.0.0 | 144 | `C085D56458B3D012BE10955B8246CC2BE99CE2A35D9C7674DE6C47B7E6404A14` | ❌ 见下 |

**个人批注版（笔记版）不进入本仓库。** 原因：它是带个人注释的私有副本，且 PDF 中 3 页
（P29 / P76 / P95）的个人批注外观已被压平进正文文本层，不能作为规则正文来源。
该文件保留在原 Windows 工作目录 `原始材料/`，需要时本地使用，勿提交。

两份官方 PDF 全程**只读**：所有阶段的输入哈希与上表一致，未被任何脚本改写。

---

## 2. 目录结构

```
.
├── 原始材料/                       # 两份官方规则 PDF（只读输入）
├── 报告索引.md                      # 全部报告与产物的入口索引
├── docs/
│   ├── 工作现场交接.md              # 执行体交接说明（Windows → Ubuntu）
│   └── 交接工作现场模板.md
└── ai_workplace/
    ├── task_specification/          # 各阶段任务书（task1..task7、交接任务）
    ├── tools/                       # 全部解析/对齐/差异/语义/校验脚本
    ├── audit/                       # 阶段 A-1 预检查产物（JSON、抽样渲染图、表格对照）
    ├── structured/                  # 阶段 A-2/A-3 结构化主数据
    │   ├── 2026_章节骨架.json / 2027_章节骨架.json
    │   ├── 2026_结构化.jsonl / 2027_结构化.jsonl      ← 主数据（逐条可溯源）
    │   ├── 2026_结构化.md  / 2027_结构化.md           ← 人读视图（非事实主数据）
    │   ├── 待人工核验清单.jsonl / quality_checks.json
    │   └── samples/                 # 阶段 A-2 方案验证样本（留档）
    ├── alignment/                   # 阶段 B1 章节对齐（135 个对齐单元）
    ├── diff/                        # 阶段 B2 全文候选差异（1333 条）
    ├── semantic/                    # 阶段 C 语义分析与补充核验
    │   ├── 规则变更候选.jsonl / 规则变更候选_修订版.jsonl
    │   ├── 规则变化初步总览.md / 语义分析争议清单.md / 语义分析质量报告.md
    │   ├── 特殊内容核验报告.md / 未解决争议清单.md / 重点规则人工审核表.md
    │   ├── 阶段C补充核验质量报告.md
    │   ├── batches/                 # 大模型实际读入的输入批次（可复现）
    │   └── compare/*.png            # 14 组新旧页面对照渲染图
    └── report/                      # 各阶段报告 + 每阶段给上游 AI 的反馈报告
```

---

## 3. Ubuntu 环境初始化（克隆后第一步）

```bash
# 1) 克隆（默认分支即 part_2，务必不要切到其他分支）
git clone https://github.com/darkttsave/rm_KnowledgeBase.git
cd rm_KnowledgeBase
git branch --show-current          # 期望输出：part_2

# 2) Python 3.12 虚拟环境
sudo apt update && sudo apt install -y python3.12 python3.12-venv
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements.txt

# 3) 运行脚本必须把工具目录加入 PYTHONPATH（脚本之间会互相 import）
export PYTHONPATH="$PWD/ai_workplace/tools"

# 4) 自检：只跑校验脚本，不重跑解析（校验只读，不改任何产物）
python ai_workplace/tools/99_verify_report.py       # 期望 71 PASS
python ai_workplace/tools/22_verify_structure.py    # 期望 88 PASS
python ai_workplace/tools/45_align_verify.py        # 期望 34 PASS
python ai_workplace/tools/53_b2_verify.py           # 期望 40 PASS
python ai_workplace/tools/64_c_verify.py            # 期望 34 PASS
python ai_workplace/tools/73_c2_verify.py           # 期望 51 PASS
```

> 校验脚本读取的是仓库内已有的 JSONL/JSON 产物，**不需要重跑 PDF 解析**，几秒内完成。
> 全部断言合计 318 项。

---

## 4. 复现全流程（可选，耗时较长）

脚本按编号分阶段，必须按顺序执行；中间产物写入 `ai_workplace/` 对应子目录。
`原始材料/` 下的 PDF 只读。

```bash
export PYTHONPATH="$PWD/ai_workplace/tools"
export TMP="$PWD/.tmp" TEMP="$PWD/.tmp"; mkdir -p .tmp   # 脚本会用到临时目录

# 阶段 A-1 预检查
python ai_workplace/tools/01_structure_probe.py
python ai_workplace/tools/03_deep_probe.py
python ai_workplace/tools/04_samples.py
python ai_workplace/tools/07_tables.py
python ai_workplace/tools/08_toc_check.py
python ai_workplace/tools/06_render.py
python ai_workplace/tools/12_render_diff.py
python ai_workplace/tools/99_verify_report.py

# 阶段 A-2/A-3 结构化
python ai_workplace/tools/20_skeleton.py      # 章节骨架（含父子路径校验）
python ai_workplace/tools/21_samples.py       # 方案验证样本
python ai_workplace/tools/22_verify_structure.py
python ai_workplace/tools/30_fulltext.py      # 全文结构化 -> structured/*.jsonl
python ai_workplace/tools/32_markdown.py      # Markdown 视图
python ai_workplace/tools/33_quality.py       # 67 项质量断言 + 待核验清单

# 阶段 B1 章节对齐
python ai_workplace/tools/40_align_candidates.py
python ai_workplace/tools/43_align_build.py
python ai_workplace/tools/44_align_reports.py
python ai_workplace/tools/45_align_verify.py

# 阶段 B2 全文差异
python ai_workplace/tools/50_b2_body.py
python ai_workplace/tools/51_b2_special.py
python ai_workplace/tools/52_b2_reports.py
python ai_workplace/tools/53_b2_verify.py

# 阶段 C 语义分析
python ai_workplace/tools/60_c_batches.py
python ai_workplace/tools/62_c_events.py
python ai_workplace/tools/63_c_reports.py
python ai_workplace/tools/64_c_verify.py

# 阶段 C 补充核验
python ai_workplace/tools/70_c2_special.py
python ai_workplace/tools/71_c2_revise.py
python ai_workplace/tools/72_c2_reports.py
python ai_workplace/tools/73_c2_verify.py
```

> 阶段 C 的语义判断由 LLM 完成：输入批次、System Prompt、判断规则与模型信息都归档在
> `ai_workplace/semantic/coverage.json`、`ai_workplace/semantic/batches/` 与
> `ai_workplace/semantic/语义分析质量报告.md`。**重跑 62_c_events.py 不会重新调用模型**，
> 它只是把已归档的判断（`61_c_decide.py`）与 B2 记录组装成事件。

---

## 5. 各阶段成果速览

| 阶段 | 产物 | 关键数字 | 断言 |
|---|---|---|---|
| A-1 预检查 | `audit/` | 3 份 PDF、130/129 书签、0 扫描页 | 71 |
| A-2 方案验证 | `structured/*_章节骨架.json`、`samples/` | 134/133 章节区域、302 条样本记录 | 88 |
| A-3 全文结构化 | `structured/*_结构化.jsonl` | 1853 + 1785 条记录、154 张表 | 67 |
| B1 章节对齐 | `alignment/章节对应关系.json` | 135 个对齐单元、130/129 章节全覆盖 | 34 |
| B2 全文差异 | `diff/全文候选差异.jsonl` | 1333 条（534 条变化候选） | 40 |
| C 语义分析 | `semantic/规则变更候选.jsonl` | 62 个规则事件（534 条差异 100% 归并） | 34 |
| C 补充核验 | `semantic/规则变更候选_修订版.jsonl` | 101 条；69 条重点审核表 | 51 |

详细内容请看 `报告索引.md`，以及各目录下的 `*.md` 报告。

---

## 6. 重要约束与使用须知

1. **只读输入**：`原始材料/` 下 PDF 不得修改；所有阶段都以 SHA256 校验一致性。
2. **结果是候选**：`verify_status` 全为 `unverified`；禁止把候选事件写成「已确认」的规则事实。
3. **不使用 OCR**：两份 PDF 都是原生文本 PDF；仅 2027 部分公式使用数学字母数字符号排版，
   其文本层不可信，相关结论一律标注为需人工核对。
4. **不做规则总结**：本仓库只提供证据与候选事件，最终规则解读与队内学习笔记不在此范围。
5. **人工审核入口**：`ai_workplace/semantic/重点规则人工审核表.md`（69 条，含
   「是否影响机器人设计或比赛策略」标注）。

---

## 7. Windows → Linux 移植说明

脚本全部使用 `os.path.abspath(__file__)` 推导项目根目录，**没有硬编码 Windows 绝对路径**，
无需修改即可在 Linux 运行。已知差异与注意事项：

| 项 | 说明 |
|---|---|
| 虚拟环境不含 pip | Windows 侧 venv 用 `--without-pip` 创建（受当时沙箱限制），依赖由外部 pip 装入；Ubuntu 上正常 `python -m venv` + `pip install -r requirements.txt` 即可 |
| `sitecustomize.py` | Windows venv 里有一个仅用于规避沙箱目录权限的补丁，**未入库**，Linux 不需要 |
| 文件编码 | 9 个脚本带 UTF-8 BOM、4 个用 CRLF；Python 均可正常解析，无需转换 |
| 路径含中文 | `原始材料/` 等目录名含中文，Linux 需保证 locale 为 UTF-8（`export LANG=C.UTF-8`） |
| 换行归一化 | `.gitattributes` 设为 `* text=auto`，仓库内存 LF；二进制资产（PDF/PNG）标记为 binary |

---

## 8. 许可与免责

本项目仅用于赛事规则研究与队伍学习，规则原文版权归 RoboMaster 组委会所有。
仓库内容按「现状」提供，不构成任何形式的官方解释；一切以组委会发布的正式规则为准。
