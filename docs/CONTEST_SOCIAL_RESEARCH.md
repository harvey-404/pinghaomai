# 本次麦当劳 MCP 比赛：轻社交方向同类核查

核查日期：2026-10-23，北京时间。本报告修正此前调研范围偏宽的问题：用户要查的是本次比赛内的作品，而不是一般餐饮社交产品。Timeleft、Beli等只作为外部背景，不能回答比赛内是否重合。

## 1. 本次实际查了什么

- 从官方活动仓库的公开Issues接口分页读取了当时的1119条非PR记录，包括重复报名、讨论与可能未通过的申请。
- 从其中的GitHub仓库链接归一化提取961个仓库；成功取得950份README；11份未取得，后续通过GitHub默认README接口重试仍未成功。
- 这不是“961个已获资格的参赛作品”：申请状态、重复项目、链接引用和最终资格不能混为一谈。
- 对950份README筛查合照/合影/照片墙/相册、拼单次数/成团次数/成功次数、排行榜/段位/信用、同城搭子/陌生人、再次约饭/固定饭搭子等，并人工核读重点命中项目。
- 对最相关的“麦饭搭子”进一步阅读`scripts/rank.py`；没有运行对方项目、连接对方私密Token或核验真实线下交易。README未说明不等于代码中绝对没有该功能。
- 原始Issue响应与README仅保存在私人核查目录，未上传到拼好麦仓库；公开材料只放方法、最小索引和结论。[筛查摘要与重点源码哈希](evidence/contest-social-screen-summary.json)。

## 2. 最值得关注的比赛内作品

### A. 麦饭搭子：累计拼单与个人战绩已经存在

【事实，高置信】README明确列出累计拼单、省钱、零超支、连续天数，并据此计算战绩点，生成段位、徽章及个人档案卡。与用户提出的“展示成功拼过多少次”有明显接近之处。

【代码边界】`rank.py`将记录保存在本机JSON文件，提供record/show/reset。这是本地个人记录与养成机制；本次未核验到跨用户、双方确认履约后的成功拼单排行榜。不能把本地记录等同于真实订单完成证明。

- 比赛报名：[Issue #874](https://github.com/M-China/mcd-developer-innovation-challenge/issues/874)
- [README](https://github.com/MX168/maifandazi/blob/5675ea568387ae349aa3dc3376e4884c5aaf7117/README.md)
- [段位实现](https://github.com/MX168/maifandazi/blob/5675ea568387ae349aa3dc3376e4884c5aaf7117/scripts/rank.py)

### B. 麦麦合拍：同城招募、固定饭搭子已有演示

【事实，高置信】公开说明包含饭局发布/编辑/取消/重新招募、同城匹配演示和固定饭搭子模板，主流程为2–6人共享餐桌。

【作者明确的边界】同城搭子匹配仍是演示，没有公开陌生人招募市场、真实聊天或真实报名通知；固定饭搭子保存在浏览器，不是成熟运营的陌生人社交平台。未见成功拼单数排行和共同授权照片墙的明确说明。

- 比赛报名：[Issue #1058](https://github.com/M-China/mcd-developer-innovation-challenge/issues/1058)
- [README](https://github.com/Aresuae/maimai-hepai-public/blob/3001f466f01da604b2edc83b065d4fae69838f43/README.md)

### C. 麦麦营养搭子：社区发布、互动与热榜已有

【事实，高置信】项目公开描述用户发布搭配、顶/踩/评论、社区筛选与时间衰减热榜。与“从点餐工具延伸为内容社区”重合。

【边界】被排名的是餐品搭配的热度，不是发起人的成功拼单次数；README展示页明确含演示数据。本次未核验其真实用户运营或双人线下合照机制。

- 比赛报名：[Issue #183](https://github.com/M-China/mcd-developer-innovation-challenge/issues/183)，另有重复申请记录。
- [README](https://github.com/archerko-code/mcd-meal-community/blob/8ce37a06a6bb4cdf1adda65d273ffd24b364b30b/README.md)

### D. 麦麦搭子契合度报告：双人关系与下次约饭已有构想

【事实，高置信】README描述合并双方画像、生成默契报告及下次约饭餐单。接近关系沉淀和再次一起吃的方向，但不是陌生人拼单后的履约记录、榜单或合照墙。

- 比赛报名：[Issue #669](https://github.com/M-China/mcd-developer-innovation-challenge/issues/669)
- [README](https://github.com/xunxuntj/mcd-duo-wrapped/blob/53a2d6f605663770281c24a6066caa1efdfcb5d7/README.md)

### E. 麦麦现拼：原有拆餐部分的直接同类

【事实，高置信】同店陌生人拆大套餐、认领和取餐，与我们的原有拼餐部分接近。已读README未明确说明按成功次数的跨用户排名或双人合照墙；不能据此断言所有源码和后续版本没有。

- 比赛报名：[Issue #865](https://github.com/M-China/mcd-developer-innovation-challenge/issues/865)
- [README](https://github.com/lululynne/maimai-xianpin/blob/2c4e4688c7dd4cff6d1daef1b990133807a6f89e/README.md)

## 3. 对用户三个具体想法的判断

| 想法 | 比赛内查到什么 | 本轮结论 |
|---|---|---|
| 展示成功拼单次数 | 麦饭搭子已有累计拼单与档案卡 | 个人累计记录已有近似实现；双方核验成功与本地记录仍需区分 |
| 全平台按成功次数排名 | 有本地战绩/段位、社区内容热榜 | 本轮没有核验到相同的跨用户成功拼单排行榜；不能称全球首创 |
| 两个人吃麦后的合照墙 | 未找到明确描述两人同意公开的同类 | 在本次已取得README范围内是较明确的差异候选，仍需承认检索空白 |

筛到的“McMuseum”照片墙指产品照片，不能算作两名真实拼餐者的合照墙；食物摄影和虚拟合影也不计为相同功能。[该项目README](https://github.com/peterpark12138/McMuseum)。

## 4. 对我们下一步的建议（推断，不是已实现功能）

1. 【推断，中】不要只做累计数字/段位：已有近似方案。值得做的是由同一份邀请的两名参与者分别确认完成，形成“双方确认完成”的站内记录；在未接真实交易核验前不称官方认证成交。
2. 【推断，中】照片墙围绕真实双人关系：一次完成记录关联一张双方自愿确认的照片，支持撤下，允许不露脸。单纯晒餐内容已有社区先例。
3. 【推断，中】进一步连接跨店单次领取、双边省钱与自愿再次约拼，让产品形成连续流程。此次未查到完整相同组合，但不能以组合没被本次检索命中作为原创性法律结论。

## 5. 局限与后续复查

- 未取得README的11个仓库：1parado/mcdaily、Librowner14/privite、dandan1232/mai-recap、fan59835402/mcd-party-scout、hhlllkkk/mcctl、jokercaijojo/maimai-watchdog、ly18z/McArchaeologist、shellteo/mcd-nft、yifei245/mcd-nutrition-butler、zddamn/mcd-saver、zmh07069/mcd-saver-skill。
- 有的仓库可能移除、私有或尚无README，不能把无法读取当作无相关功能；本次未逐个确认失败原因。
- GitHub报名与源码会变化；跨多分钟读取不是原子快照。重点项目的提交SHA与README哈希单独记录供复查。
- 本报告确认“比赛内已有相邻作品”，不对报名是否最终通过、线上完整落地、权利归属或抄袭作结论。
