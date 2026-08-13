# 结构化视觉 QA 系统总结

## 1. 系统定位

本系统用于检测文档翻译前后的视觉保真度。它不只回答“两份文档是否相似”，而是输出：

- 哪些结构保持一致；
- 哪些元素发生异常；
- 异常位于哪一页、哪个区域；
- 异常严重程度及其是否影响交付。

系统名称可定位为 **Document Visual Fidelity QA Engine**。

## 2. 核心原则

1. **结构优先**：优先解析 PDF、DOCX、PPTX 的原生结构，再结合页面渲染图。
2. **统一模型**：不同格式统一转换为 `Page / Block / Region / Issue`。
3. **确定性检测为底座**：布局、边界框、字体、间距、对象数量和表格结构由算法与规则检测。
4. **多模态模型负责复核**：视觉模型接收页面图、结构化差异和已有问题，负责发现遗漏、识别误报及补充观察。
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

| 检测层 | 关注内容 | 典型问题 |
| --- | --- | --- |
| Layout QA | 位置、尺寸、间距、对齐、重叠、越界 | `REGION_SHIFTED`、`CONTENT_OUT_OF_PAGE` |
| Typography QA | 字号、字重、颜色、对齐、行高、字体兼容性 | `FONT_SHRINK`、`TYPOGRAPHY_CHANGED` |
| Text Flow QA | 换行、行数、溢出、裁切、文本重叠 | `TEXT_OVERFLOW`、`TEXT_CLIPPED` |
| Object QA | 图片、Logo、图表等对象的数量与相似度 | `MISSING_IMAGE`、`MISSING_ELEMENT` |
| Table QA | 行列、合并单元格、边框、单元格布局 | `TABLE_STRUCTURE_CHANGED` |

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

## 8. MVP 建议

第一阶段只支持 PDF，形成最短闭环：

```text
PDF 解析
→ Page / Block 标准化
→ Region 分组与对齐
→ Overflow / Overlap / Missing Element 检测
→ JSON 报告
```

后续再增加 DOCX、PPTX、表格专项检测、图片 Embedding、多模态复核和可视化报告。

