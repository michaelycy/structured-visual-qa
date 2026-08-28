# 结构化视觉 QA 系统总结

## 1. 系统定位

本系统用于检测文档翻译前后的视觉保真度。它不只回答“两份文档是否相似”，而是输出：

- 哪些结构保持一致；
- 哪些元素发生异常；
- 异常位于哪一页、哪个区域；
- 异常严重程度及其是否影响交付。

系统名称可定位为 **Document Visual Fidelity QA Engine**。

## 2. 核心原则

1. **结构优先**：以 PDF 结构解析为底座；DOCX/PPTX/XLSX 等 Office 格式经 LibreOffice 归一化为 PDF 后复用同一流水线（不做原生解析），再结合页面渲染图。
2. **统一模型**：不同格式统一转换为 `Page / Block / Region / Issue`。
3. **确定性检测为底座**：布局、边界框、字体、间距、对象数量和表格结构由算法与规则检测。
4. **多模态模型负责复核**（规划中，当前 MVP 未启用）：视觉模型接收页面图、结构化差异和已有问题，负责发现遗漏、识别误报及补充观察。
5. **评分与状态分离**：总体分数用于衡量质量；严重问题可以独立触发 `REVIEW` 或 `FAIL`。

## 3. 处理流程

```text
Source / Target Document
          ↓
Document Parser
          ↓
Normalized Page Model
          ↓
Block Extraction → Region Grouping
          ↓
Page / Region Alignment
          ↓
Structured Diff
          ↓
Layout / Typography / Text Flow / Object / Table QA
          ↓
Rule-based Issues
          ↓
Multimodal Visual Review
          ↓
Risk Scoring → PASS / REVIEW / FAIL
          ↓
QA Report
```

### 3.1 当前实现的六段流水线

上面是系统的概念流程。当前代码库已经落地为一个确定性的六段流水线，所有阈值和权重由版本化的 `RuleProfile` 统一驱动：

```text
源 PDF ─┐
        ├─ ①解析 → ②分组 → ③页对齐 → ④Region 匹配 → ⑤检测 → ⑥报告
目标 PDF┘  PyMuPDF  Region    动态规划      全局最优分配       规则引擎   评分+JSON
```

这是 `--verify-stage` 对外暴露的六个阶段：`parse / group / alignment / match /
detect / report`。评分在报告组装阶段执行，不单独形成可暂停的验证阶段。

1. **解析（`parsers/pymupdf_parser.py`）**：提取每个文本 Span 的字体、字号、颜色、透明度、BBox 以及图片块；以 SHA256 作为稳定文档 ID；限制输入不超过 100MB / 500 页。带打开密码的 PDF 可由 CLI/API 显式提供密码，密码只用于解析与渲染，不进入报告或持久化。输出纯数据模型，不携带任何 PyMuPDF 运行时对象。
2. **分组（`grouping/region_grouper.py`）**：把零散 Span 按原始 PDF Block 聚合成可比较的 Region；同行允许保留强调色等混合样式，跨行合并则要求规范化颜色、字号、字重和斜体兼容，并在编号、项目符号或冒号明细处建立不可跨越的条目边界；字号达到全页文本中位数 1.25 倍以上的 Region 标记为标题，其余为段落；按 `(y, x)` 排序并写入上下邻接关系。
3. **页对齐（`matching/page_aligner.py`）**：使用页面版面相似度和动态规划做跨页单调对齐，在 Profile 的移页窗口内恢复对应页，并显式标记缺失页和新增页。
4. **Region 匹配（`matching/`）**：先通过双侧几何对应图，把同栏、连续、同类型且样式相近的原始 Region 组合为逻辑文本流，使两侧 M↔N 的 PDF Block 差异规范化为逻辑 1↔1；已确认逻辑组使用内部配对键锁定。随后按位置、尺寸、类型和顺序加权构建代价矩阵，通过 SciPy 匈牙利算法求全局最优分配；低于 `minimum_score`（默认 0.45）的分配进入缺失/新增判定。
5. **检测（`detectors/`）**：产出页面与元素完整性、几何、排版、可见性、重叠、数字、文本漏译、图像化文字和术语问题。server 可选注入本地 OCR Provider，只对位置尺寸稳定的大图片候选区识别；未启用或失败时不阻断原有确定性流水线。
6. **报告（`scoring/`、`reporting/`）**：先按严重度与 Issue 类型页内上限评分，再输出经 Pydantic 校验的 JSON 报告；报告内嵌 `RuleProfile` 版本引用、完整快照及可选 OCR 运行元数据，并可渲染源/目标页面 PNG。

## 4. 四个核心 Schema

### Page

归一化页面，保存文档标识、页码、页面尺寸、原始 Blocks 和语义 Regions。页面负责校验：

- Block 与 Region ID 在页内唯一；
- 子对象页码与当前页一致；
- Region 引用的 Block 必须存在。

### Block

解析器产生的最小元素，例如文本块、图片、表格、图表或形状。主要字段包括：

- `id`、`page`、`type`；
- `bbox`；
- 可选的 `style` 与 `content`；
- 父子关系和解析器扩展元数据。

### Region

由一个或多个 Block 分组形成的语义比较单元，例如标题、段落、图片或表格。Region 是区域对齐和结构化 Diff 的核心对象，保存：

- 几何位置与尺寸；
- 样式和内容；
- 所包含的 Block ID；
- 上、下、左、右邻接关系。

### Issue

所有检测器与视觉复核器共用的问题格式，保存：

- 页码、问题类型和严重度；
- Source / Target Region 引用；
- 问题位置 `bbox`；
- 检测指标、描述和检测器名称。

## 5. 主要检测层

| 检测层 | 关注内容 | 典型问题 | 实现状态 |
| --- | --- | --- | --- |
| Layout QA | 位置、尺寸、间距、对齐、重叠、越界 | `REGION_SHIFTED`、`CONTENT_OUT_OF_PAGE` | ✅ 已实现 |
| Typography QA | 字号、字重、颜色、对齐、行高、字体兼容性 | `FONT_SHRINK` | ✅ 已实现（字号缩小） |
| Typography QA | 字号放大、对齐方式变化、隐形文字 | `TYPOGRAPHY_CHANGED`、`TEXT_ALIGNMENT_CHANGED`、`INVISIBLE_TEXT` | ✅ 已实现；字体族/字重专项仍未实现 |
| Text Flow QA | 换行、行数、溢出、裁切 | `ABNORMAL_WRAP`、`LINE_COUNT_EXPLOSION`、`TEXT_OVERFLOW`、`TEXT_CLIPPED` | 🔒 规划中（Schema/评分已预留） |
| Text Overlap QA | 文本互叠、文字压图 | `TEXT_OVERLAP`、`TEXT_IMAGE_OVERLAP` | ✅ 已实现 |
| Content QA | 数字一致性、漏译、术语合规 | `NUMBER_MISMATCH`、`UNTRANSLATED_TEXT`、`GLOSSARY_VIOLATION` | ✅ 已实现 |
| Raster Text QA | 图像字形簇、候选区 OCR、转曲/栅格化 | `UNTRANSLATED_RASTER`、`TEXT_VECTORIZED`、`TEXT_RASTERIZED` | ✅ 已实现；OCR 为 server 可选能力 |
| Object QA | 图片、Logo 等对象的数量与位置 | `MISSING_IMAGE`、`MISSING_ELEMENT`、`ADDED_ELEMENT` | ✅ 已实现 |
| Table QA | 行列、合并单元格、边框、单元格布局 | `TABLE_STRUCTURE_CHANGED` | 🔒 规划中（Schema/评分已预留） |

> 注意：`RuleProfile.scoring.issue_type_deduction_caps` 覆盖了全部 Issue 枚举以保证配置完备性，但上表“规划中”的检测器当前不会产出对应 Issue，报告使用者不应假设这些检查已经发生。

字体族不应简单要求完全相同，而应判断字体类别和语言覆盖是否兼容，例如 Arial 与 Noto Sans CJK 可以视为兼容的无衬线字体。

## 6. 区域分组与对齐

原始 Block 不能按序号直接比较。相邻 Block 可以依据字体、字号、X 轴对齐、行间距和语义类型组合成 Region。

Source 与 Target Region 的匹配分数应综合：

```text
position_similarity
+ size_similarity
+ type_similarity
+ neighborhood_similarity
+ order_similarity
+ semantic_similarity
```

跨语言场景下，语义相似度只作为辅助信号；空间结构、元素类型和邻接关系应占更高权重。

## 7. 严重度与最终判定

严重度分为：`INFO / LOW / MEDIUM / HIGH / CRITICAL`。

建议的默认状态规则：

- `PASS`：没有 High/Critical，且分数不低于 90；
- `REVIEW`：存在 High，或分数为 75–90；
- `FAIL`：存在 Critical，或分数低于 75。

该规则应配置化。即使总体平均分较高，文字截断、图片丢失、表格损坏或页面丢失等 Critical 问题仍可直接导致失败。

## 8. MVP 演进记录

项目初始阶段只支持 PDF，并以以下路径形成最短闭环：

```text
PDF 解析
→ Page / Block 标准化
→ Region 分组与对齐
→ Overflow / Overlap / Missing Element 检测
→ JSON 报告
```

后续重点是复杂表格专项检测、通用像素差分、图片 Embedding 和多模态复核。

> 现状：DOCX/PPTX/XLSX 已通过 LibreOffice 归一化支持；Web 可视化、XLSX/HTML
> 导出、图像指纹和候选区 OCR 已落地。表格专项检测、通用像素差分、图片
> Embedding 与多模态复核仍为规划项。
