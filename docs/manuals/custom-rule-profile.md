# 自定义 JSON Rule Profile 配置手册

## 1. 手册用途

本文说明如何创建、修改、校验和使用 Structured Visual QA 的自定义 JSON Rule Profile。

Rule Profile 用于统一配置：

- Source/Target Region 的匹配权重；
- Region 最低匹配分数和跨语言文本合并容错；
- 各检测器是否启用；
- 偏移、字号缩小和重叠等检测阈值；
- Severity 扣分、Issue 页内扣分上限；
- `PASS / REVIEW / FAIL` 状态规则。

配置文件不会修改 Python 代码。每次 QA 任务都会把 Profile 版本引用和完整快照写入报告，因此旧任务可以复现。

## 2. 快速开始

以下命令均在项目根目录执行：

```bash
cd /path/to/structured-visual-qa
```

### 2.1 导出默认配置

```bash
uv run document-qa \
  --export-default-profile profiles/translation-balanced.v1.json
```

命令会自动创建 `profiles/` 目录并生成经过真实中英文 PDF 校准的默认配置。

### 2.2 复制为自定义配置

不要直接覆盖已经发布或已经用于生产任务的配置。复制为新文件，然后修改身份信息和版本：

```bash
cp profiles/translation-balanced.v1.json \
  profiles/translation-strict.v1.json
```

建议修改：

```json
{
  "profile_id": "translation-strict",
  "name": "翻译 PDF 严格模式",
  "version": 1,
  "status": "draft",
  "description": "适用于正式交付前的严格检查。"
}
```

这里只展示需要修改的字段。实际配置必须保留完整 JSON 结构。

### 2.3 使用自定义配置运行

```bash
uv run document-qa \
  source.pdf \
  target.pdf \
  --profile profiles/translation-strict.v1.json \
  --output artifacts/strict-report.json \
  --render-dir artifacts/pages
```

终端示例：

```text
状态=review 分数=91.80 报告=/.../artifacts/strict-report.json
```

报告包含：

```json
{
  "rule_profile_reference": "translation-strict@1",
  "rule_profile_snapshot": {}
}
```

## 3. 精简可加载示例

下面示例依赖 Pydantic 默认值补齐未列字段，适合讲解结构，不是当前 Schema 的完整
字段清单。需要创建完整配置时必须执行 §2.1 的导出命令；需要工具生成表单或校验
字段时使用 §10.1 的 JSON Schema。不要从本节复制后假设遗漏字段不存在。

```json
{
  "schema_version": 1,
  "profile_id": "translation-balanced",
  "name": "翻译 PDF 平衡模式",
  "version": 1,
  "status": "published",
  "description": "适用于机器生成型双语 PDF 的默认平衡配置。",
  "matching": {
    "minimum_score": 0.45,
    "merged_text_coverage_ratio": 0.4,
    "text_type_similarity": 0.8,
    "weights": {
      "position": 0.4,
      "size": 0.25,
      "type": 0.2,
      "order": 0.15
    },
    "logical_grouping": {
      "enabled": true,
      "max_regions": 8,
      "line_gap_ratio": 0.6,
      "horizontal_overlap_ratio": 0.3,
      "font_size_tolerance_ratio": 0.15,
      "edge_tolerance_ratio": 0.015,
      "negative_overlap_ratio": 0.25,
      "counterpart_overlap_ratio": 0.5
    }
  },
  "alignment": {
    "enabled": true,
    "max_shift": 3,
    "skip_penalty": 0.5,
    "shift_margin": 0.01
  },
  "grouping": {
    "heading_ratio": 1.25,
    "disconnected_span_gap_ratio": 3.0,
    "style_font_size_tolerance_ratio": 0.03,
    "style_font_size_tolerance_points": 0.25
  },
  "detectors": {
    "enabled": {
      "missing_element": true,
      "region_shifted": true,
      "font_shrink": true,
      "content_out_of_page": true,
      "overlap": true,
      "number_mismatch": true,
      "untranslated_text": true,
      "untranslated_raster_ocr": true,
      "text_rasterized": true
    },
    "thresholds": {
      "shifted_ratio": 0.05,
      "severely_shifted_ratio": 0.15,
      "font_shrink_ratio": -0.2,
      "overlap_ratio": 0.05,
      "overlap_increase_ratio": 0.05,
      "text_overlap_axis_ratio": 0.1,
      "image_caption_area_ratio": 0.005,
      "untranslated_ratio": 0.7,
      "untranslated_min_letters": 8,
      "conversion_noise_ratio": 0.03,
      "text_reflow_max_added_lines": 1,
      "text_reflow_width_tolerance_ratio": 0.25,
      "text_reflow_font_tolerance_ratio": 0.2,
      "text_reflow_line_height_tolerance_ratio": 0.6
    },
    "layout_analog_weights": {
      "position": 0.7,
      "size": 0.3
    },
    "severity_overrides": {
      "text_rasterized": "high"
    }
  },
  "scoring": {
    "pass_score": 90.0,
    "fail_score": 75.0,
    "critical_forces_fail": true,
    "high_forces_review": true,
    "severity_deductions": {
      "info": 0.0,
      "low": 1.0,
      "medium": 4.0,
      "high": 10.0,
      "critical": 25.0
    },
    "issue_type_deduction_caps": {
      "region_shifted": 12.0,
      "text_overflow": 25.0,
      "text_clipped": 25.0,
      "abnormal_wrap": 10.0,
      "line_count_explosion": 10.0,
      "font_shrink": 10.0,
      "text_overlap": 10.0,
      "text_image_overlap": 25.0,
      "content_out_of_page": 25.0,
      "missing_element": 10.0,
      "added_element": 3.0,
      "missing_image": 25.0,
      "typography_changed": 10.0,
      "table_structure_changed": 25.0,
      "page_missing": 25.0,
      "number_mismatch": 12.0,
      "untranslated_text": 12.0,
      "glossary_violation": 12.0,
      "other": 10.0
    }
  }
}
```

## 4. 顶层字段

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | integer | `>= 1` | Profile JSON 结构版本，当前为 `1` |
| `profile_id` | string | 2～64 字符 | 稳定 ID，只允许小写字母、数字和连字符 |
| `name` | string | 1～100 字符 | 人类可读名称，允许中文 |
| `version` | integer | `>= 1` | 当前 Profile 业务版本 |
| `status` | enum | 见下表 | 生命周期状态 |
| `description` | string | 无特殊限制 | 使用场景和变更说明 |
| `language` | string | `auto` 或脚本对标识 | 翻译场景标识，见下方"语言场景"说明 |
| `language_overrides` | object | 可选 | 按语言场景覆盖 `detectors` 配置，见下方说明 |
| `matching` | object | 必填 | Region 匹配配置 |
| `alignment` | object | 必填 | 跨页对齐配置 |
| `grouping` | object | 必填 | Block→Region 分组配置 |
| `detectors` | object | 必填 | 检测器开关与阈值 |
| `scoring` | object | 必填 | 评分和状态规则 |

### 4.1 语言场景（`language` 与 `language_overrides`）

不同目标语言的排版与数字书写习惯不同（如阿拉伯语使用阿拉伯-印度数字 ٠-٩、
从右向左书写），引擎内置的脚本自适应会自动归一这些差异；当某语言场景确实
需要不同阈值或检测开关时，通过 `language_overrides` 覆盖，无需另建完整 Profile：

- `language` 默认为 `auto`：由引擎按文档内容推断"源脚本-目标脚本"标识
  （如英文→中文为 `latin-cjk`，英文→阿拉伯语为 `latin-arabic`）；
  也可显式声明固定值；
- `language_overrides` 的键为场景标识，值为一份完整的 `detectors` 配置；
  未命中的场景沿用全局 `detectors`；
- 支持的脚本名：`latin`、`cjk`、`arabic`、`hebrew`、`cyrillic`、`greek`、
  `devanagari`、`bengali`、`thai`、`hangul`、`kana`。

```json
{
  "language": "auto",
  "language_overrides": {
    "latin-arabic": {
      "enabled": { "number_mismatch": false },
      "thresholds": { "untranslated_ratio": 0.8 }
    }
  }
}
```

`status` 允许：

| 值 | 含义 |
| --- | --- |
| `draft` | 草稿，可继续修改，不建议用于稳定生产任务 |
| `published` | 已发布，应视为不可变配置 |
| `archived` | 已归档，不再用于新任务，但旧报告仍可复现 |

Profile 的稳定引用格式为：

```text
{profile_id}@{version}
```

例如：

```text
translation-strict@2
```

## 5. Matching 配置

### 5.1 `minimum_score`

```json
"minimum_score": 0.45
```

取值范围为 `0～1`。Source Region 与 Target Region 的综合匹配分低于该值时，系统不会接受这组匹配，而会进入缺失/新增元素检查。

- 降低：匹配更宽松，减少未匹配元素，但可能产生错误匹配；
- 提高：匹配更严格，错误匹配减少，但缺失/新增误报可能增加；
- 推荐调节范围：`0.40～0.60`；
- 每次变更必须运行真实双语样本回归。

### 5.2 `merged_text_coverage_ratio`

```json
"merged_text_coverage_ratio": 0.4
```

取值范围为 `0～1`。英文 PDF 可能把正文拆成多个文本框，而中文 PDF 将同一区域合并成一个文本框。未匹配源文本被目标文本覆盖达到此比例时，系统将其视为多对一文本合并，而不是元素缺失。

- 降低：更容易认定为正常合并，减少 `missing_element`；
- 提高：要求版面覆盖更准确，缺失检测更严格；
- 推荐调节范围：`0.35～0.60`。

### 5.3 Matching 权重

```json
"weights": {
  "position": 0.4,
  "size": 0.25,
  "type": 0.2,
  "order": 0.15
}
```

综合匹配分：

```text
match_score =
    position × position_similarity
  + size     × size_similarity
  + type     × type_similarity
  + order    × order_similarity
```

| 权重 | 作用 | 提高后的影响 |
| --- | --- | --- |
| `position` | 页面位置相似度 | 更偏向匹配相同位置的元素 |
| `size` | Region 宽高相似度 | 更偏向匹配尺寸相似的元素 |
| `type` | Heading/Paragraph/Image 类型 | 更严格区分文本、图片和标题 |
| `order` | 阅读顺序 | 更偏向相同页面顺序 |

四项必须满足：

```text
position + size + type + order = 1.0
```

允许浮点误差不超过 `0.000001`。不能只修改一个权重而不重新平衡其他权重。

## 6. Detector 开关

```json
"enabled": {
  "missing_element": true,
  "region_shifted": true,
  "font_shrink": true,
  "content_out_of_page": true,
  "overlap": true,
  "number_mismatch": true,
  "untranslated_text": true,
  "untranslated_raster_ocr": true,
  "text_rasterized": true
}
```

| 字段 | 控制的检测 |
| --- | --- |
| `missing_element` | 缺失元素、缺失图片和目标新增元素 |
| `region_shifted` | 匹配 Region 的位置偏移 |
| `font_shrink` | 目标字号明显缩小 |
| `content_out_of_page` | Region 超出页面边界 |
| `overlap` | 新增文字重叠、文字图片重叠 |
| `number_mismatch` | 页面数字集合不一致（数字错漏译） |
| `untranslated_text` | 目标文本区仍保留源语言文字（漏译） |
| `untranslated_raster_ocr` | 使用已注入 OCR Provider 检查大图片候选区内的源语言残留 |
| `region_resized` | 匹配 Region 宽/高剧变（段落被合并或拆散） |
| `text_fragmented` | 目标文字被竖排/拆散成字母碎片（窄列排版破坏） |
| `font_grow` | 目标字号明显放大（换行爆炸前兆） |
| `invisible_text` | 目标文字颜色与页面背景同色（视觉不可见） |
| `text_rasterized` | 透明译文文本层与同位置图片组成的局部文字栅格化 |
| `text_alignment_changed` | 段落水平对齐方式变化（如右对齐变左对齐） |

关闭检测器意味着对应 Issue 不再产生，也不参与扣分和状态判定。建议只在明确不适用时关闭，不要通过关闭检测器掩盖阈值问题。

## 7. Detector 阈值

### 7.1 位置偏移

```json
"shifted_ratio": 0.05,
"severely_shifted_ratio": 0.15
```

偏移量以页面宽度或高度归一化：

```text
shift = max(abs(x_shift_ratio), abs(y_shift_ratio))
```

- `shift > shifted_ratio`：产生 `MEDIUM REGION_SHIFTED`；
- `shift > severely_shifted_ratio`：产生 `HIGH REGION_SHIFTED`。

必须满足：

```text
0 <= shifted_ratio < severely_shifted_ratio <= 1
```

数值 `0.05` 表示页面尺寸的 5%，不是 5 个 PDF point。

### 7.2 字号缩小

```json
"font_shrink_ratio": -0.2
```

计算公式：

```text
(target_font_size - source_font_size) / source_font_size
```

`-0.2` 表示目标字号比源字号缩小超过 20% 时进入检测；默认分档下 20%～40%
产生 `MEDIUM FONT_SHRINK`，达到 40% 后为 `HIGH`。

取值必须位于 `-1～0`：

- 越接近 `0`：越严格，例如 `-0.10`；
- 越接近 `-1`：越宽松，例如 `-0.40`。

单独的字号缩小不会产生 Critical；如果同时发生裁切或越界，对应检测器会生成 Critical。

### 7.3 重叠比例

```json
"overlap_ratio": 0.05,
"overlap_increase_ratio": 0.05,
"text_overlap_axis_ratio": 0.1
```

`overlap_ratio` 是两个 Region 交集面积占较小 Region 面积的比例。低于该值的轻微接触被忽略。

`overlap_increase_ratio` 比较 Target 与 Source 的重叠关系。只有 Target 重叠相对 Source 明显增加时才报告，避免把封面背景图叠字等原设计判为异常。

`text_overlap_axis_ratio` 要求两个文本 BBox 在水平和垂直方向的侵入比例都超过
该值，排除相邻行或相邻列因字体上延、下延产生的轻微边界接触。

三者取值范围均为 `0～1`。

### 7.4 严重度分档（bands）

数字不一致、字号缩小与漏译三类检测支持按幅度分档严重度：轻微幅度 `MEDIUM`、
严重幅度 `HIGH`，替代以往所有命中一律 HIGH 的扁平判定。

```json
"number_mismatch_bands": [
  { "gte": 5, "severity": "high" },
  { "gte": 1, "severity": "medium" }
],
"font_shrink_bands": [
  { "gte": 0.4, "severity": "high" },
  { "gte": 0.2, "severity": "medium" }
],
"untranslated_bands": [
  { "gte": 0.9, "severity": "high" },
  { "gte": 0.7, "severity": "medium" }
]
```

各分档的指标定义：

| 字段 | 指标 | 缺省分档 |
| --- | --- | --- |
| `number_mismatch_bands` | 页面差异数字总数（缺失 + 多余） | ≥5 → HIGH；1～4 → MEDIUM |
| `font_shrink_bands` | 字号缩小幅度（正数，0.4 = 40%） | ≥0.4 → HIGH；0.2～0.4 → MEDIUM |
| `untranslated_bands` | 目标区域中源脚本字母占比 | ≥0.9 → HIGH；阈值～0.9 → MEDIUM |

规则：

- `gte` 为命中下界（指标 ≥ gte 命中该档），多档命中时取 `gte` 最大的一档；
- 基础阈值（如 `font_shrink_ratio`）仍先行把关是否算问题，分档只决定严重度；
- 分档列表为空时退回该检测器缺省严重度（HIGH），等价于旧行为。

### 7.5 图片 Caption 面积

```json
"image_caption_area_ratio": 0.005
```

文字 Region 面积不超过页面面积的 0.5% 时，系统将图片边缘的版权署名、来源和小型 Caption 排除出文字图片重叠检测。

- 降低：更多小文字参与重叠检查，检测更严格；
- 提高：更多小文字被视为 Caption；
- 建议不要高于 `0.01`，否则可能忽略小型正文标签。

### 7.6 未翻译文本判定

```json
"untranslated_ratio": 0.7,
"untranslated_min_letters": 8
```

内容级检测器会先判定页面主导语言，再检查目标文本区是否仍大量保留源语言文字：

- `untranslated_ratio`：目标文本中源语言字符占比达到该值即判为漏译（`HIGH UNTRANSLATED_TEXT`）；
- `untranslated_min_letters`：目标文本字母数少于该值的短文本（版权行、机构缩写等）不参与判定。

源码同文、源语言无法判定或源页面本身中英混排时，该检测整体跳过。

### 7.7 LibreOffice 归一化噪声容差

```json
"conversion_noise_ratio": 0.03
```

当输入为 Word/PPT/Excel 等 Office 格式时，系统先经 LibreOffice 归一化为 PDF。归一化会引入约 1–3% 的版面转换噪声，该容差会**自动叠加**到偏移类阈值（`shifted_ratio`/`severely_shifted_ratio`）上，纯 PDF 流水线不受影响。报告 `metadata.normalized_from` 会标记转换来源。

### 7.8 段落对齐方式推断

系统先按栏位、行距、字号和水平重叠把相邻文本行聚成临时段落流，再比较左边缘、右边缘和中心线的稳定性，推断 `left/right/center`。主要阈值如下：

| 字段 | 默认值 | 作用 |
| --- | ---: | --- |
| `alignment_min_lines` | 3 | 少于该行数不推断对齐方式 |
| `alignment_line_gap_ratio` | 0.6 | 相邻行最大间距，相对行高归一化 |
| `alignment_horizontal_overlap_ratio` | 0.3 | 相邻行最小水平重叠比例 |
| `alignment_font_size_tolerance_ratio` | 0.15 | 同一文本流允许的字号差异 |
| `alignment_edge_tolerance_ratio` | 0.015 | 稳定边缘允许的页面宽度误差 |
| `alignment_confidence_margin` | 0.01 | 最优对齐特征相对次优特征的最小优势 |
| `alignment_group_match_ratio` | 0.6 | 源文本流配对到同一目标文本流的最小多数比例 |

命中对齐变化后，系统输出 `HIGH TEXT_ALIGNMENT_CHANGED`，并抑制同一段落内由换行和对齐变化产生的重复行级 `REGION_SHIFTED/REGION_RESIZED`。

### 7.9 透明文字与图片栅格化

```json
"invisible_opacity_threshold": 0.01,
"rasterized_image_overlap_ratio": 0.8
```

- `invisible_opacity_threshold`：PDF 文本 alpha 归一化后不高于该值，视为视觉不可见；
- `rasterized_image_overlap_ratio`：已匹配透明译文文本与未匹配目标图片的重叠比例达到该值时，合并为 `text_rasterized`；
- 命中后抑制同一图片的 `added_element`、同一透明文本的 `invisible_text` 以及两者的重叠问题。

### 7.10 图像文字与候选区 OCR

`untranslated_raster_*` 控制无 OCR 的图像字形簇检测；
`untranslated_raster_ocr_*` 控制大图片候选数量、渲染 DPI、置信度、字符数和源脚本
残留比例。完整字段较多，必须以导出的默认 Profile 为准。OCR 开关打开并不等于
core 会自行加载模型：只有 server 配置 `DQA_OCR_ENABLED=true` 并成功构造 Provider
时才执行 OCR；未安装 extra 或模型失败时保留确定性检测并记录降级状态。

### 7.11 其他布局抑制阈值

- `invisible_dark_background_overlap_ratio`：浅色文字与深色块重叠达到该比例时，
  视为正常反白设计；
- `alignment_negative_overlap_ratio`：对齐文本流允许的最大负行距比例；
- `matching.logical_grouping.negative_overlap_ratio`：逻辑分组允许的最大负行距比例。

这些值与其他检测阈值一样必须由 `RuleProfile` 持有，不得在检测器中写裸常量。

## 8. Scoring 配置

### 8.1 状态分数线

```json
"pass_score": 90.0,
"fail_score": 75.0
```

必须满足：

```text
0 <= fail_score < pass_score <= 100
```

默认状态规则：

```text
Critical 存在或 Score < 75 → FAIL
High 存在或 Score < 90     → REVIEW
其他                        → PASS
```

### 8.2 状态覆盖开关

```json
"critical_forces_fail": true,
"high_forces_review": true
```

- `critical_forces_fail=true`：即使分数很高，只要存在 Critical 仍为 FAIL；
- `high_forces_review=true`：即使分数不低于 PASS 线，只要存在 High 仍为 REVIEW。

正式交付配置建议保持两项为 `true`。

### 8.3 Severity 单次扣分

```json
"severity_deductions": {
  "info": 0.0,
  "low": 1.0,
  "medium": 4.0,
  "high": 10.0,
  "critical": 25.0
}
```

五个键必须全部存在，扣分不能为负数。

页面基础分为 100。系统先按 Severity 累加同类 Issue 扣分，再应用 IssueType 页内扣分上限。

### 8.4 IssueType 页内扣分上限

例如：

```json
"font_shrink": 10.0
```

即使一页图表中出现 12 个 `HIGH FONT_SHRINK`，报告仍保留 12 条 Issue，但该类型最多扣 10 分。这避免 PDF 把一个视觉对象拆成大量小 Region 后重复扣分。

所有 IssueType 必须完整配置：

| IssueType | 当前是否已有检测器 | 默认上限 |
| --- | ---: | ---: |
| `region_shifted` | 是 | 12 |
| `text_overflow` | 否 | 25 |
| `text_clipped` | 否 | 25 |
| `abnormal_wrap` | 否 | 10 |
| `line_count_explosion` | 否 | 10 |
| `font_shrink` | 是 | 10 |
| `text_overlap` | 是 | 10 |
| `text_image_overlap` | 是 | 25 |
| `content_out_of_page` | 是 | 25 |
| `missing_element` | 是 | 10 |
| `added_element` | 是 | 3 |
| `missing_image` | 是 | 25 |
| `typography_changed` | 否 | 10 |
| `table_structure_changed` | 否 | 25 |
| `page_missing` | 是 | 25 |
| `number_mismatch` | 是 | 12 |
| `untranslated_text` | 是 | 12 |
| `glossary_violation` | 是 | 12 |
| `invisible_text` | 是 | 25 |
| `text_rasterized` | 是 | 10 |
| `text_vectorized` | 是 | 0 |
| `text_alignment_changed` | 是 | 10 |
| `other` | 预留 | 10 |

“尚无检测器”表示当前不会自动产生该 Issue，但配置键仍须保留，以保证未来增加检测器时旧 Profile 的评分行为明确。

## 9. 常用配置方案

以下片段只展示需要变化的字段。创建配置时应先导出完整默认 JSON，再修改相应字段。

### 9.1 正式交付严格模式

适合最终交付前检查：

```json
{
  "profile_id": "translation-strict",
  "name": "翻译 PDF 严格模式",
  "status": "draft",
  "matching": {
    "minimum_score": 0.5
  },
  "detectors": {
    "thresholds": {
      "shifted_ratio": 0.03,
      "severely_shifted_ratio": 0.1,
      "font_shrink_ratio": -0.15,
      "overlap_ratio": 0.03,
      "overlap_increase_ratio": 0.03
    }
  },
  "scoring": {
    "pass_score": 95.0,
    "fail_score": 80.0
  }
}
```

注意：实际文件不能只保留这个片段，必须保留完整字段。

### 9.2 早期宽松预检模式

适合翻译流程早期快速发现明显问题：

```json
{
  "profile_id": "translation-preflight",
  "name": "翻译 PDF 宽松预检",
  "detectors": {
    "thresholds": {
      "shifted_ratio": 0.08,
      "severely_shifted_ratio": 0.2,
      "font_shrink_ratio": -0.3,
      "overlap_ratio": 0.1,
      "overlap_increase_ratio": 0.1
    }
  },
  "scoring": {
    "pass_score": 85.0,
    "fail_score": 65.0
  }
}
```

即使宽松预检，也建议保留页面缺失、图片缺失和越界检测。

### 9.3 只检查致命布局问题

```json
"enabled": {
  "missing_element": true,
  "region_shifted": false,
  "font_shrink": false,
  "content_out_of_page": true,
  "overlap": true
}
```

这会减少噪声，但不会产生普通偏移和字号变化问题。

## 10. 配置校验

当前 CLI 在加载 `--profile` 时自动执行完整 Pydantic 校验。要单独验证配置而不处理文档，可以使用 Python：

```bash
uv run python -c '
from pathlib import Path
from document_qa.profiles import RuleProfileStore
profile = RuleProfileStore.load(Path("profiles/translation-strict.v1.json"))
print(profile.reference)
'
```

成功输出示例：

```text
translation-strict@1
```

当前 CLI 在加载时校验，Web 配置界面通过 `/api/profile/schema` 获取 Schema，并在
`/api/profile/save` 保存边界再次执行服务端校验。尚未提供独立的 `/validate` 路由。

### 10.1 导出 JSON Schema

```bash
uv run document-qa \
  --export-profile-schema profiles/rule-profile.schema.json
```

JSON Schema 可用于：

- IDE 自动补全；
- React 动态表单；
- 浏览器端初步校验；
- 配置中心字段定义。

服务端 Pydantic 校验仍是最终判定，前端校验不能替代它。

## 11. 常见错误

### 11.1 匹配权重总和不为 1

错误：

```json
"weights": {
  "position": 0.5,
  "size": 0.3,
  "type": 0.2,
  "order": 0.1
}
```

总和为 1.1，加载时会出现：

```text
匹配权重总和必须等于 1
```

### 11.2 严重偏移阈值小于普通阈值

错误：

```json
"shifted_ratio": 0.2,
"severely_shifted_ratio": 0.1
```

会出现：

```text
严重偏移阈值必须大于普通偏移阈值
```

### 11.3 FAIL 分数线高于 PASS

错误：

```json
"pass_score": 80,
"fail_score": 90
```

会出现：

```text
FAIL 分数线必须低于 PASS 分数线
```

### 11.4 通过删除 IssueType 上限来关闭检测

旧 Profile 缺少后来新增的 IssueType 上限时，加载边界会从默认配置补齐，以保持历史
兼容；删除某个上限不会关闭检测器。需要关闭能力时使用 `detectors.enabled`，需要
调整扣分时显式设置非负上限。最终通过校验的 Profile 必须覆盖全部 IssueType。

### 11.5 使用百分数 5 代替比例 0.05

所有 `ratio` 字段都使用 `0～1` 的比例：

```text
5%  → 0.05
20% → 0.20
```

写成 `5` 会超出允许范围。

### 11.6 添加自定义未知字段

Profile 使用严格 Schema。拼写错误或未支持字段会被拒绝，例如：

```json
"min_score": 0.5
```

正确字段是：

```json
"minimum_score": 0.5
```

## 12. 版本管理

### 12.1 不覆盖已发布版本

当 `status=published` 的配置已经用于任务时，不应修改原文件。创建下一版本：

```text
translation-strict.v1.json
translation-strict.v2.json
```

并更新 JSON：

```json
"version": 2
```

### 12.2 推荐生命周期

```text
draft → 样本验证 → published → archived
```

### 12.3 变更记录

建议在 `description` 中记录变更目的：

```json
"description": "v2：将普通偏移阈值由 5% 调整为 4%，用于正式合同文档。"
```

后续配置中心应保存独立的 Changelog，而不是完全依赖描述字段。

## 13. 调整阈值的正确流程

不要根据单份报告直接反复调参。推荐流程：

1. 收集 Source/Target 真实 PDF；
2. 人工标注正常页面与问题页面；
3. 使用当前 Profile 生成基线报告；
4. 统计误报和漏报；
5. 每次只修改一个指标或一组强相关指标；
6. 使用同一批样本重新运行；
7. 比较 `PASS / REVIEW / FAIL`、Issue 数量和人工标签；
8. 运行全部自动测试；
9. 创建新版本并发布。

运行测试：

```bash
uv run python -m unittest discover -s tests -v
```

运行真实样本：

```bash
uv run document-qa \
  source.pdf target.pdf \
  --profile profiles/translation-strict.v2.json \
  --output artifacts/calibration-report.json
```

## 14. 安全注意事项

- Profile JSON 不能包含 API Key、令牌、密码或文档正文；
- `profile_id` 不是文件路径；
- API 不接受客户端指定服务器保存路径；
- 生产环境应限制 Profile JSON 大小；
- 服务端必须重新执行 Pydantic 校验；
- 发布配置前必须运行 Golden Sample；
- 配置文件应纳入版本控制，但真实 PDF 和 QA 中间产物不应提交。

## 15. 当前限制

- CLI 尚无单独的 `validate-profile` 子命令，加载 Profile 时会自动校验；
- Profile 已保存到 SQLite 版本表；Web 配置界面已落地（`/api/profile/*` 路由 + frontend 的 ProfileEditor / ProfileManager）；
- Profile 版本号由配置 JSON 的 `version` 字段维护，尚未由服务端自动递增；
- 修改配置不会创建自动 Changelog；
- 新增检测指标仍需要先修改代码和 RuleProfile Schema，然后才能在 JSON 中配置。

FastAPI 与 React 界面已经复用当前 `RuleProfile` 和导出的 JSON Schema；新增字段时
仍需同步检查字段说明、表单展示和旧 Profile 兼容补齐逻辑。
