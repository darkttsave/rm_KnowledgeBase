# 任务：rm_KnowledgeBase 仓库初始化与 Windows → Ubuntu 工作现场交接

## 一、任务背景

当前项目位于：

`C:\Users\SHIN\Desktop\RM规则对比`

目标仓库：

https://github.com/darkttsave/rm_KnowledgeBase.git

用户已明确授权：**远端仓库现有测试项目内容可以全部删除，用当前 RM 2026—2027 规则对比项目替换。**

本轮仅负责项目迁移、Git 提交与执行体交接，不继续开展规则分析。

## 二、Git 仓库初始化与迁移

1. 先检查本地工作目录、Git 状态、远端分支及现有文件。
2. 远端仓库目前默认分支为 `part_2`。优先沿用该默认分支完成首次迁移，避免 Ubuntu 克隆后落入错误分支。
3. 使用克隆远端仓库并导入现有项目的方式处理，不能直接将两个无关的 Git 历史强行合并。
4. 删除远端原有测试项目内容，清理旧测试文件。
5. 将当前规则对比项目完整导入，尽量保持现有目录结构，尤其保留：
   - 官方规则 PDF 与版本信息；
   - `ai_workplace/structured/`；
   - `ai_workplace/alignment/`；
   - `ai_workplace/diff/`；
   - `ai_workplace/semantic/`；
   - 解析与质量检查脚本；
   - 各阶段报告、候选差异、人工审核表及必要的图片对照材料。
6. 不覆盖或重写阶段 A/B/C 的业务成果。
7. 配置 `.gitignore`，排除 Python 虚拟环境、缓存、临时目录、无用的本地日志及凭据。
8. 仓库为公开仓库，个人批注版 PDF 默认不上传；保留于 Windows 原工作目录，并在交接文档中注明。两份官方原版 PDF 应保留在仓库内，供后续复现与核验。
9. 添加简洁 README、Python 依赖说明和必要的 Ubuntu 环境初始化说明。
10. 检查现有脚本对 Windows 绝对路径的依赖，记录移植风险；只做必要的跨平台适配，不重构算法。

## 三、Git 提交要求

遵循 `类型: 中文描述` 格式，例如：

- `chore: 清理仓库历史测试文件`
- `feat: 导入RM规则对比结构化资产与分析工具`
- `docs: 补充Ubuntu部署说明与执行体交接`

按逻辑独立提交，不伪造开发历史，不使用无意义的 `update files` 等提交信息。

禁止 `git push --force`，禁止删除远端提交历史，禁止提交敏感凭据。

提交前检查暂存文件清单和文件大小，确认没有误提交虚拟环境或不应公开的数据。

提交后推送到远端默认分支，检查远端文件是否完整，并核对远端 commit SHA。

## 四、工作现场交接

严格参考用户提供的《交接工作现场.md》。

在仓库内生成：

`docs/工作现场交接.md`

按以下结构填写：

### Workspace
- Path：Windows 原始工作目录及 Git 仓库目录
- Branch：实际推送分支
- Commit：最终 SHA
- Dirty Files：未提交修改
- Running Processes / Connections：后台进程与连接情况

### Current Task
本次迁移及下一阶段任务。

### Current Position
阶段 A/B/C 已完成，当前停留在阶段 D 人工审核入口。

### Existing Evidence
报告、规则数据、人工审核表及其他成果的仓库路径。

### Important Local State
只写尚未进入 Git 的重要内容，包括个人批注版 PDF 及特殊环境配置。

### First Next Action
Ubuntu 新执行体接管后的第一个操作。

### Takeover Status
READY / WAIT / PARTIAL

正文建议控制在 300～700 中文字符，已有报告能够说明的细节只提供路径，不重复全文。

## 五、交付与验收

1. 检查本地 Git 状态与远端提交是否一致。
2. 确认 GitHub 上能够访问完整项目。
3. 确认 README 包含 Ubuntu 克隆及环境恢复方法。
4. 检查是否存在未提交的重要文件。
5. 确认迁移后不需要继续依赖 Windows 的工作目录。
6. 给出最终仓库链接、分支、commit SHA，以及是否可以安全接管。

如果认证或权限阻止推送，立即停止并说明原因，不得声称迁移成功。

完成后停止，不继续执行阶段 D 的规则分析。