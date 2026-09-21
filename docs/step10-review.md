# Step 10: Balance Calculation & Settlement Suggestions

## Completed

2026-09-19（本机 America/New_York）：Step 10 已完成。新增一个只读余额接口、
动态 SQL 聚合、确定性结算建议、账本一致性检查及 38 个测试用例。
保留已有费用、权限和认证规则，没有启动 Step 11 或 HarmonyOS。

## OpenTrip Reference Review

实际核对 `https://github.com/stvlynn/OpenTrip.git` 远端 HEAD：
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`。本地参考 checkout 位于
`/private/tmp/triptogether-opentrip-reference`。网页工具未返回可用正文，
因此以核实过提交的实际 Git 源码为依据，不推测未查看的行为。

| 实际文件 | 核实结果 |
| --- | --- |
| `apps/api/src/domain/trip/settlement.ts` | `computeBudget` 按成员计算 paid/share/net，生成 debtor -> creditor 建议 |
| `apps/api/src/domain/trip/trip.ts` | `budget()` 从当前 snapshot 动态调用 computeBudget |
| `apps/api/src/application/dto.ts` | Trip DTO 输出 `budget: trip.budget()` |
| `apps/api/prisma/schema.prisma` | Expense amount 为 Int，participants 仅存关联 ID，没有 share_amount；未找到 settlement/payment 持久化表 |
| `apps/api/src/domain/trip/types.ts` | Balance、Budget、Settlement 类型 |
| `apps/api/test/trip.test.ts` | 测 paid-net、双人结算、seed 总额；seed 守恒允许绝对误差 <=1 |

参考实现确实存在 Trip-level balance 和 who-owes-whom，也存在净额化后的
债权/债务匹配；不是“没有完整余额逻辑”。它用 TypeScript number，
对每笔费用重新除以参与人数，随后 Math.round 汇总份额/net；初始按金额排序，
双指针推进，有小额阈值。没有显式 user_id 平局排序。
它的代码注释称 minimal，但所查看算法和测试没有证明全局最少交易数。

参考数据有 Trip/Expense currency；`computeBudget` 没有按币种分组或换算，
不能据此声称它安全支持多币种结算。未找到实际还款历史或本步骤对应的支付系统。
参考测试只阅读，没有运行。这里只借鉴动态派生和债权/债务匹配概念，
没有复制实现、移植 number 舍入、引入参考项目的框架或数据模型。

## Domain Design

```text
Expense + ExpenseSplit (source data)
                 |
            Aggregation
                 |
            User Balance
                 |
       Settlement Suggestions (derived data)
```

费用与已存分摊是事实来源；余额与建议是计算结果。当前每次读取直接计算，
不维护第二份会过期的余额。当前 participants 是 `Trip.owner_id UNION
TripMember.user_id`，Owner 权威不依赖冗余 membership 行。
返回所有当前参与者，包括没有支付/分摊的零余额成员。

未来若增加退出、移除、所有权转移，需要先决定历史债务如何保留与展示。
现在不实现这些能力；若原始 SQL 造成历史付款人/分摊人不再是参与者，
接口拒绝生成建议，而不是静默删除此人的债务。

## Files Changed

新增：

- `backend/app/services/balances.py`：纯匹配、单语句 SQL 聚合、账本检查和安全服务错误。
- `backend/app/schemas/balance.py`：成员余额、建议及完整响应的 Pydantic 类型。
- `backend/app/api/balances.py`：只读路由、认证依赖、错误映射和 no-store。
- `backend/tests/test_balance_algorithm.py`：纯函数例子、边界、精度和守恒性质。
- `backend/tests/test_balances.py`：PostgreSQL、权限、费用集成、异常账本、查询数。
- `backend/tests/test_balance_concurrency.py`：独立事务的读写并发快照测试。
- `docs/step10-review.md`：本报告、阅读指南、手工步骤和面试问答。

修改：

- `backend/app/main.py`：仅增加余额 router 的导入和注册。
- `README.md`：Step 10 状态、接口契约、验收和限制。
- `RECORD.md`：按八个规定小节新增本阶段记录。

本次没有修改 Expense 模型/业务代码、认证、成员服务、依赖或历史迁移。
临时网络验收脚本在 `/private/tmp/triptogether-step10-verify.py`，不是项目源文件。

## Database Changes

**No migration required.** 没有 schema change、Balance/Settlement/Payment 表。
数据库仍为 `0005 (head)`；`alembic check` 无差异。
五个既有迁移内容保持不变。没有启动时建表、缓存或后台同步任务。
未新增第三方依赖。

## Balance Formula

```text
paid(U)    = SUM(Expense.amount WHERE paid_by_user_id = U)
share(U)   = SUM(ExpenseSplit.share_amount WHERE user_id = U)
balance(U) = paid(U) - share(U)
```

所有查询只在授权 Trip 内。正数表示应收，负数表示应付，零表示净额已平。
`paid` 是实际垫付，不是费用创建者的统计；`share` 是责任，不要求付款人参与分摊。
例如 Alice 为 Bob 单独支付 50：Alice +50、Bob -50。

## API

`GET /trips/{trip_id}/balances`，Bearer JWT，返回：

```json
{
  "trip_id": 1,
  "currency": "USD",
  "members": [
    {"user_id": 1, "username": "alice", "paid": "120.00", "share": "60.00", "balance": "60.00"},
    {"user_id": 2, "username": "bob", "paid": "0.00", "share": "60.00", "balance": "-60.00"}
  ],
  "suggested_settlements": [
    {"from_user_id": 2, "to_user_id": 1, "amount": "60.00"}
  ]
}
```

成员顺序 user_id ASC。无费用时 currency=null、成员金额均为 "0.00"、建议为空。
单人支付并承担全部费用同样没有建议。只有 GET，不定义余额输入 schema 或写接口；
POST 返回 405，客户端不能覆盖服务器计算。
200 响应带 `Cache-Control: no-store`。

| 情况 | 状态 |
| --- | --- |
| Owner / accepted Member | 200 |
| 无 JWT / 无效凭证 | 401，沿用既有认证 |
| 其他人 / pending / 不存在或已删除的 Trip | 404 |
| 非法 path ID | 422 |
| 混币、分摊不守恒、历史身份不一致 | 409，仅通用错误，无建议 |
| 数据库错误 | 503，rollback，不暴露 SQL/凭据 |

## Query Strategy

每个有效调用只有 **2 条数据查询**：已有 current-user lookup，加一条
完整的 balance SQL。CTE（`WITH`）只是同一条语句内有名字的子查询，
不是数据库表，也不是多次网络往返。

1. `balance_trip` 复用 `accessible_to` 的 Owner OR EXISTS Member 条件。
2. `balance_participants` 合并 Owner 与成员，UNION 去重。
3. `balance_expenses` / `balance_splits` 限定账本范围。
4. `balance_paid` 按 payer GROUP BY SUM(amount)，`balance_shares` 按 user SUM(share_amount)。
5. `balance_split_totals` / `balance_audit` 检查每笔总额和币种数。
6. 合并身份并 LEFT JOIN 两份独立汇总，COALESCE 缺失金额为 Decimal 零。

先汇总再连接，避免把一笔支付与多个 splits JOIN 后重复累计 amount。
财务身份也参与 identity union，避免非成员财务行被静默漏掉。
没有逐个成员的查询、懒加载或 GET commit。测试直接记录 SQL，
2 人与 10 人均为 2 次查询，且没有 INSERT/UPDATE/DELETE/FOR UPDATE。
查询数恒定不代表工作量 O(1)：数据库仍需扫描/聚合相关费用与分摊，
规划器可自行优化；没有宣称每张表物理上只扫描一次。

## Balance Example

三人每笔都参与，币种 USD：

| Expense | Amount | Payer | 每人 Share |
| --- | ---: | --- | ---: |
| Hotel | 300.00 | Alice | 100.00 |
| Dinner | 90.00 | Bob | 30.00 |
| Tickets | 60.00 | Alice | 20.00 |

| User | Paid | Share | Net |
| --- | ---: | ---: | ---: |
| Alice | 360.00 | 150.00 | +210.00 |
| Bob | 90.00 | 150.00 | -60.00 |
| Carol | 0.00 | 150.00 | -150.00 |

建议顺序：Carol -> Alice 150.00，然后 Bob -> Alice 60.00。
Dinner 改成 150.00：每人 share170，net 为 +190/-20/-170。
再删 Tickets：paid300/150/0、每人 share150，net 为 +150/0/-150。
这些是实际 HTTP 验收数据，不只是纸面示例。

## Settlement Algorithm

`suggest_settlements` 是纯函数：接收 user_id -> Decimal net，
输出 SettlementSuggestion 列表；不调用 SQL/HTTP，不 commit，不读取全局状态，
也不修改输入字典。

1. 验证金额类型、有限性、最多两位小数，先检查所有 net 合计严格为零。
2. 拆成 creditors（正余额）和 debtors（负余额的绝对值）。
3. 两边仅在开始时按金额 DESC、user_id ASC 排序。
4. 双指针匹配，transfer=min(剩余 debt, 剩余 credit)，减去双方剩余值。
5. 一方归零就推进相应指针；双方同时归零就同时推进。

这是**初始排序**后的匹配，不是每一步重新寻找当前最大余额：
无需 heap，也不会偷偷引入不同的顺序规则。
以 Alice+80、Bob+20、Carol-50、David-50 且 Carol ID 较小为例：

| 步骤 | 建议 | 剩余应收 | 剩余应付 |
| --- | --- | --- | --- |
| 1 | Carol -> Alice 50 | Alice30，Bob20 | David50 |
| 2 | David -> Alice 30 | Bob20 | David20 |
| 3 | David -> Bob 20 | 0 | 0 |

每次两个活跃余额都大于零，故 transfer>0；每次至少一人归零，因此会终止。
正负用户集合互斥，没有自转账。精确守恒保证最后两边都清空。
非零用户 k 人时至多 k-1 条建议，但这不是全局最少交易数的证明。
排序 O(n log n)，匹配 O(n)，额外空间与输出 O(n)。
同金额按 ID 打破平局，因此输入字典顺序变化不影响结果。

## Conservation Invariant

每笔 Expense.amount 等于它的 splits 合计，因此：

```text
SUM(paid) = SUM(expense amounts) = SUM(stored shares)
SUM(balance) = SUM(paid) - SUM(share) = 0
```

SQL 检查每笔费用，包括缺少 splits；Python 纯函数再检查全体净额。
两笔损坏的费用可能一笔多1、一笔少1，让全局仍等于0，所以不能仅查全局。
测试分别覆盖单笔差异、两笔抵消、无 splits、混币和失去成员身份。
发现不一致返回409，不能掩盖误差、容忍一分钱或继续建议。

应用建议时，对付款方净额加 amount，对收款方净额减 amount，
最终所有 net 必须**精确**等于0。性质测试覆盖50组固定种子的不同规模账本，
检查正金额、无自转账、总转出=总应收、归零、确定性及输出条数界。

## Money Precision

SQL NUMERIC 聚合由 psycopg/SQLAlchemy 返回 Decimal；不转 float。
复用 `MoneyResponse` 序列化为固定两位字符串。没有偷偷 quantize/round
来修复不合法输入。`100/3` 的 33.34/33.33/33.33 直接从持久化 splits 相加。
测试额外调整一份守恒的历史分摊，证明 GET 不调用 equal_split。
这不表示 API 新增了 custom split 功能。

汇总值允许超过单笔 `9999999999.99` 上限。服务局部 Decimal precision=50，
足以覆盖当前 INTEGER 主键数量及 NUMERIC(12,2) 的聚合上界；
纯函数根据金额位数和用户数设置局部精度，避免受低精度调用环境影响。
不改变进程全局 Decimal 配置。极大金额和低 ambient precision 也有测试。
沿用统一两位会计精度，不声称支持各币种官方最小单位；不做 FX。

## Authorization

认证仍是已有 `get_current_user`。查询使用既有 `accessible_to`，
与 `get_accessible_trip` 相同的 Owner/Member 规则，但无需先单独查一次 Trip：
授权嵌在聚合语句内，使权限和账本使用同一快照。
不能只靠前端隐藏入口；数据库 scope 直接限制数据。
未接受邀请不算成员；创建者身份不影响读取权限；Trip.owner_id 仍是所有权权威。

## Concurrency / Freshness

PostgreSQL 默认 READ COMMITTED 下，每条语句读取一个已提交快照。
分别查 paid、share、members 可能在中间跨过另一次提交，导致假不守恒。
本实现将它们放入一条 SQL，没有修改全局隔离级别或给 GET 加行锁。
无需为了只读操作阻塞已有按 Trip 锁串行执行的写入。

两个独立连接测试实际验证：

- 写事务已经删除旧 splits、尚未提交时，余额 GET 仍返回完整旧账本，不等待写锁。
- 余额 SQL 已执行、结果返回前 PATCH 提交时，该次 GET 仍返回旧完整快照。

两者下一次 GET 都得到 150/75/75 的新结果。没有跨请求缓存，
也没有需要失效的 balance 表。响应代表查询快照，不能承诺永远与响应到达客户端
那一刻的数据库一致；并发写仍可在查询之后提交。费用同字段仍 Last Write Wins。
删除 Trip 后下一次 GET404；没有额外余额 cleanup。

## Tests

实际在 Python3.9.6、现有内部磁盘虚拟环境和本机 PostgreSQL17 运行：

| 命令 | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: |
| `python -m pytest -q` | 315 | 178 | 0 |
| `RUN_POSTGRES_TESTS=1 python -m pytest -q` | 493 | 0 | 0 |

相较 Step9 增加38例：22个无需PG、16个真实PG用例。默认 skipped 是显式 opt-in，
不是伪造通过。完整回归含 health/auth/JWT/Trip/Invitation/Itinerary/排序/Expense。
没有 SQLite 或新增 property-testing 依赖。

还执行了 SELECT1、`alembic current`（0005）、`alembic check`（无差异）、
`pip check`（无损坏依赖），并核对迁移 SHA-256 未改变。
普通 PG 测试用私有 schema + savepoint；并发测试用独立连接及已提交私有 schema。
所有 fixture 都清理自己的数据，不重置开发库。

## Manual Verification

已实际启动 Uvicorn 在 `127.0.0.1:8020`，使用随机进程内 JWT 密钥。
真实网络 HTTP 不是 TestClient；每次余额还用独立 SQL 分别 SUM paid/share 核对。
四人注册/登录201/200；Alice创建Trip、邀请Bob/Carol201，接受200；
pending404；三笔费用201；三人均能GET200且内容相同；outsider404、匿名401。
PATCH Dinner200、删除Tickets204，新净额与上方示例完全相同。
删除Trip204，余额404；health200且 `{"status":"ok"}`。

开发库验收前后七张业务表均为0行，只删除本任务准确ID/用户名/Trip名匹配的数据，
没有清除其他记录、重置序列、改写 `.env` 或输出密钥/密码/token。
确认 public 仍是七张业务表及 alembic_version。临时服务器已停止。
没有声称完成浏览器 Swagger 点击流程。

自行复验：

```bash
source /private/tmp/triptogether-step1-venv/bin/activate
cd /Volumes/Elements/TripTogether/backend
python -m app.db.check
python -m alembic current
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

1. 确认本地 `.env` 已有 DATABASE_URL、安全 JWT 配置；此步不用新依赖/迁移。
2. 打开 `http://127.0.0.1:8000/docs`，注册三人，用 JSON login 得到各自 token。
3. 用 Alice token Authorize，POST Trip；分别按邮箱邀请 Bob、Carol。
4. 各自切换 token 接受自己的邀请；记下实际 Trip/user ID。
5. 按上方三人示例 POST 三笔费用，participant_user_ids 都是三人的实际ID，
   currency="USD"，amount 必须是字符串，expense_date="2027-05-01"。
6. GET `/trips/{实际ID}/balances`，逐项比较 paid/share/net 和建议。
7. Bob PATCH Dinner amount="150.00"，再 GET；Carol DELETE Tickets，再 GET。
8. 无 token401；第四人404；邀请未接受时404。最后 Owner删Trip，余额404。
9. 数据库只读核对（将示例6换成自己的实际Trip ID）：

```sql
SELECT paid_by_user_id, SUM(amount) AS paid
FROM expenses WHERE trip_id = 6 GROUP BY paid_by_user_id;
SELECT s.user_id, SUM(s.share_amount) AS share
FROM expense_splits s JOIN expenses e ON e.id = s.expense_id
WHERE e.trip_id = 6 GROUP BY s.user_id;
SELECT e.id, e.amount, COALESCE(SUM(s.share_amount), 0) AS split_total
FROM expenses e LEFT JOIN expense_splits s ON s.expense_id = e.id
WHERE e.trip_id = 6 GROUP BY e.id
HAVING e.amount <> COALESCE(SUM(s.share_amount), 0);
```

最后一个查询应没有记录。退出服务器用 Ctrl+C，不要把 JWT/密码写进记录。

## Important Code

建议按以下七个文件阅读；无需先理解整个项目：

1. [services/balances.py](/Volumes/Elements/TripTogether/backend/app/services/balances.py:21)：
   `suggest_settlements` 第21行、守恒第31行、双指针第43行；
   `balance_query` 第59行、两个 GROUP BY 第73行、逐笔审计第82行；
   `get_balances` 第108行、paid-share 第121行。串起数学、SQL快照和安全失败。
2. [schemas/balance.py](/Volumes/Elements/TripTogether/backend/app/schemas/balance.py:8)：
   三种 response，第8/16/22行；它们描述公开结果而非数据库表。
   MoneyResponse 复用已有 Decimal 字符串输出，不暴露用户敏感字段。
3. [api/balances.py](/Volumes/Elements/TripTogether/backend/app/api/balances.py:21)：
   Depends 当前用户/Session、no-store 和409/503映射；Router不计算金额。
4. [test_balance_algorithm.py](/Volumes/Elements/TripTogether/backend/tests/test_balance_algorithm.py:17)：
   三个具体例子、固定随机性质测试第36行、非法输入和大额低精度；
   看如何验证最终归零而非只比较某一个“看起来对”的结果。
5. [test_balances.py](/Volumes/Elements/TripTogether/backend/tests/test_balances.py:101)：
   三笔费用动态变化第101行、已存余数第126行、损坏账本第164行、
   查询计数第185行。真实PG验证接口和事实来源，不模拟数据库金额行为。
6. [test_balance_concurrency.py](/Volumes/Elements/TripTogether/backend/tests/test_balance_concurrency.py:10)：
   两个 Event 控制暂停点、独立事务和 finally 释放，理解为什么快照测试需要真正并发。
7. [services/expenses.py](/Volumes/Elements/TripTogether/backend/app/services/expenses.py:42)：
   既有 equal_split 和 update_expense 第128行，是上游事实的生成者；
   余额只读取其已提交结果，不能二次均分。此文件未修改。

## Concepts to Understand

| 概念 | 本项目里的含义 |
| --- | --- |
| Derived Data | 可由费用/分摊重新计算的余额与建议，不独立落库 |
| Aggregation | 将很多笔记录汇总为每个人的总额 |
| GROUP BY | 按 payer/user ID 分组，在组内执行 SUM |
| Net Balance | 实付减应承担份额，是应收/应付而非银行账户余额 |
| Creditor | net>0，应当收到补偿的人 |
| Debtor | net<0，应当支付补偿的人 |
| Conservation Invariant | 全体应收等于应付，精确净额合计0 |
| Greedy Algorithm | 每步匹配当前指针的一对，用 min 清掉至少一方 |
| Deterministic Algorithm | 同输入一定产生同输出，稳定排序解决平局 |
| Algorithm Complexity | n名成员排序O(n log n)、匹配O(n)，不包含数据库聚合费用 |

## OpenTrip Comparison

| 方面 | OpenTrip（已检查代码） | TripTogether |
| --- | --- | --- |
| 派生 | Trip.budget 动态计算 | 单独只读余额 endpoint |
| 金额 | Int存储、number运算、Math.round | NUMERIC存储、Decimal运算、两位字符串 |
| 分摊 | 按人数重新除法 | SUM已保存的share_amount，保留余数 |
| 结算 | 初始金额排序、阈值推进 | 初始金额+ID排序、精确零推进 |
| 守恒 | seed测试允许<=1误差 | 逐笔检查及全局严格0 |
| 币种 | budget中未做分区/换算 | 单币种账本，混币拒绝 |
| 查询 | 已加载Trip snapshot派生 | 授权与聚合一条SQL，不N+1 |
| 支付 | 未找到对应持久化工作流 | 明确仅建议，无支付能力 |

参考帮助确认领域概念；实现选择来自本项目现有 SQLAlchemy、
Decimal、持久化 split、会员权限和 PostgreSQL 并发约束，因此没有复制代码。

## Interview Questions

1. **How do you calculate each user's balance?** 同一Trip内SUM实付减SUM已保存的应承担金额。
2. **Why is balance derived instead of stored?** 避免费用更新后还需要同步第二份余额，减少不一致来源。
3. **What does a positive balance mean?** 此人实付超过责任，应收回差额。
4. **What does a negative balance mean?** 此人承担额超过实付，应补付差额。
5. **Why must all balances sum to zero?** 每笔实付总额等于分摊总额，相减全局为0。
6. **How do you calculate total paid?** Expense按paid_by_user_id分组，SUM(amount)。
7. **How do you calculate total share?** 当前Trip的ExpenseSplit按user_id分组，SUM(share_amount)。
8. **How do you avoid N+1 queries?** 全部成员用分组汇总加JOIN，只有一条账本SQL，不逐人查。
9. **Why do you continue using Decimal?** 金额需要精确十进制，float近似会破坏分钱与严格守恒。
10. **How does the settlement algorithm work?** 正负分组、初始稳定排序、min匹配、归零推进双指针。
11. **Is the settlement algorithm globally optimal?** 没有此保证；它生成确定性、有效的建议，不证明最少笔数。
12. **Why is it deterministic?** 金额降序后按user_id升序解决平局，不依赖输入遍历顺序。
13. **What happens when a Trip has no expenses?** 返回所有成员0.00、currency=null、建议空列表。
14. **What happens when an Expense is modified?** 下一次SQL读取新的已提交金额与分摊，余额自动变化。
15. **What happens when an Expense is deleted?** 下一次汇总自然不再包含它，不需要删余额行。
16. **Why don't you persist settlement suggestions?** 当前没有实际还款事件；建议随事实改变，持久化会陈旧。
17. **How do you handle multiple currencies?** 不混算，复用单币种规则，发现混币409；不做FX。
18. **What's the algorithmic complexity?** 排序O(n log n)、匹配O(n)、空间O(n)；SQL工作量另外计算。
19. **How do you test financial invariants?** 检查每笔分摊守恒、全局0、正转账、无自转账、模拟后全员0。
20. **How would you extend this to record actual repayments?** 未来需独立还款事实、币种、双方身份、确认/撤销和幂等规则，再纳入净额；本步不实现，也不能直接把建议当已付款。
21. **Why one SQL statement instead of three small queries?** READ COMMITTED下三条语句可能读到不同提交，一条语句统一快照。
22. **Why check per-expense totals if global net is zero?** 两笔相反误差会互相抵消，全局0不能证明逐笔账本正确。

## Problems Encountered

- 多条简单聚合在并发下可能混版本：设计时选择单语句CTE解决，没有提高全局隔离级别或锁GET。
- 仅全局守恒会漏掉抵消错误：增加逐笔审计，测试确认安全409。
- OpenTrip网页查询没有正文：核对远端提交并阅读实际checkout，不编造参考结论。
- 一个测试清理补丁的上下文未匹配，未改动文件；纠正上下文后应用成功。
- 临时验收脚本首次写入审批超时，确认文件不存在后重试一次成功。
- pip缓存目录不可写仅导致禁用缓存，`pip check`成功。未出现最终测试失败。
- 尚无限制成员退出后的历史债务设计、真实还款、FX或交易数全局最优保证；
  这些是明确边界，不是本次偷偷实现的功能。

## RECORD.md

已按 AGENT.md 八小节追加 Step10，记录参考审查、架构、代码、真实验收、
限制与学习内容。之前阶段的历史结果保留，不把过去的测试数字改成当前数字。

## Next Step

仅推荐 **Step 11 — Backend MVP Hardening & API Integration Readiness**。
未开始实现；不自动进入 HarmonyOS。
