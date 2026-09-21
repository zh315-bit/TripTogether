# Step 9: Expense System

## Completed

实现 Expense + ExpenseSplit、五个费用 API、精确均摊与确定性余数分配、
付款人/承担者校验、成员共享编辑、事务回滚和迁移 0005。
Step 10 的 Trip Balance、债务结算、谁给谁转账均未实现。
无新增依赖，无汇率、自定义比例、支付服务、实时推送或客户端。
验证时间采用本机日期 2026-09-19。

## OpenTrip Reference Review

先复核 README、AGENT、RECORD、Step 7/8 review 和已有代码。
参考仓库 `https://github.com/stvlynn/OpenTrip.git` 的远程 HEAD 实际核对为
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`，与现有本地 checkout 一致。
网页工具未提供可用正文，分析来自 git 源码。没有复制源码，没有运行参考测试。

实际参考文件：

- `apps/api/prisma/schema.prisma`：expenses、expense_participants、Trip/member。
- `apps/api/src/domain/trip/types.ts`：ExpenseSnapshot、Budget、Balance。
- `apps/api/src/domain/trip/trip.ts`：addExpense、updateExpense、requireMember。
- `apps/api/src/domain/trip/settlement.ts`：computeBudget，仅研究边界，不移植算法。
- `apps/api/src/application/use-cases.ts`：loadEditable、费用保存和发布。
- `apps/api/src/application/dto.ts`：费用/参与者和预算输出。
- `apps/api/src/interfaces/http/app.ts`：费用 POST/PATCH。
- `apps/api/src/infrastructure/persistence/trip-repository.db.ts`：
  费用与参与关系读取、事务内删除/重插聚合数据。
- `apps/api/test/trip.test.ts`：拒绝空参与者、币种默认/覆盖和修改测试。

OpenTrip 有费用领域，不是“没有找到费用功能”：

1. expenses 存 string id、trip_id、description、payer_id、Int amount、
   when_label、sort_order、currency、category。
2. payer 指 Trip-local member ID，而非本项目的 users.id；领域 requireMember 校验。
3. expense_participants 保存 expense_id/member_id 复合主键；没有 share_amount 列，
   Prisma 未为 member_id/payer_id 声明与用户/成员表的 FK。
4. Trip FK 和 participant -> expense FK 使用 CASCADE。
5. 领域使用 TypeScript number，保存时 Math.round；不能称为 Python Decimal。
6. 均摊并非逐笔持久化金额：computeBudget 用 amount / participants.length，
   累加后 Math.round 产生成员余额，再生成结算建议。
7. Trip 有 currency，费用可覆盖默认币种；测试明确接受 JPY Trip 中的 USD 费用。
   检查的 computeBudget 直接聚合金额，没有按 currency 分组或进行换汇；
   因此不把它描述成已安全处理多币种结算。
8. add/update 都经过 loadEditable：owner/editor 可改，viewer 不可改，
   非成员 404，另有本项目不采用的 legacy/demo 回退。
9. 已查到费用 POST/PATCH 和聚合详情读取；未在检查的服务/路由找到独立
   Expense DELETE，不能根据表级 cascade 推断存在完整删除 API。
10. Repository save 在事务里保存费用及参与关系，但并不保存我们要求的逐人
    精确份额；参考的余额算法不能替代本阶段的金额守恒设计。

借鉴：付款人与参与者分离、参与关系单独存储、成员访问、服务与事务边界。
不采用：整数存储的参考具体数值逻辑、整体聚合重写、预算/结算、混合币种、
分类标签、when_label、实时/AI。TripTogether 的持久化均摊基于自身需求设计。

## Domain Design

```text
Trip
 |
 +-- Expense
       +-- paid_by_user_id ------> User
       +-- created_by_user_id ---> User
       +-- ExpenseSplit
              +-- user_id ------> User
              +-- share_amount
```

Trip 1:N Expense；Expense 1:N ExpenseSplit；
User 1:N 付款记录，也可在多条 ExpenseSplit 中承担份额。
Expense 是“谁支付了多少钱”；Split 是“谁承担多少钱”，两者不能合并成 payer。
例：Bob 记录 Alice 替 Bob 支付的 50，creator=Bob，payer=Alice，唯一 split=Bob/50。

## Files Changed

新增：

- `backend/app/models/expense.py`：费用与 splits 关系。
- `backend/app/models/expense_split.py`：承担份额、唯一约束。
- `backend/app/schemas/expense.py`：严格输入、Decimal 与安全输出。
- `backend/app/services/expenses.py`：均摊、权限、币种、事务和一致读取。
- `backend/app/api/expenses.py`：五个路由与统一错误映射。
- `backend/migrations/versions/0005_create_expenses_and_splits.py`：新表迁移。
- `backend/tests/test_expenses.py`：算法/schema/HTTP/持久化/回滚。
- `backend/tests/test_expense_migrations.py`：约束/默认值/往返迁移。
- `backend/tests/test_expense_concurrency.py`：并发重算与币种竞争。
- `docs/step9-review.md`：完整设计、报告和学习材料。

修改：

- `backend/app/models/__init__.py`：注册两个新模型。
- `backend/app/main.py`：挂载费用 router。
- `backend/tests/test_user_migrations.py`、`test_trip_migrations.py`、
  `test_itinerary_migrations.py`：仅调整最新 head/表集合断言。
- `README.md`：当前状态、API、金额/币种规则与手工步骤。
- `RECORD.md`：按八小节记录本阶段。

未改 Trip 模型、历史迁移 0001-0004、认证、邀请或行程业务逻辑。
临时验收脚本位于 `/private/tmp/triptogether-step9-verify.py`，不是业务代码。

## Expense Model

| Field | Type | Constraint | Purpose |
| --- | --- | --- | --- |
| id | INTEGER Identity | PK, NOT NULL | 稳定费用标识 |
| trip_id | INTEGER | NOT NULL, FK CASCADE, index | 所属 Trip |
| description | VARCHAR(200) | NOT NULL, nonblank CHECK | 付款用途，API trim |
| amount | NUMERIC(12,2) | NOT NULL, >0 且 <=9999999999.99 CHECK | 精确付款总额 |
| currency | VARCHAR(3) | NOT NULL, 大写字母 CHECK | 记账币种标记 |
| paid_by_user_id | INTEGER | NOT NULL, User FK RESTRICT, index | 实际付款人 |
| expense_date | DATE | NOT NULL | 实际付款日，可在旅行前后 |
| created_by_user_id | INTEGER | NOT NULL, User FK RESTRICT, index | 记录者，不是权限来源 |
| created_at | TIMESTAMPTZ | NOT NULL, now() | 创建时刻 |
| updated_at | TIMESTAMPTZ | NOT NULL, now()/ORM onupdate | 最新修改时刻 |

本阶段允许旅行日期外的 Expense：机票、酒店可能提前付款；旅行结束后也可能补付款。
它不是某一天的行程活动，因此不复制 Itinerary 的日期范围限制。
Trip 缩短日期不自动影响费用，原有行程日期保护不变。

## ExpenseSplit Model

| Field | Type | Constraint | Purpose |
| --- | --- | --- | --- |
| id | INTEGER Identity | PK, NOT NULL | 分摊行标识 |
| expense_id | INTEGER | NOT NULL, FK CASCADE | 所属单笔费用 |
| user_id | INTEGER | NOT NULL, User FK RESTRICT, index | 承担者 |
| share_amount | NUMERIC(12,2) | NOT NULL, >=0 且 <=上限 CHECK | 精确承担金额 |

UNIQUE(expense_id,user_id) 保证同笔同人只有一行，且其索引已支持 expense_id 查询，
不额外重复建立 expense_id 索引。允许 0 份额，因为 0.01 分给三人必然有人承担 0。
User 删除未实现，用 RESTRICT 保持审计/引用完整性。

## Money Representation

比较两种方案：

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| Decimal + NUMERIC(12,2) | 数据库直接可读金额、Python 精确十进制、贴合 API | 需严格控制输入和精度 |
| integer minor units | 整数除余方便，无二进制小数误差 | API/SQL 必须始终解释单位和换算比例 |

选择 Decimal + NUMERIC，计算均摊时临时变为“百分之一单位”的整数除余。
这不是偷偷转成 float，而是精确表示之间转换；最终每条份额仍是 Decimal。

链路：JSON 字符串 -> Decimal -> Service Decimal/整数 -> ORM Decimal ->
psycopg/PostgreSQL NUMERIC -> Decimal 响应模型 -> 两位小数字符串。
`money_input` 拒绝 JSON number（包括整数）、bool、NaN、Infinity、指数写法、
空白、负数、超过两位小数及超上限值。没有把 1.001 静默舍入到 1.00。
内部 Python 可传合规 Decimal；HTTP 契约只接受字符串。

十进制 0.1 在二进制中通常是无限展开，float 存的是附近可表示值，
所以 `0.1 + 0.2` 可能呈现为 `0.30000000000000004`。
`Decimal("0.1")` 从原始十进制字符串构造，避免先经 float 的近似。
Decimal 也有上下文精度；当前最多 12 位金额和整数除余在默认精度下精确，
代码没有修改全局 Decimal 上下文。

### Currency Policy

Trip 当前没有 currency。没有偷偷给 Trip 加字段或改变已有 API。
所有**现存**费用必须同币种：在父 Trip 锁内检查其他费用是否存在不同 currency。
首笔确定现存账本币种；其他币种创建或冲突 PATCH 返回 409。
只剩一笔时可更正其币种标签，金额不换算；全部删除后下笔可重新选择。
这不是一个永久 Trip.currency 设置或汇率转换。

三位大写只是格式，不查询官方币种表。统一两位小数是本 MVP 的记账精度，
不宣称实现 JPY 等币种官方最小单位，也不支持三位精度货币的完整规则。
未来正式扩展币种精度需单独设计；本阶段不接外部汇率或币种库。
Step 10 可在这项单币种约束下聚合现存账目，但还未实现。

## Migration 0005

autogenerate 后逐项人工审查和整理。upgrade 创建 expenses，再建 expense_splits；
FK 从 Trip 到 Expense、Expense 到 Split 都 CASCADE，User 引用 RESTRICT。
两个 Identity 主键、全字段 NOT NULL、金额有限范围 CHECK、币种/描述 CHECK、
split 复合 UNIQUE。上下限同时排除 NUMERIC 的 NaN，不能只写 amount>0。

必要索引：expenses.trip_id 服务列表/币种查询；payer/creator/user 索引支持引用检查；
split 的复合 UNIQUE 已覆盖 expense_id。没有给所有描述/日期等字段乱加索引。
downgrade 先删 splits 后删 expenses，保留旧表。回退丢失费用数据，
重新升级恢复结构而不是被删除的记录。
开发库实际升级到 0005；0005 -> 0004 -> head 在真实 PostgreSQL 私有 schema 验证，
没有对开发库进行破坏性 downgrade。旧迁移哈希保持不变。

## API

| Method | Path | Success |
| --- | --- | --- |
| POST | /trips/{trip_id}/expenses | 201 ExpenseResponse |
| GET | /trips/{trip_id}/expenses | 200 list |
| GET | /trips/{trip_id}/expenses/{expense_id} | 200 ExpenseResponse |
| PATCH | /trips/{trip_id}/expenses/{expense_id} | 200 ExpenseResponse |
| DELETE | /trips/{trip_id}/expenses/{expense_id} | 204 empty |

Create 六个必填字段：description、amount、currency、paid_by_user_id、
expense_date、participant_user_ids。server id/trip/creator/timestamps/splits 禁止输入。
PATCH 同六字段部分更新；省略保留，显式 null 拒绝；最终状态重新检查成员/币种。
amount 或参与者集合变化就重算；其他修改保留份额。排序后的相同参与者集合是 no-op。
空/完全相同 PATCH 不推进 updated_at；仅修改参与者也会推进父 Expense.updated_at。
列表 SQL 排序为 expense_date DESC,created_at DESC,id DESC，最后 ID 保证稳定；
splits 按 user_id ASC。输出只有公开字段和 user_id/share_amount，不展开 User 凭据。

## Equal Split Algorithm

`backend/app/services/expenses.py` 的 `equal_split` 是独立可测试的纯函数。
参与者先按 user_id 排序，金额精确乘 100 变整数 units：
`quotient,remainder = divmod(units,人数)`。
每人先拿 quotient，前 remainder 个 user_id 多拿 1 单位，再转 Decimal 两位小数。

```text
120.00 / 2: 12000 divmod 2 = (6000, 0)
=> 60.00, 60.00

100.00 / 3: 10000 divmod 3 = (3333, 1)
=> 33.34, 33.33, 33.33

0.01 / 3: 1 divmod 3 = (0, 1)
=> 0.01, 0.00, 0.00
```

没有随机选择、没有丢弃余数、没有简单把 33.333... 各自四舍五入。
商乘人数加余数恰好等于总 units，所以 SUM(share_amount)==amount。
相同金额与参与者集合永远同样结果，不受请求顺序影响。

## Authorization

| Actor | Expense CRUD | Trip PATCH/DELETE/Invite |
| --- | --- | --- |
| Owner | 全部允许 | 允许 |
| Accepted Member | 全部允许，含他人创建记录 | 404 |
| Other / Pending Invitee | 404 | 404 |
| Anonymous | 401 | 401 |

操作者复用 get_accessible_trip，不新增费用专属权限体系。
payer/承担者身份是业务输入，需要独立验证：从 TripMember 取指定用户集合，
与 owner_id 合并后比较。空/重复列表在 schema 拒绝，未知/非成员统一 422，
不泄露对方是否全局注册。即使 owner membership 被外部 SQL 弄丢，
authoritative owner_id 仍可作为付款人/参与者，符合既有 Owner OR Member 语义。
Item 查找使用 trip_id + expense_id，不能跨 Trip ID 绕过作用域。
Payer 无需在 splits 中；creator 固定取当前 JWT 用户，不能由客户端冒充。

## Transaction Design

Create：锁 Trip -> 验证成员/币种 -> add Expense+Splits -> flush -> 响应快照 -> commit。
Update：锁 Trip -> 加载完整旧值 -> 合并 -> 验证 -> 更新金额/清空旧 splits ->
flush 删除旧唯一键 -> 添加新 splits -> flush -> 响应快照 -> commit。
先删旧行避免相同 expense_id/user_id 插入产生唯一冲突，两个 flush 不是两次提交。
任何 SQL/commit 失败 rollback，HTTP 安全 503，不暴露数据库内部内容。
故障测试在费用已 INSERT/UPDATE 后故意让 Split INSERT 失败，确认全部恢复。

响应先在事务锁内构造成独立 Pydantic 数据，再成功 commit 才返回。
避免提交释放锁后 lazy reload 把另一个更新的一部分混进本次响应。
GET 使用 joinedload 一次 SQL 获取金额和所有份额，不用两条查询跨提交拼装。
删除时 ORM 处理已加载 splits；数据库 CASCADE 也保护直接 SQL/Trip 删除。

## Database Invariants

数据库保证：PK、NOT NULL、FK、非负/正数有限金额、币种格式、每笔每人唯一。
服务保证：payer/参与者属于 Trip、参与者非空、同 Trip 单币种、精确均摊、
SUM(splits)==amount。这些跨行/跨表不变量不适合用普通单行 CHECK 表达。
父行锁 + 单次事务 + 测试覆盖应用写路径，不声称原始 SQL 随意写也能保持总额。
NUMERIC(12,2) 对原始高精度 SQL 输入会按列精度处理；API 提前拒绝多余小数，
不能把数据库存储精度等同于输入拒绝规则。
updated_at 沿用 ORM statement_timestamp，不是数据库触发器，手写 SQL 自行维护。

## Concurrency

所有 Expense 写先锁所属 Trip，与现有邀请/行程/Trip 删除锁顺序一致。
第二个 PATCH 等待后读取最新 Expense+Splits，再合并和重算。
因此不会提交“amount=150，splits 总额=120”。
两个不同币种同时创建首笔，只会一个 201，一个 409，不能形成混合账本。

同字段写仍 **Last Write Wins**，没有版本校验、历史审计表或编辑冲突合并。
串行化数据库操作不等于判断客户端哪个过时意图应优先，吞吐量也按 Trip 限制。
这些保证针对应用管理的数据和默认 READ COMMITTED 环境。

## Database Verification

实际 PostgreSQL：

- upgrade head 成功；current **0005 (head)**。
- alembic check：**No new upgrade operations detected.**
- connectivity：**PostgreSQL connectivity check passed (SELECT 1).**
- psql `\d expenses`：10 列，NUMERIC(12,2)、DATE、TIMESTAMPTZ、
  3 CHECK、3 FK、Trip/payer/creator 索引均确认。
- psql `\d expense_splits`：4 列，NUMERIC(12,2)、非负 CHECK、
  两 FK、复合唯一约束及 user 索引确认。
- 实际 SELECT：Dinner 150.00 USD 对应 Alice 75.00/Bob 75.00；
  Bob 记录 Alice 垫付 50.00，唯一承担者 Bob 50.00。
- SQL 检查无总额不一致记录，Expense 删除和 Trip 删除均清理 splits。
- 验证前后七张业务表均为空，只清理任务创建的明确 ID，未重置序列。

## Tests

| Command | Passed | Skipped | Failed |
| --- | --- | --- | --- |
| python -m pytest -q | 293 | 162 | 0 |
| RUN_POSTGRES_TESTS=1 python -m pytest -q | 455 | 0 | 0 |

比 Step 8 新增 103 案例；旧 health/注册/JWT/Trip/邀请/成员/行程排序回归包含在内。
算法覆盖三个要求例子、最大值、100 种金额与 10 种人数的守恒和最大份额差；
Schema 拒绝 float/整数/NaN/无穷/精度溢出/身份注入。
真实 ORM 和 response 中为 Decimal，JSON 金额为字符串。
PostgreSQL 测试覆盖 null/FK/CHECK/UNIQUE/NaN、0005 往返、级联删除、事务回滚。
并发测试使用已有 Step 7 fixture 的独立连接，验证重算响应和最终数据库的金额一致，
以及不同首笔币种只允许一个成功。没有 SQLite 或伪装跳过失败。
普通 live tests 仍用私有 schema+外层事务/savepoint，不污染 public。

## Manual Verification

真实 Uvicorn --reload 在 8019 启动，JWT 密钥只存在测试进程环境中。
三个用户注册/登录为 201/200，health 和 auth/me 200。
Alice 创建 Trip/邀请 201，Bob 接受 200。
Alice 创建 120.00 Dinner 201，返回 60.00/60.00；
Bob GET/PATCH 200，改为 150.00，返回 75.00/75.00；
Alice GET 200，读取相同更新。
Charlie 五个费用操作全 404，匿名全 401。
非成员 payer/承担者 422，混币创建 409，JSON 数字金额 422。
Bob 记录 Alice 替 Bob 垫付 50.00 成功 201，creator/payer 正确分离。
Bob 删除 Alice 的 Expense 204；Owner 删除 Trip 204，两级 cascade 通过。
临时数据清理完毕，服务器已停止；无密码/JWT/.env 输出或修改。

自行复现（保持原有 DATABASE_URL/JWT 配置）：

```bash
source /private/tmp/triptogether-step1-venv/bin/activate
cd /Volumes/Elements/TripTogether/backend
python -m alembic upgrade head
python -m app.db.check
python -m alembic current
python -m alembic check
python -m pytest -q
RUN_POSTGRES_TESTS=1 python -m pytest -q
python -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/docs`，注册并登录 Alice/Bob/Charlie；
每次切换 Authorize 中 token 后执行相应角色步骤。Alice 建 Trip、邀请 Bob，Bob 接受。
使用返回的用户 ID 创建：

```json
{
  "description": "Dinner",
  "amount": "120.00",
  "currency": "USD",
  "paid_by_user_id": 1,
  "expense_date": "2027-05-01",
  "participant_user_ids": [1, 2]
}
```

把示例 1/2 替换为真实 ID；Bob PATCH `{"amount":"150.00"}`，Alice 再 GET。
psql 检查：

```sql
\d expenses
\d expense_splits
SELECT id, trip_id, description, amount, currency, paid_by_user_id,
       expense_date, created_by_user_id FROM expenses;
SELECT expense_id, user_id, share_amount
FROM expense_splits ORDER BY expense_id, user_id;
SELECT e.id FROM expenses e LEFT JOIN expense_splits s ON s.expense_id=e.id
GROUP BY e.id HAVING count(s.id)=0 OR sum(s.share_amount) <> e.amount;
```

最后查询正常应返回空集。清理时只操作自己建的测试 Trip，勿回退有数据的开发库。

## Important Code

只选 8 个：

| File | 重点理解 | 上游 -> 下游 |
| --- | --- | --- |
| backend/app/models/expense.py | Numeric、payer/creator、splits relationship | Service -> PostgreSQL |
| backend/app/models/expense_split.py | 复合唯一、非负份额、CASCADE | Expense -> 分摊表 |
| backend/app/schemas/expense.py | money_input、字符串契约、PATCH null、MoneyResponse | JSON -> Service/响应 |
| backend/app/services/expenses.py | **equal_split 的 divmod/余数分配**，create/update 事务、joinedload | Router -> Session/纯算法 |
| backend/app/api/expenses.py | Depends、404/409/422/503 映射，不写金额计算 | FastAPI -> Service |
| backend/migrations/versions/0005_create_expenses_and_splits.py | 表创建顺序、正反向 FK 和 CHECK | Alembic -> DDL |
| backend/tests/test_expenses.py | test_exact_split、共享流程、失败后恢复旧总额 | pytest -> HTTP/真实 PG |
| backend/tests/test_expense_concurrency.py | 独立事务同时重算和首笔币种竞争 | Step 7 fixture -> 行锁 |

## Concepts to Understand

Decimal 是 Python 十进制数；NUMERIC 是 PostgreSQL 精确十进制存储。
二者配合不等于任意输入都安全，所以还要限制类型、范围、小数位和输出序列化。
Expense 保存付款事实，ExpenseSplit 保存承担分配；payer 垫付款不表示自己承担全部。
Creator 只是记录者，不决定谁能编辑。
Equal Split 尽量平均；不能整除时 remainder distribution 补回剩余百分之一单位，
避免简单 rounding 造成总额损失。排序 user_id 让这个规则可重复。
Transaction 把父记录与子份额当一件事提交，Atomicity 表示全成或全不成。
Database Invariant 是必须一直成立的关系；数据库约束和服务事务各负责适合的部分。
共享费用是共享状态：Bob 修改后 Alice 下一次 GET 才可见，不是实时通知。

## OpenTrip Comparison

OpenTrip 用 expenses + 参与 ID 关联，读取时计算预算/余额；
TripTogether 用 Expense + 已存好的精确 ExpenseSplit，Step 9 只记录单笔承担额。
前者 Trip/Expense 可存不同币种、数值计算用 number；后者单币种现存账本、
Decimal/NUMERIC + 精确余数分配。没有照搬不满足本任务守恒要求的计算方式。
未来 Step 10 可以参考领域边界，但不能直接照搬其混币聚合/舍入逻辑。

## Interview Questions

1. 如何建模共享费用？Trip 下 Expense 表示付款，ExpenseSplit 存每人精确承担额。
2. 为什么拆两张表？一笔付款可由多人承担，payer 单字段无法描述多条份额。
3. 为什么不用 float？十进制小数的二进制近似可能积累误差，不适合精确守恒。
4. 为什么选 Decimal/NUMERIC？API、Python、ORM、数据库均保留可读的精确十进制金额。
5. 100 分三人怎么做？10000 除 3，商 3333 余 1；最低 ID 多拿 1，得到 33.34/33.33/33.33。
6. 如何保证份额合计？整数 divmod 数学守恒，父子同一事务保存，并以单元/PG 测试验证。
7. payer 为什么可不在参与者里？Alice 可以只为 Bob 垫付；Bob 承担不表示 Alice 自己消费。
8. payer 怎么校验？已有 Trip 行锁内查询 membership，加上 owner_id 后检查其 ID。
9. 参与者怎么校验？schema 拒绝空/重复，Service 验证所有 ID 都在当前 Trip。
10. 为什么复合 UNIQUE？同笔同人只能一份，不禁止同一个人承担多笔费用。
11. 创建为什么要事务？任何 Split 失败都不能留下只有付款总额的孤立记录。
12. 修改金额怎么办？保留最终参与者集合，重新均摊，原子替换旧份额。
13. 修改参与者怎么办？合并旧金额后校验新集合，删旧 splits，再创建新 splits。
14. 并发如何处理？父 Trip 锁串行化，每次金额/份额一致；相同字段仍 LWW。
15. Trip 删除怎样清理？数据库 Trip->Expense->Split 两级 CASCADE。
16. 为什么不换汇？缺乏汇率时间/精度/来源规则，本阶段用单币种账本避免错误相加。
17. DB 与 Service 各管什么？DB 管行级范围/FK/UNIQUE；Service 管成员、币种一致及跨行总额。
18. Step 10 如何计算余额？概念上按用户汇总实际付款，减去存储的承担份额；
    这是未来聚合逻辑，本阶段没有实现余额接口或谁给谁转账算法。
19. 为什么金额要求字符串？避免 JSON 数字先解析成 float，输入边界就保持精确。
20. 为什么 GET 用 joinedload？一次 SQL 快照同时读父金额和子份额，避免跨两次读取混合版本。
21. 修改币种是换汇吗？不是，唯一费用可改标签但金额不变，有其他币种费用时 409。
22. 0 份额合法吗？0.01 分三人时两个 0.00 合法，总付款仍正数。

## Problems Encountered

Trip 没有 currency，不能假设它存在；选择父锁内约束现存费用同币种，
并记录清空账本后的重选规则，没有擅自重构 Trip。
跨行总额不能只加单行 CHECK，采用可测试纯算法和原子父子写入。
人工整理新迁移时第一次补丁同时删除/添加同路径被工具拒绝，文件未变化；
改为普通更新补丁成功，无数据库影响。
已知外置磁盘 AppleDouble 风险按既有 dot_clean 流程处理，未改 Alembic。
旧迁移测试的最新版本断言需要更新到 0005，保留原有回退行为。
网络与本机 PostgreSQL/HTTP 访问需要授权。已执行测试没有失败。

## RECORD.md

已按 AGENT 的八个小节更新 Step 9，记录实际结果、读码重点和限制。

## Next Step

Step 10: Balance Calculation。仅推荐，未实现。
