# Competitive Research Snapshot

> 范围说明：此文为跨产品背景调研，不能回答“本次比赛是否有同类”。比赛内核查请以 [本次比赛轻社交同类核查](CONTEST_SOCIAL_RESEARCH.md) 为准。此说明用于纠正此前范围理解偏宽的问题。

调研日期：2026-10-23，北京时间。检索截止于本次整理；这是有边界的公开资料调研，不是全球穷尽搜索、专利检索或侵权鉴定。

## 1. Scope

**Company/product:** 拼好麦轻社交构想 | **Category:** 双人拆餐、饭搭子及用餐后关系沉淀 | **Decision supported:** 是否继续，以及如何区别于已有方案 | **Competitors analyzed:** 麦麦现拼、Timeleft、Beli、TRAE社区饭搭子原型。

研究对象是用户提出的“成功拼餐次数、公开排名、双人合照墙”，加上讨论中的“双方愿意再次约拼”。这些尚未实现。查找中文拼餐/饭搭子、英文 social dining、排行榜/照片/再次见面等组合；优先查项目仓库、官方产品与帮助页，再查作者原帖。事实（Fact）只说明来源确实声称了什么；推断（Inference）与待验证假设（Assumption）另列。没有登录或体验对方付费功能。

## 2. Competitor Snapshots

### Competitor: 麦麦现拼
- **Positioning:** 【Fact】项目README定位同店陌生人现场拆大套餐。
- **Relevant capability:** 【Fact】公开说明支持最多三人、认领、按参考单点价分摊、拼单广场与取餐流程。公开网页演示与本地真实MCP模式有边界区别。
- **Likely strength:** 【Inference】与我们原有拆餐场景最直接相邻，用户无需理解一种全新交易方式。
- **Likely weakness:** 【Inference】本次已读README未见成功次数排名、双方确认公开合照墙或饭后再次约拼的明确说明；这只能说明文档未说明，不能断言全部实现不存在。
- **Key source URL:** https://raw.githubusercontent.com/lululynne/maimai-xianpin/2c4e4688c7dd4cff6d1daef1b990133807a6f89e/README.md

### Competitor: Timeleft
- **Positioning:** 【Fact】官方定位组织陌生人在线下聚餐等活动中建立关系。
- **Relevant capability:** 【Fact】官方Streak页面明确列出活动历史、连续参与计数、Connect双方表达兴趣、Repeat邀请过去认识的人参加后续活动。
- **Likely strength:** 【Inference】“用餐后双向连接、再见面”和“参与记录激励”已有很接近的公开产品机制，不能将这些单独称为我们首创。
- **Likely weakness:** 【Inference】这些来源描述的是组织社交活动；未见同一双人套餐互补拆分、双方低于单点参考价的计算流程。
- **Key source URL:** https://timeleft.com/post/streak/ ; https://timeleft.com/blog/is-timeleft-a-dating-app/

### Competitor: Beli
- **Positioning:** 【Fact】官网定位与朋友记录和分享喜欢的餐厅。
- **Relevant capability:** 【Fact】官方隐私政策的数据字段明确包括个人头像、排行榜位置、去过/想去的餐厅、关注关系、用餐偏好。这支持“已有用餐记录与排名社交”，不支持断言它按成功拼单数排名。
- **Likely strength:** 【Inference】记录、个人展示、排名这一套社交激励并非空白。
- **Likely weakness:** 【Inference】本次来源未说明陌生人拆餐匹配、双方确认完成或双人同意合照墙，不能把缺少说明当作已证实缺少功能。
- **Key source URL:** https://beliapp.com/ ; https://beliapp.com/app-privacy-policy/

### Competitor: TRAE社区“饭搭子”原型
- **Positioning:** 【Fact】作者原帖2026-06-23公开介绍基于口味、预算、时段和位置的饭友匹配，附Demo HTML。
- **Relevant capability:** 【Fact】原帖提出饭后互评、信用积累、饭友关系与再次约饭，也提到商家搭子套餐/拼团优惠。
- **Likely strength:** 【Inference】在中文创意作品中，“吃饭匹配＋信用＋关系沉淀”也已有明确先例。
- **Likely weakness:** 【Fact】这是作者介绍与原型材料；本次没有核验支付、身份核验、信用接入及线上真实履约，不能当作已运营成熟平台。
- **Key source URL:** https://forum.trae.cn/t/topic/41973

补充照片机制参照：【Fact】Eatwith官方帮助页建议主持人活动后请客人评价、把现场照片加到个人资料。它说明“共同用餐＋评价＋活动照片”已有先例，但不等于双方逐张授权的双人合照墙。来源：https://intercom.help/eatwith/en/articles/2680329-how-do-i-become-an-eatwith-host ; https://intercom.help/eatwith/en/articles/1497789-write-reviews-for-your-guests

## 3. Quick Comparison

表中“未见”=本次指定来源未明确说明；“拟做”=我们未实现；不是对整个产品的否定。

| Dimension | 拼好麦构想 | 麦麦现拼 | Timeleft | Beli | 饭搭子原型 |
|---|---|---|---|---|---|
| Target customer | 附近愿意双人拆餐者 | 同店拆餐者 | 线下社交活动参与者 | 与朋友分享餐厅者 | 找附近饭友者 |
| Core use case | 双边省钱→可选一起吃→再拼 | 拆餐认领 | 聚餐→连接→再参加 | 用餐记录与分享 | 匹配→约饭→互评 |
| 完成记录/激励 | 拟做双方确认次数 | 文档未见排名 | 历史、连续参与计数 | 排名字段明确存在 | 信用积累为作者主张 |
| 再次约见 | 拟做双向意愿 | 指定来源未见 | Connect、Repeat明确 | 指定来源未见 | 原帖明确提出 |
| 共同照片 | 拟做双人同意公开/撤回 | 指定来源未见 | 指定来源未证实双人墙 | 有个人头像等资料，不等于合照墙 | 指定来源未见 |
| Main strength | 可核算互补拆餐结合低压力交往 | 与套餐直接衔接 | 饭后连接机制明确 | 记录与社交展示 | 中文低压力饭友场景明确 |
| Main weakness | 社交未做；无真实交易完成核验 | 社交延伸资料不足 | 已读资料不涉及拆餐省钱 | 已读资料不涉及拆餐匹配 | 真实运行未核验 |
| Evidence quality | 已有代码＋未来构想明确分开 | 一手仓库，未跑私密模式 | 官方自述，非本次实测 | 官方自述，非本次实测 | 作者原型自述，非运营证据 |

## 4. So What?

### 三项产品判断
1. 【Inference / 中高】这条大方向已有相近先例，不能再说“饭搭子＋排名＋照片”无人做过。依据见上列一手来源。
2. 【Inference / 中】本次未找到“麦当劳真实双人拆餐＋双方均省钱＋跨店单次领取＋可选共同用餐＋双方同意照片”的完整相同公开实现；检索局限不足以支持全球首创结论。
3. 【Inference / 中】差异应围绕“口味互补带来便宜、同一餐降低交往压力”，而不是堆砌常见榜单/动态。这个组合值得验证，但效果未知。

### 两项竞争风险
1. 【Inference / 高】对麦麦现拼只增加照片、排行榜，仍容易被理解为同类功能扩展，不能自动消除相似性疑问。
2. 【Inference / 中高】Timeleft及中文原型已描述再次约饭与饭后关系，不能将双向连接本身作为独占创新。

### 两项产品机会
1. 【Assumption / 待验证】发单时选择“只分餐”或“愿意一起吃10–20分钟”，两人意愿一致才提示社交；未同意则仍可完成省钱拼餐。
2. 【Assumption / 待验证】完成后显示真实平台记录、可选再次约拼及双人确认照片；用“帮搭子节省金额/共同完成”鼓励互惠，榜单自愿参加，平台范围标明。

### 三项待验证假设
1. 【Assumption】以省钱进入的人愿意一起坐下来吃；需要真实自愿选择率验证。
2. 【Assumption】公开次数能提升信任且不会主要诱发刷单；当前双确认不是官方交易完成证明。
3. 【Assumption】合照墙能促进复访；需观察双方公开同意率、撤回率，而非强制上传/露脸。

### 证据空白与搜索边界
- 未做全球全产品穷尽搜索、专利/商标检索，也没有核验商业产品所有版本和私有后端。
- 中文下载站和外包开发营销页虽出现信用分、动态墙等描述，但可信度不足，未用于确认产品实际存在或功能已落地。
- 未发现完整相同组合不等于不存在；照片分享、参与记录和饭后再次连接都有已知相邻先例。
- 独立开发证据、功能独创程度、第三方权利是不同问题，不能相互替代。

### 下一步可选研究
1. 竞品对照说明卡。
2. 面向评委的功能比较矩阵。
3. 两个季度的产品风险与机会。
4. 验证上述假设的用户访谈问题。
