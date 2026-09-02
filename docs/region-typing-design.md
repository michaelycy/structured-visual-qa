# 区域类型感知（Region Typing）设计规格

状态：**设计稿，待评审**。本文档是 T39 的设计基线；与 T38 渲染验证层
（`docs/render-verification-layer-design.md`）同属"从枚举修复走向机制
覆盖"的原理线——T38 回答"这个主张是真的吗"，本设计回答"这个元素
是什么"。获批后按 §7 分期实施。

## 1. 背景与动机

### 1.1 词表与能力的落差

Schema 的 `ElementType` 预留了 11 类元素词汇（TEXT / PARAGRAPH /
HEADING / LIST / IMAGE / TABLE / CHART / SHAPE / HEADER / FOOTER /
OTHER），但解析器实际只产出 **2 类**（text、image），分组后 Region 层
只有 paragraph / heading / image 三种。词表是愿望清单，不是能力清单。

实测锚点（IGBT 32 页图表密集文档）：Block 层 103 image + 122 text；
Region 层 73 paragraph + 16 heading + 103 image。一份半导体行业报告里
的全部图表，在系统眼中与照片、Logo、装饰图没有任何区别。

### 1.2 类型无感知的已发生代价（全部有本仓库实例）

| 真实类型 | 当前遭遇 | 已发生案例 |
| --- | --- | --- |
| 矢量图表 | 不成为 Region，整体进入 background 桶，只服务于 invisible_text 的背景判断 | T29：饼图扇形作为"背景"参与判定却无类型身份，38 条误报 |
| 位图图表 | IMAGE Region，与照片/Logo/装饰图同权 | T27：图表标题被译文合并，区域级字号对照失真 |
| 表格 | 文本段落 + 网格线矢量，无表格感知 | 重排表格逐格暴露在字号/偏移检测下 |
| 公式 | LibreOffice 归一化后转曲或位图 | 仅靠 TEXT_VECTORIZED / TEXT_RASTERIZED 的 INFO 豁免兜底 |
| 页眉页脚 | 无分类 | 移页误报靠 8% 带状豁免的窄口子兜住 |

## 2. 设计原则

1. **类型是推断的语义属性**：解析器只看到路径、字符、像素；类型在
   区域层由统计特征推断，不指望解析器直接给出。
2. **保守分类，低置信回退**：置信度不足一律判 `other`，下游按现状
   处理。分类器的失败模式必须是"没识别出来"（退化为今天的行为），
   绝不能是"识别错了"（产生错误豁免 → 漏报）。
3. **只贴标签，不恢复结构**：TABLE 只标注"这是表格"，不做单元格
   结构恢复（契约 §3.2 排除项不越界）；图表只标注类型，不做轴值级
   语义解析。
4. **metadata 沉淀，公开字段不动**：结果写
   `region.metadata["semantic_type"]`（契约 §6.2 允许），公开 `type`
   字段不变，属兼容变更。
5. **分类依据可解释**：每条分类写入触发特征与置信度，可审计、可回溯。
6. **阈值集中**：全部特征阈值进入 `RuleProfile` 新增 `typing` 设置段，
   运行时实际值随分类结果写入 metadata。

## 3. 架构：三层

```text
Parse（信号沉淀）→ Grouper → [RegionTyping 新增] → Matcher → Detector → [Verifier T38] → Scorer
```

Typing 阶段位于分组之后、匹配之前：此时 Region 已成型、Block 级信号
已可用，且匹配与检测尚未开始消费类型。

### 3.1 层 1：解析信号沉淀（阶段 1，纯增量）

解析器已"看到"大量分类信号但随手丢弃。统一写入
`block.metadata["typing_signals"]`：

| 信号 | 来源 | 主要服务的类型 |
| --- | --- | --- |
| 矢量路径数 / 填充路径数 / 独立颜色数 / 填充面积比 | background 管线既有统计的扩展（现只算盒子与面积） | CHART_VECTOR、SHAPE、TABLE 网格 |
| 文本数字密度（数字字符占比） | span 文本统计 | 坐标轴标签 → CHART |
| 短文本比例（≤8 字符 span 占比） | span 文本统计 | 图例/轴标签 → CHART |
| 数学字体标记（Cambria Math、Symbol 等字体族名单） | span 字体 | FORMULA |
| 图片面积占页比 | 既有 bbox | CHART_BITMAP |

阶段 1 不做任何推断、不被任何下游消费，Golden 逐位一致。

### 3.2 层 2：类型推断器（阶段 2 主体，shadow 运行）

`RegionTyping` 按规则表推断，输出
`region.metadata["semantic_type"] = {type, confidence, evidence_keys}`。
置信度 ≥ 阈值（默认 high 档）才落类型标签，否则 `other`。

| 目标类型 | 判定特征（与 RuleProfile 阈值联动） | 置信策略 |
| --- | --- | --- |
| CHART（位图） | IMAGE 区域面积占页比 ≥ 阈值 且 周边短标签文本环绕（环绕度 = 紧邻短文本 Region 数） | 双特征齐备 high；仅面积 medium |
| CHART（矢量） | 区域内/周边矢量填充密度 ≥ 阈值 且 散点短文本 + 数字密度特征 | 双特征齐备 high |
| TABLE | 区域内网格线矢量密度 ≥ 阈值 且 行列对齐度（文本 Region 左右边缘共线比例）≥ 阈值 | 双特征齐备 high |
| FORMULA | 数学字体命中 且 区域短 且 符号密度 ≥ 阈值 | 字体命中即 medium，三项齐备 high |
| HEADER / FOOTER | 跨页重复聚类（归一化文本打码 + 位置带 + 出现页占比 ≥ 阈值）——原挂起的页眉页脚方案在此归并，不再单独立项 | 出现占比越高置信越高 |
| SHAPE | 大面积矢量填充 且 区域内无文本 | 单特征 high |
| 其他 | — | other |

设计要点：

- **规则优先，不引入模型**：首版全部是可解释规则；若未来规则精度不足，
  按契约 §12"扩展接口加入"再评估本地小模型，且必须保持可解释输出。
- **分类与豁免解耦**：本层只负责"是什么"；"豁免什么"是层 3 消费端的
  独立决策，二者分开演进、分开验收。
- **页级与文档级上下文**：HEADER/FOOTER 需要跨页统计，Typing 的该
  子步骤在整本文档分组完成后执行（文档级 pass），其余类型为页级 pass。

### 3.3 层 3：类型感知消费（阶段 3 起，逐消费点独立推进）

消费矩阵（`正常` = 现状；`降级` = 严重度上限下调；`豁免` = 不产出）：

| 消费点 | CHART | TABLE | FORMULA | HEADER/FOOTER |
| --- | --- | --- | --- | --- |
| font_shrink / merged_font_shrink | 豁免（图表标签重排是翻译常态） | 降级 | 豁免 | 豁免 |
| region_shifted / region_resized | 降级 | 正常（表格错位是真缺陷） | 豁免 | 豁免 |
| text_overlap / text_image_overlap | 降级（图内叠字常见） | 正常 | 正常 | 豁免 |
| number_mismatch | 降级（轴标签换算频繁） | 正常 | 豁免 | — |
| content_out_of_page | 正常 | 正常 | 正常 | 降级 |
| 匹配器 type_similarity | semantic_type 一致性计入相似度权重 | 同左 | 同左 | 同左 |
| T38 验证层 | 实证方法按类型选择（矢量背景 vs 位图背景的对比度采样策略不同） | — | — | 模板级对照（远期） |

矩阵中每个格子是一个独立消费点：独立实施、独立 Golden 评估、独立
回滚开关（`RuleProfile.typing.consumption` 逐项开关）。

## 4. 与 T38 渲染验证层的关系

- **互补**：T38 裁决"主张为真吗"，本设计供给"这是哪类元素"；几何/对应
  类误报走对应关系对齐路径（第三条原理线），三者共同构成机制覆盖。
- **依赖方向**：T38 阶段 1（shadow）不依赖本设计；本设计阶段 2 的
  shadow 也不依赖 T38。层 3 的"验证方法按类型选择"在 T38 阶段 3 后
  才启用。两份设计可并行评审、交错实施。

## 5. 成本与性能

- Typing 本体是纯内存统计（信号已在解析/分组时收集），无新增渲染、
  无新增 IO；HEADER/FOOTER 跨页聚类为 O(页数 × 带内区域数)。
- 性能预算：Typing 阶段耗时 < 总管线耗时 5%，E2E 计时验收。
- 报告体积：每 Region 增加约 60-120 字节 metadata（仅分类 Region），
  41 页文档约增 20-40 KB，可忽略。

## 6. 分期实施与验收

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| 1 | 解析信号沉淀 `typing_signals` | examples Golden **逐位一致**（纯 metadata）；信号数值抽样与 PyMuPDF 原始数据一致 |
| 2 | RegionTyping 推断器，shadow（只写 metadata） | Golden 逐位一致；IGBT / state-of-ai / SyneosHealth 三个真实文档的类型分布报告人工审（图表类召回抽检 ≥ 90%、误标率抽检 ≈ 0——误标即回退 other）；耗时预算达标 |
| 3 | 消费矩阵逐格启用 | 每格独立 Golden diff 逐条解释；构造用例：图表标签字号变化零误报、表格错位零漏报、公式排版豁免；误报库存中对应类目清零或可解释 |

每期独立提交、独立回滚（层 3 每个消费格有独立 profile 开关）。

## 7. 契约影响

1. metadata 新增字段（`typing_signals`、`semantic_type`）——契约 §6.2
   允许，兼容变更；
2. 阶段 3 各消费格改变检测行为——属行为变更，逐格附 Golden Sample
   前后差异（§12）；
3. 契约 §7 组件图增补 `Typing` 节点（Grouper 与 Matcher 之间）——与
   T38 的 Verifier 增补一并走基线确认，一次审批两处修改。

## 8. 明确不做（边界）

- 表格单元格结构恢复与内容级表格比对（契约 §3.2 排除项）；
- 图表轴值/图例的语义级解析与数值比对（远期候选，需单独立项）；
- 公式语义等价判断（仅做类型识别与排版检测豁免）；
- 机器学习分类模型（首版规则覆盖不足时按契约扩展接口另行评估）。
