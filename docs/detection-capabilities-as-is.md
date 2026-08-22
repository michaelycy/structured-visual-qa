# 当前问题识别能力（AS-IS）

## 文档状态

- 范围：当前系统能够实际生成的文档质量问题及其判别方式
- 分析基线：`master` / `c1d0dd0` + 当前工作树中的“文字已转曲”未提交实现
- 分析日期：2026-08-21
- 证据状态：本文主表全部为 **Verified（已验证）**，依据可达实现与现有测试
- 不包含：待办中的像素层检测、OCR、翻译语义正确性判断、复杂表格结构恢复

## 判别链路

系统不是直接比较两张页面截图，而是先建立可解释的结构化对应关系：

1. 解析源文档和目标文档，提取页面、文本 Span、图片、样式与 BBox。
2. 将 Block 组合成 Region，Region 是匹配和检测的基本单元。
3. 使用页面版面相似度和动态规划做跨页单调对齐；默认最多容忍 3 页移位。
4. 对已对齐页面的 Region 计算位置、尺寸、类型、顺序相似度，并用全局最优分配建立一对一匹配。
5. 匹配分数默认低于 0.45 时不接受配对，进入缺失/新增元素判定。
6. 在匹配结果上依次执行布局、内容、术语规则，统一输出 `Issue`。
7. 按严重度扣分，并由 Critical/High 问题覆盖单纯的分数判定。

区域匹配默认权重为：位置 40%、尺寸 25%、类型 20%、顺序 15%。证据：
`core/src/document_qa/profiles.py:23-48`、
`core/src/document_qa/matching/region_matcher.py:46-104`。

## 可识别问题总表

> 默认阈值均可通过版本化 `RuleProfile` 调整。表中的“源/目标”分别指原文文档与译文文档。

当前可达实现覆盖 **19 个问题场景、18 个实际 Issue 类型**；“额外页面”和“新增 Region”共用 `added_element`，但判别路径和严重度不同，因此分别列出。

| 分类 | 可识别问题 | Issue 类型 | 默认判别方式 | 默认严重度 | 前提与边界 | 主要证据 |
| --- | --- | --- | --- | --- | --- | --- |
| 页面完整性 | 目标缺少整页 | `page_missing` | 页面动态规划对齐后，源页面没有目标配对页 | Critical | 跨页对齐默认只在页码差不超过 3 的窗口中搜索 | `pipeline.py:216-228`；`page_aligner.py:34-70` |
| 页面完整性 | 目标出现额外页面 | `added_element` | 页面对齐后，目标页面没有源配对页 | High | 与“新增 Region”共用 Issue 类型，通过 `detector=page-alignment` 和描述区分 | `pipeline.py:201-214` |
| 元素完整性 | 文本或一般区域缺失 | `missing_element` | 源 Region 未获得分数不低于 0.45 的目标匹配 | High | 若未匹配源文本被目标文本覆盖至少 40%，视为多对一合并承载，不报缺失 | `rules.py:60-117`；`region_matcher.py:69-104` |
| 元素完整性 | 图片缺失 | `missing_image` | 源图片 Region 未获得有效目标匹配 | Critical | 当前判断的是图片对象/区域是否缺失，不比较图片内部内容是否被替换 | `rules.py:68-90` |
| 元素完整性 | 目标新增区域 | `added_element` | 目标 Region 未获得有效源匹配 | Low | 合理新增内容也可能命中，需要人工复核 | `rules.py:92-106` |
| 几何布局 | Region 显著偏移 | `region_shifted` | 取 X/Y 相对页面尺寸的位移比例最大值；大于 5% 报告，大于 15% 升级 | 5%～15%：Medium；>15%：High | Office 经 LibreOffice 归一化时，服务层默认为两档阈值各增加 3% 转换噪声容差 | `rules.py:119-153`；`profiles.py:155-167`；`compare_service.py:173-189` |
| 几何布局 | Region 尺寸剧变 | `region_resized` | 宽度或高度变化比例的绝对值最大值大于 50% | >50% 且 <80%：Medium；≥80%：High | 用于捕获段落合并、拆散等几何异常；不直接判断文本语义 | `rules.py:207-234`；`profiles.py:143-149,180-187` |
| 字体排版 | 字号明显缩小 | `font_shrink` | 匹配 Region 字号相对源字号缩小超过 20% | >20% 且 <40%：Medium；≥40%：High | 只有双方都能提取有效字号时才判断 | `rules.py:155-183`；`profiles.py:125-131,157` |
| 字体排版 | 字号明显放大 | `typography_changed` | 匹配 Region 字号相对源字号放大超过 25% | Medium | 作为换行或排版恶化前兆；目前不单独判定字体族、粗细等变化 | `rules.py:185-205`；`profiles.py:186-187` |
| 字体排版 | 文字竖排或碎片化 | `text_fragmented` | 目标文本 Region 宽度不超过 18 pt，且字母数不超过 3 | Medium | 纯数字/符号不参与；针对缩写被拆成单字母窄列的典型破坏 | `rules.py:237-297`；`profiles.py:188-191` |
| 字体排版 | 段落水平对齐方式变化 | `text_alignment_changed` | 将相邻文字行聚成临时文本流；根据左右边缘和中心线稳定性推断对齐方式，源/目标不同则报告 | High | 默认至少 3 行；同一段落内的重复行级偏移/缩放被抑制 | `alignment.py`；`rules.py`；`profiles.py` |
| 可见性 | 浅色背景上的同色文字 | `invisible_text` | 页面背景为浅色，Region 内全部文本颜色也接近浅色；RGB 最低通道默认均不低于 235 | High | 深色页面、文字覆盖深色块/图片达到 30%、或任一文字 Block 为深色时跳过 | `rules.py:299-402`；`profiles.py:192-195` |
| 页面边界 | 内容超出页面 | `content_out_of_page` | 目标 Region 的左/上坐标小于 0，或右/下边界超过页面宽高 | Critical | 基于结构 BBox；只能说明可能被裁切，不做最终像素可见性判断 | `rules.py:417-445` |
| 重叠 | 文本与文本新增重叠 | `text_overlap` | 目标两文本 Region 重叠比例超过 5%，且相对源版面类比的重叠增量超过 5% | High | 只报翻译后新增或显著加剧的重叠，尽量保留源版已有设计 | `rules.py:447-539`；`profiles.py:158-160` |
| 重叠 | 文本侵入图片 | `text_image_overlap` | 文本与图片重叠超过阈值、文字中心新进入图片，且重叠相对源版明显增加 | Critical | 页面面积不超过 0.5% 的小型图片署名/脚注跳过；源版已有图上文字跳过 | `rules.py:463-537`；`profiles.py:158-160` |
| 内容一致性 | 数字缺失、增加或错写 | `number_mismatch` | 分别抽取整页数字，归一化千分位、全角数字、阿拉伯-印度数字和前导零，然后比较多重集合 | 差异 1～4 个：Medium；≥5 个：High | 页面级守恒，不要求数字留在同一 Region；不理解数字的业务语义或单位换算 | `content.py:15-58,106-176`；`profiles.py:116-122` |
| 翻译完整性 | 疑似整段/大段漏译 | `untranslated_text` | 判断源页面主导脚本；目标匹配文本中源脚本字母占比达到 70% | ≥70% 且 <90%：Medium；≥90%：High | 少于 8 个字母、全大写缩写、同脚本文档、无法判断主脚本或源页混排时跳过 | `content.py:213-298`；`profiles.py:134-140,161-164` |
| 术语规范 | 未使用术语库允许译法 | `glossary_violation` | 源匹配 Region 命中术语，但目标 Region 未命中任一允许译法 | High | 仅在任务配置术语库时启用；拉丁术语按词边界匹配，纯 CJK 术语按子串匹配 | `glossary.py:26-46,70-134`；`pipeline.py:275-279` |
| 文本层状态 | 目标页面文字已转曲/矢量化 | `text_vectorized` | 源页文本字符数至少 30，目标页字符数不超过源页的 10% | Info，不扣分 | 命中后抑制该页文本缺失、数字、漏译和术语检测；布局与图片检测继续。该能力位于当前未提交工作树 | `pipeline.py:166-188,234-279`；`profiles.py:196-200,276` |
| 文本层状态 | 局部文字被栅格化 | `text_rasterized` | 源文本匹配到目标透明文本层，且同位置存在重叠比例至少 80% 的未匹配图片 | High | 合并透明文本层与可见图片证据，并抑制同一结构产生的新增、隐形和重叠重复问题 | `pymupdf_parser.py`；`rules.py`；`profiles.py` |

## 评分与文档状态

### 页面分数

每页从 100 分开始，按 Issue 严重度累计扣分：

| 严重度 | 单条默认扣分 |
| --- | ---: |
| Info | 0 |
| Low | 1 |
| Medium | 4 |
| High | 10 |
| Critical | 25 |

同一 Issue 类型设置页内扣分上限，避免一个视觉缺陷因解析成多个 Region 而重复扣分到 0。证据：
`core/src/document_qa/profiles.py:237-279`、
`core/src/document_qa/scoring/scorer.py:17-32`。

### 状态规则

| 状态 | 判定方式 |
| --- | --- |
| `PASS` | 没有 Critical/High，且页面分数不低于 90 |
| `REVIEW` | 存在 High，或页面分数低于 90 但不低于 75 |
| `FAIL` | 存在 Critical，或页面分数低于 75 |

文档分数是页面分数平均值；文档状态采用最差页面状态覆盖：任一页面 `FAIL` 则文档 `FAIL`，否则任一页面 `REVIEW` 则文档 `REVIEW`。证据：
`core/src/document_qa/scoring/scorer.py:33-45`、
`core/src/document_qa/pipeline.py:290-327`。

## 配置开关

默认 Profile 可独立关闭以下检测组：缺失/新增元素、Region 偏移、字号缩小、越界、重叠、数字不一致、疑似漏译、Region 尺寸剧变、文字碎片化、字号放大、隐形文字、段落水平对齐变化。术语检测由是否注入术语库决定。证据：
`core/src/document_qa/profiles.py:82-99`、
`core/src/document_qa/detectors/rules.py:32-58`、
`core/src/document_qa/detectors/content.py:69-88`。

## 已预留但当前不会由检测器生成的问题类型

下列枚举存在于 Schema 和评分配置中，但在当前可达检测实现中没有对应的 `Issue` 生成路径，因此不能视为已支持能力：

| 预留 Issue 类型 | 当前状态 |
| --- | --- |
| `text_overflow` | 仅有枚举与扣分配置；现有实现只检测 Region 是否整体越出页面 |
| `text_clipped` | 仅有枚举与扣分配置 |
| `abnormal_wrap` | 仅有枚举与扣分配置 |
| `line_count_explosion` | 仅有枚举与扣分配置 |
| `table_structure_changed` | 仅有枚举与扣分配置；复杂表格恢复仍不在当前范围 |
| `other` | 通用扩展类型，当前核心流水线没有主动生成路径 |

证据：`core/src/document_qa/schemas/issue.py:21-46`；全仓库 `IssueType` 使用点集中于
`core/src/document_qa/detectors/` 和 `core/src/document_qa/pipeline.py`。

## 已知检测边界

当前系统不能可靠判断：

- 翻译语义是否正确、表达是否自然；
- 图片对象位置尺寸不变但图片内容被替换；
- 水印、线条、阴影、绘制顺序等纯像素层变化；
- 扫描 PDF 中未经 OCR 的文字；
- 复杂表格行列结构是否保持一致；
- 被遮挡但结构对象与 BBox 仍正常的最终视觉结果；
- 转曲文字中的数字、术语和漏译情况。

这些边界与项目契约及待办中的可选像素层方案一致：
`docs/project-contract.md:31-45`、`docs/todo/tech-adoption-plan.md` 的 T10。

## 测试证据概览

现有测试直接覆盖区域偏移、图片缺失、文本合并容错、文本图片重叠、数字一致性、漏译和术语违规。新近加入的 Region 尺寸剧变、文字碎片化、隐形文字、字号放大及文字转曲，在当前测试搜索中未发现逐类型断言，应在后续开发验收中通过真实样例分阶段验证，并按项目契约补足必要的边界证据。

证据存在一处文档状态差异：`docs/todo/tech-adoption-plan.md` 的 T9 索引仍写着“pptx/xlsx 待真实样例回归”，而当前本地历史产物已经有 PPTX 端到端运行记录。因此本文将 PPT 证据标记为“本地真实样例跑通”，不将其提升为已经正式登记完成的项目验收。

主要测试位置：

- `tests/test_matching_and_detection.py`
- `tests/test_content_detectors.py`
- `tests/test_glossary.py`
- `tests/test_pymupdf_pipeline.py`
- `tests/test_golden_samples.py`
