# 渲染验证层（Render Verification Layer）设计规格

状态：**设计稿，待评审**。本文档是 T38 的设计基线；获批后按 §7 分期实施，
每期独立验收。实施前需按契约 §12 完成两处基线确认（见 §8）。

## 1. 背景与动机

### 1.1 问题：枚举式修复的缝隙

当前检测器的主体是"代理特征 + 阈值"的启发式判定。近期的三个修复暴露了
同一类结构性弱点——代理特征与真实语义之间存在缝隙，每条缝隙都是一个
未来的误报或漏报：

| 案例 | 启发式 | 缝隙 | 修复方式 |
| --- | --- | --- | --- |
| T29 invisible_text | `dark_box_min_area_ratio=0.1` 过滤"背景盒子" | 饼图扇形（小面积矢量填充）被过滤，白字误判不可见 | 阈值降到 0.0005 |
| T25 content_out_of_page | bbox 与页面矩形求交 | 贴边元素的测量噪声被当越界 | 容差 0.005 |
| T25 number_mismatch | 移页时豁免上下 8% 带 | 带内正文与带外页脚一视同仁 | 移页条件豁免带 |

三个修复本身都是对的，但它们共同说明：**只要判定停留在几何代理层，
每遇到一种新排版就要重新调一次代理特征**。

### 1.2 原理：假设—实证模型

文档质检的终极事实只有两个：**渲染出来的像素**与**提取出的内容**。
检测器报出的每条 Issue 本质是一个假设（"这段文字不可见""内容越出页面"）。
渲染验证层的核心是：**假设必须经过像素级实证才能以原严重度成立**。

T29 排查时已经完整手工执行过一次该闭环：渲染目标区域 → 采样文字
bbox 内像素与背景像素 → 证明白字在彩色扇区上清晰可见 → 误报结论。
当时的验证是一次性工具；本设计把它平台化为管线的常驻阶段。

### 1.3 与契约 §2 的关系（重要）

契约 §2 规定"不以单一图片相似度或单次大模型判断作为最终依据"。渲染
验证层**不是**整页图片相似度：它对每条 Issue 的**具体主张**做定向实证
（"不可见"→ 测对比度；"越界"→ 测内容存在性），结论与数值证据全部写入
metrics 供人工复核。这是"可复核的结构化证据"的强化而非违背；相似度
打分、LLM 判断仍然被排除在外。

## 2. 设计原则

1. **假设—实证分离**：检测器负责提出假设（启发式，宽而不漏）；验证器
   负责实证裁决（渲染像素，窄而不冤）。两层职责不允许互相渗透。
2. **验证只裁决、不新增**：验证器不产生新 Issue。它不是第二个检测引擎，
   不做"验证器自己的检测"，避免系统复杂度翻倍。
3. **证据强制落 metrics**（契约 §6.4）：verdict 与全部判定数值写入
   `issue.metrics["verification"]`，shadow 期同样写入。
4. **默认 shadow，逐类启用**：先只记录不改行为（Golden 逐位不变），
   按 Issue 类型逐个切换到 enforce。
5. **fail-open**：渲染失败、超时、验证器异常一律放行原 Issue
   （verdict=`unverified`）。验证层故障的后果是"回到现状"（多误报），
   而不是制造漏报。质检工具中漏报的代价高于误报。
6. **阈值集中**：验证层的全部判定阈值进入 `RuleProfile`（新增
   `verification` 设置段），运行时实际值进 metrics。
   **实现期修正**：RuleProfile 会全量快照进报告（`rule_profile_snapshot`），
   任何新增字段都会改变报告 JSON、破坏 shadow 期"Golden 逐位一致"的
   验收前提——因此阶段 1 的配置以 `verification` 包内集中定义的引擎级
   常量运行（单一 settings 类，含全部阈值与注释），阶段 2 enforce 时
   随 Golden 更新一并迁入 RuleProfile。

## 3. 架构

### 3.1 管线位置

```text
Detector → [Verifier（新增，可选）] → Scorer → Reporter
```

挂在 `_compare_page` 中：全部布局检测（rules）与内容检测（content /
glossary / raster_ocr）完成之后、`scorer.score` 之前。此时该页候选
Issue 集合已完整，且页面上下文（路径、密码、页对象）在作用域内。

### 3.2 组件与接口

新增 `core/src/document_qa/verification/` 包（core 零 HTTP 不变）：

```python
Verdict = Literal["confirmed", "rejected", "downgraded", "unverified"]

class VerificationContext:  # 每页构造一次
    """渲染实证所需的只读上下文。"""
    renderer: PyMuPDFRenderer          # 复用管线渲染器
    source_path / target_path: Path
    source_password / target_password: str | None
    thresholds: VerificationSettings   # 来自 RuleProfile

class IssueVerifier(Protocol):
    """按 Issue 类型注册的实证裁决器。"""
    def verify(self, issue: Issue, ctx: VerificationContext) -> Verdict: ...
```

- 注册表按 `IssueType` 映射验证器；无验证器的类型直接 `unverified` 放行。
- `VerificationContext` 内部按 `(path, password)` 缓存已打开的 PDF
  Document、按 `(path, page)` 缓存整页 pix——`render_crop_png` 现版每次
  调用重新打开文档，验证器必须走批量缓存路径（见 §5）。
- 验证层整体包在 try/except 中，任何异常 → 该 Issue `unverified`。

### 3.3 裁决语义

| Verdict | 含义 | shadow 行为 | enforce 行为 |
| --- | --- | --- | --- |
| `confirmed` | 实证支持主张 | 经 progress 事件通道输出 | 原样输出 |
| `rejected` | 实证否定主张 | 经 progress 事件通道输出 | severity 降为 INFO，描述追加"已渲染实证否定（详见 metrics）"，保留可解释性 |
| `downgraded` | 实证部分支持（如重叠但可读） | 经 progress 事件通道输出 | 按验证器定义降级 |
| `unverified` | 无验证器/渲染失败/超限 | 不输出 | 原样输出（fail-open） |

**shadow 不改动 Issue 输出**（含 metrics）：一旦写入
`metrics["verification"]` 报告 JSON 即发生变化，"Golden 逐位一致"
的验收前提就不成立。因此 shadow 期的裁决经管线既有的 progress 事件
通道输出（`stage="verification"`，服务端随之落入任务进度 JSONL），
metrics 落盘推迟到 enforce 期与严重度变更一并引入、随当期 Golden
更新。

enforce 期 `rejected` 选择"降 INFO 保留"而不是"删除"：验收人能看到
系统看过并否决了什么，误判验证器本身时也有痕迹可查。评分影响：INFO
不触发 PASS/REVIEW/FAIL 翻转、不计入 problem_total 的严重度加权——
具体扣分行为随 enforce 期的 Golden 更新逐条核对。

## 4. 各 Issue 类型的可实证性盘点

设计的关键取舍：**验证层只处理"视觉后果类"主张，不处理"几何/内容
事实类"主张**。偏移了多少、数字是否一致，是解析层与匹配层的事实，
渲染不构成反证；强行纳入只会制造不可解释的否决。

| Issue 类型 | 主张 | 可实证性 | 实证方法 | 成本/条 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| `invisible_text` | 译文文字在页面上不可见 | **强**（T29 已手工验证） | 渲染目标区域裁切，文字 bbox 内采样像素与周边背景的对比度 ≥ 阈值 → 可见 → rejected | 1 次裁切（页 pix 缓存后近乎免费） | **P0** |
| `content_out_of_page` | 内容越出页面边界 | 强 | 渲染 bbox 与页面交集区域，交集内实际内容像素占比 < 阈值 → rejected；完全页外（交集为空）直接 confirmed | 1 次裁切 | **P1** |
| `text_image_overlap` / `text_overlap` | 重叠遮挡影响可读 | 中（可读性是连续量） | 渲染重叠区，文字像素对比度 + 被遮挡面积比；候选加强：小 OCR 交叉读出文字 → downgraded | 1-3 次裁切（OCR 交叉限 HIGH+ 抽样） | P2 |
| `text_rasterized` | 文字被图片化 | 强（机制与 invisible_text 对偶） | 渲染源区域含文字而目标对应图片区域无对应字形 → confirmed（当前启发式已较准，仅 shadow 观察） | 1-2 次裁切 | P2 |
| `region_shifted` / `region_resized` | 位置/尺寸变化 | ✗ 几何事实，渲染不能否证 | —（治理走对应关系对齐，非本层） | — | 不纳入 |
| `number_mismatch` / `untranslated_text` | 数值/文本不一致 | ✗ 内容事实 | —（治理走数量签名 T36 与移页结构判定） | — | 不纳入 |
| `missing_element` / `added_element` / `missing_image` | 对应关系缺失/新增 | ✗ 本质是对应关系问题 | —（治理走匹配层改进） | — | 不纳入 |
| `font_shrink` / `text_fragmented` / `typography_changed` | 样式/结构变化 | 弱（渲染可测字形高度/连续性但判据主观） | 首期不纳入，shadow 数据积累后再评估 | — | 暂缓 |

首期只做 P0（`invisible_text`）：方法论已被 T29 验证、已知误报库存
明确（SyneosHealth 一对即 38 条）、实现面最小。P1/P2 在 P0 的 shadow
数据证明基础设施稳定后推进。

## 5. 渲染成本控制

以最坏情况实测数据估算（state-of-ai 对：41 页、178 条 Issue）：

1. **只渲染候选区域**：验证发生在检测之后，渲染对象是 Issue 的
   bbox（含 padding），不是整页对整页。
2. **Document 与页 pix 双级缓存**：`VerificationContext` 按
   `(path, password)` 缓存打开的 Document、按 `(path, page, dpi)` 缓存
   整页 pix，裁切从 pix 取。同一页多条 Issue 只渲染一次整页。
   估算上例：涉及的独立 (side, page) 组合 ≈ 82，一次整页渲染 ≈ 数十
   毫秒，合计增量 ≈ 3-5 秒，对比该对 20 分钟的总耗时（<0.5%）。
3. **DPI 独立阈值**：`verification_dpi`（默认 96，与 OCR 用 DPI 解耦——
   对比度采样不需要 OCR 的精度）。
4. **单页验证上限**：`verification_max_per_page`（默认 50），超限部分
   `unverified`，防极端页拖垮管线。
5. **验收预算**：启用后端到端耗时增量 < 15%（无 OCR 文档），
   E2E 计时验收。

## 6. 证据格式

enforce 期起，每条被验证的 Issue 在 metrics 写入：

```json
"verification": {
  "verdict": "rejected",
  "method": "pixel_contrast",
  "dpi": 96,
  "sample_count": 214,
  "text_pixel_contrast": 0.83,
  "background_reference": "ring_sampling",
  "threshold_used": 0.35,
  "duration_ms": 12
}
```

阈值名与数值同时记录（契约 §12"运行时实际使用值必须进入 metrics"）。
shadow 期同样的结构经 progress 事件通道（`stage="verification"`）输出，
服务端落入任务进度 JSONL 供排查与 T21 归因消费；该通道同时是校准
闭环的新数据源：按类型统计 rejected 率，即是各检测器启发式的持续
精度度量。

## 7. 分期实施与验收

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| 0 | 契约 §7 组件图增补 Verifier 节点（§8 基线确认） | 用户批准 |
| 1（shadow） | `verification` 包骨架 + `invisible_text` 验证器 + progress 事件通道裁决输出，全局 shadow | examples 对 Golden **逐位一致**；SyneosHealth 对 shadow 裁决与 T29 人工结论一致（38 条应全数 rejected）；构造用例：真不可见文字（白色 on 白底）confirmed、半透明渐变背景边界用例不崩溃；静态验收全绿；耗时预算达标 |
| 2（enforce P0） | `invisible_text` 切 enforce（rejected → INFO 保留） | Golden 漂移逐条解释并更新基线；rejected 条目抽查 ≥ 10 条人工复核零冤杀 |
| 3 | `content_out_of_page`（P1）shadow→enforce | 同上模式；越界真阳性（构造用例）零漏放 |
| 4 | overlap 类（P2，含抽样 OCR 交叉验证） | 按相同模式 |

每期独立提交、独立可回滚（enforce 开关 = RuleProfile 内
`verification.enforce_types` 列表，随 profile 版本化）。

## 8. 需要用户确认的基线事项（契约 §12）

1. **契约 §7 组件边界图**增补 `Verifier` 节点（Detector 与 Scorer 之间）
   ——属于项目基线变更；
2. **阶段 2 起**的 enforce 行为改变既有 Issue 输出（严重度降级），属
   "严重度阈值变更"，每次启用都附 Golden Sample 前后差异并更新基线。

## 9. 与其他原理性路径的关系

- **对应关系对齐**（span 级内容图对齐，T27 的推广）：治理几何/对应类
  误报的根因路径，与本层互补——本层管"视觉后果类"，它管"对应关系类"。
- **T21 校准闭环**：消费本层的 verdict 统计作为检测器精度指标，
  阈值标定从逐案调参走向语料级校准。
- 明确不做：整页相似度、多模态模型判断（契约 §2 排除项）。
