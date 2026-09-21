# Step 8: Shared Itinerary

## Completed

完成共享行程 CRUD、完整列表排序、删除后压缩、跨日期移动、日期/时间校验、
参与者权限、Trip 缩短日期保护，以及 PostgreSQL 迁移 0004。
没有新增第三方依赖，没有实现 Step 9、实时推送、地图或客户端。
下文是本阶段完整报告和学习材料；验证日期为本机 2026-09-19。

## OpenTrip Reference Review

先阅读 README、AGENT、RECORD、Step 6/7 review 和现有模型、服务、路由、
schema、迁移及测试。参考仓库为 `https://github.com/stvlynn/OpenTrip.git`。
通过 `git ls-remote` 实际确认 HEAD：
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`，与本地参考 checkout 一致。
网页工具没有返回可用正文，因此分析来自该提交的实际源码，不是产品外观猜测。
未复制参考项目代码，也未运行其测试；只阅读测试断言。

实际检查的参考文件（均相对 OpenTrip 根目录）：

- `apps/api/prisma/schema.prisma`：stops、trip_days、trips。
- `apps/api/src/domain/trip/types.ts`：DaySnapshot、StopSnapshot、TripIntake。
- `apps/api/src/domain/trip/trip.ts`：insertStop、updateStop、moveStop、
  deleteDay、reorderDays、permissionsFor。
- `apps/api/src/application/use-cases.ts`：loadReadable/loadEditable、保存和发布。
- `apps/api/src/application/trip/ops/schemas.ts`：HTTP/操作字段校验。
- `apps/api/src/application/dto.ts`：TripDto 和 stop 输出投影。
- `apps/api/src/interfaces/http/app.ts`：POST stop、PATCH stop、PUT position。
- `apps/api/src/infrastructure/persistence/trip-repository.db.ts`：
  按 sort_order 查询、事务内保存 stops、bumpVersion。
- `apps/api/src/infrastructure/realtime/trip-realtime-object.ts`、
  `cloudflare-trip-change-publisher.ts` 和 `apps/api/src/worker.ts`：
  WebSocket 接入、Durable Object 广播及重放。
- `apps/api/test/trip.test.ts`、`trip-service-realtime.test.ts`：
  插入、跨日移动、连续顺序，以及保存成功后发布/保存失败不发布的断言。

### 实际模型、字段与顺序

OpenTrip 不是一个叫 ItineraryItem 的模型，而是 `Trip -> trip_days + stops`。
day 有 trip_id、number、date_label、city、color、date，主键为 Trip/day number。
stop 有 id、trip_id、day、time、duration、name、area、category、lat、lng、
cost、cost_currency、created_by、transit、note、sort_order，并关联预订、评论、投票。
StopSnapshot 的 order 对应持久化 sort_order；DTO 不输出 order 字段，而保留数组顺序。
没有把不存在的 end_time 字段加到参考模型描述里。

insertStop 按某天的 index 找相邻元素，插入 Trip 的全局 stops 数组，
然后把所有 order 重写成从 0 开始的连续序号。moveStop 从旧位置移除，
在目标日期/index 插入，再重排全局 order。Repository 使用 ORDER BY sort_order。
save 在事务里删除/重插 stops（还包含其他聚合数据），不是本项目的逐条 ORM UPDATE。
参考 schema 没有我们新增的 `(trip_id,date,position)` 唯一约束。
当前检查范围没有发现独立的单 Stop DELETE 路由/服务；deleteDay 会删除该天 stops。
不能把这个行为误称为完整单条 Stop CRUD。

### 日期、地点与权限

参考 Trip/day 日期是字符串，可表示未知日期；Stop time/duration 也是字符串，
不是 PostgreSQL DATE/TIME，更没有 Stop 的开始/结束时间对。此 planning 模型没有
Trip 级时区字段；预订领域自己的时间戳不是 Stop 的时间设计。
TripIntake.destination 是地点名称，可有 destinationLat/Lng；Stop 使用 name/area
和 lat/lng。检查的 Stop 定义没有持久化 external place ID。
地点可经服务地理查询补充，不只是我们的普通 location 文本。
note 在参考领域声明为 Markdown，可包含图片 URL；本项目仅保存普通文本。

loadReadable 检查 membership：非成员 404；loadEditable 再检查 canEdit：
owner/editor 可编辑，viewer 403。creator 不是单条修改权限来源。
参考 legacy/demo 有宽松访问回退，本项目不采用。删除 day 也经过可编辑权限检查；
不能根据此推断一个未找到的 deleteStop 接口。

### 实时机制与取舍

确实存在实时机制：持久化成功后发布 Trip change，经 Cloudflare Durable Object
向相应 Trip 的 WebSocket 发送带 sequence 的 change，保存事件用于重放，
过旧游标收到 resync_required。Trip version 用作变化 revision/invalidation 信息，
不能仅凭 version 字段宣称具有乐观锁或自动冲突合并。
参考测试确认数据库保存失败不发布、通知失败不推翻已成功提交的修改。

借鉴：明确顺序、参与者校验、服务边界、事务、跨日移动需要重排。
不采用：day 独立实体、整体聚合重写、demo 回退、editor/viewer 额外角色、
坐标/地图、价格/预订、Markdown 媒体、投票评论、AI、WebSocket、version。
这些不属于本阶段目标，会增加表、状态和学习成本。

## Domain Design

```text
Trip
 |
 +-- ItineraryItem A
 +-- ItineraryItem B
 +-- ItineraryItem C

User
 |
 +-- created_by_user_id
             |
         ItineraryItem
```

一个 Trip 有多条 Item；每条 Item 只有一个必填 trip_id，这是 One-to-Many。
日期直接存 Item，不需要先创建 Day 表。创建者 User 只负责归属记录，
权限仍由 Trip.owner_id 或已接受邀请形成的 TripMember 决定。
外键足以表达关系，不添加当前代码不用的 ORM collection/relationship。

## Files Changed

新增文件：

- `backend/app/models/itinerary_item.py`：12 字段及持久化约束。
- `backend/app/schemas/itinerary.py`：create/update/response/reorder 四种 schema。
- `backend/app/services/itinerary.py`：权限、日期、顺序、事务与错误。
- `backend/app/api/itinerary.py`：六个认证路由、状态码与响应转换。
- `backend/migrations/versions/0004_create_itinerary_items.py`：增量迁移。
- `backend/tests/test_itinerary.py`：输入、共享编辑、权限、排序及失败回滚。
- `backend/tests/test_itinerary_migrations.py`：真实约束、默认值、隔离迁移往返。
- `backend/tests/test_itinerary_concurrency.py`：独立连接并发测试。
- `docs/step8-review.md`：完整报告。

修改文件：

- `backend/app/models/__init__.py`：注册 ItineraryItem 到 metadata。
- `backend/app/main.py`：挂载行程 router，health 不变。
- `backend/app/services/trips.py`：可访问 Trip 的可选行锁、日期缩短保护。
- `backend/app/api/trips.py`：新的 409 错误映射和文档。
- `backend/tests/test_user_migrations.py`、`test_trip_migrations.py`：
  更新最新 head/表集合断言，保留旧迁移回退测试。
- `README.md`：状态、六个 API、输入策略和手工验证步骤。
- `RECORD.md`：按 AGENT 的八个小节记录 Step 8。

依赖、真实 .env、User/认证/邀请业务实现和历史迁移 0001-0003 均未修改。
真实 HTTP 验收使用 `/private/tmp/triptogether-step8-verify.py`，不是后端业务模块。

## ItineraryItem Model

| Field | Type | Constraint | Purpose |
| --- | --- | --- | --- |
| id | INTEGER Identity | PK, NOT NULL | 稳定条目身份 |
| trip_id | INTEGER | NOT NULL, FK trips CASCADE | 唯一所属 Trip |
| title | VARCHAR(160) | NOT NULL, nonblank CHECK | 显示活动内容；API trim |
| location | VARCHAR(200) | nullable | 可选地点文本；自由活动无需地点 |
| date | DATE | NOT NULL | 活动所属日历日 |
| start_time | TIME without time zone | nullable | 可暂时不决定具体开始时间 |
| end_time | TIME without time zone | nullable, 成对规则 CHECK | 可选结束时间 |
| notes | VARCHAR(2000) | nullable | 有界普通备注，不渲染富文本 |
| position | INTEGER | NOT NULL, > 0 CHECK | 同 Trip/日期的明确显示顺序 |
| created_by_user_id | INTEGER | NOT NULL, User FK RESTRICT, index | 审计归属，不授予权限 |
| created_at | TIMESTAMPTZ | NOT NULL, now() | 创建时刻 |
| updated_at | TIMESTAMPTZ | NOT NULL, now() | 最近 ORM 修改时刻 |

UNIQUE(trip_id,date,position) 同时提供按 Trip/日期/顺序访问的 B-tree 索引，
无需重复 trip_id 索引。creator 索引支持引用检查。User 删除暂未实现，
RESTRICT 避免删除创建者后丢失归属或连带删除旅行计划。
updated_at 沿用 SQLAlchemy onupdate=statement_timestamp()，不是数据库 trigger；
原始 SQL 必须自己维护。API 空/相同 PATCH 不发 UPDATE，因此时间不变。

## Migration 0004

链路：0001 users -> 0002 trips -> 0003 membership/invitations -> 0004 itinerary。
先 autogenerate，再人工审查和整理；upgrade 只新增该表、PK、两个 FK、
三个 CHECK、复合 UNIQUE、creator 索引和时间默认值。
Trip 删除 CASCADE；User 删除 RESTRICT。所有必填字段有 NOT NULL。
downgrade 删除 creator 索引和新表，不删除 users/trips/membership/invitations。
回退会丢失行程数据，重新升级只恢复结构，不能恢复数据。

真实开发数据库执行 upgrade 到 0004；破坏性的 downgrade 仅在隔离测试 schema：
0004 -> 0003 -> head，确认已有 User/Trip 保留且模型一致。
历史 0001/0002/0003 未编辑；不使用 create_all。

## API

所有路径以前缀 `/trips/{trip_id}/itinerary` 开始：

| Method | Suffix | Success | Meaning |
| --- | --- | --- | --- |
| POST | 空 | 201 | 末尾创建，creator 从 JWT 用户得到 |
| GET | 空 | 200 | 全 Trip，SQL ORDER BY date, position |
| GET | /{item_id} | 200 | 限当前 Trip 的详情 |
| PATCH | /{item_id} | 200 | 合并旧值后的部分更新 |
| DELETE | /{item_id} | 204 | 删除并压缩原日期 |
| PATCH | /reorder | 200 | 返回该日最终有序列表 |

静态 /reorder 在动态 /{item_id} 前注册。没有复杂搜索、分页或日期过滤功能。
输入只接受 title/location/date/start_time/end_time/notes。
id/trip_id/creator/position/timestamps 等额外字段一律 422。
响应只包含模型的 12 个公开字段，没有 User 凭据。

## Shared Editing Flow

```text
Alice Create -> PostgreSQL -> Bob Read -> Bob Edit -> PostgreSQL -> Alice Read
```

Alice/Bob 操作同一个 trip_id/item_id。Bob 没有自己的 Item 副本；
Alice 下次 GET 读取已提交的新内容。创建者 ID 不因 Bob 编辑而改变。

## Authorization

| Actor | 行程读/创建/修改/删除/排序 | Trip PATCH/DELETE | 邀请 |
| --- | --- | --- | --- |
| Owner | 全部允许 | 允许 | 允许 |
| Accepted Member | 全部允许，包括他人创建的 Item | 404 | 404 |
| Other / Pending Invitee | 404 | 404 | 404 |
| Anonymous | 401 | 401 | 401 |

先 get_accessible_trip：owner OR EXISTS membership；再用 trip_id + item_id 查 Item。
因此即使用户参与两个 Trip，也不能把 B Trip 的 item_id 填到 A Trip 路径修改。
get_owned_trip 继续独立用于 Trip 管理，不把成员可读误扩展为元数据可写。

## Date & Time Validation

- title trim 后 1-160 字符；location 可空、trim、最多 200；notes 可空最多 2000。
- 文本拒绝 NUL 和非法 Unicode，避免数据库编码错误；备注不做 Markdown 解释。
- date 只接受真实 YYYY-MM-DD，拒绝数字时间戳和 datetime 字符串。
- Service 检查 Trip.start_date <= Item.date <= Trip.end_date，包含首尾日。
- 开始和结束可都空；仅开始合法；仅结束不合法。
- 两者存在时 end >= start，相等允许；23:00 -> 01:00 拒绝，不支持跨日。
- 时间为当地钟表值，接受 HH:MM、HH:MM:SS 及最多 6 位小数秒，拒绝时区/数字。
- PATCH 先合并旧值，省略表示保留，null 清除可空字段。title/date 不可清空。
- 已有 end 时单独把 start 清空不合法；可以同次把两者置 null。
- Owner 缩短 Trip 日期若排除任一现有 Item，409 Conflict。不是悄悄删除/移动；
  客户端先处理已有计划，再缩短日期。没有现有计划冲突时仍可更新日期。

## Ordering Design

position 以 Trip + date 为范围，从 1 开始，不依赖时间或创建顺序。
create 在锁内读 max+1；客户端不能传 position=999。
delete 先删除并 flush，再按旧 position 压缩成 1..N。
date move 先算目标日 max+1，修改日期/位置并 flush，然后压缩旧日。

reorder 要求完整排列：长度和 ID 集合必须与当前日期查询结果完全相同，
schema 另拒绝重复 ID；未知、外 Trip、其他日期、漏项均 422。
空日期允许 []，但日期仍需在 Trip 范围内。

例如原 A1/B2/C3，目标 C1/A2/B3：
把目标列表暂存 C4/A5/B6，flush 后旧 1/2/3 都空了，再写 C1/A2/B3。
临时位置始终正数且大于原最大值，不会触发正数 CHECK 或即时 UNIQUE 冲突。
压缩也复用这一小函数。已是目标顺序则不做无意义 UPDATE。

## Transaction Design

一次操作只有一次 commit；flush 只是发 SQL，不代表提交。
两轮排序之间若失败，rollback 恢复原位置和时间戳，不能留半个顺序。
其他连接在提交前看不到临时位置。删除/跨日移动与后续压缩也属于同一事务。
测试在第二轮 UPDATE 注入数据库错误，确认三种操作都整体恢复，HTTP 返回安全 503。
数据库异常不输出 SQL、参数、连接地址或底层异常。

## Concurrency

所有 itinerary 写先对可访问 Trip SELECT FOR UPDATE。已有 Trip 日期修改、
Trip 删除、邀请决策也先锁 Trip，所以同一 Trip 的相关写操作串行化。
拿锁后再查 Item/最大位置/全日列表，避免并发创建拿到同一个 max+1。
在 PostgreSQL 默认 READ COMMITTED 下，等待者后续查询看到前一提交的状态。
数据库 UNIQUE/CHECK/FK 仍是最终保护。

这是按 Trip 串行化的简单 MVP 权衡，不是高吞吐细粒度锁框架。
相同字段仍 Last Write Wins：Alice 先写 title=B，Bob 后写 title=C，最终 C。
锁保证数据库操作有序，却不知道 Bob 的客户端读过哪个旧版本，因此没有解决
业务意义的 Lost Update。没有 version、乐观锁、CRDT、合并或实时冲突检测。
全列表排序同样最后写入的合法完整列表生效；期间新增/删除使列表不完整则 422。

跨表日期规则依赖所有应用写路径遵守同一父行锁；绕过服务的原始 SQL
可以破坏日期/连续位置业务规则。CHECK 只能保证本行时间/正数，
UNIQUE 不能保证位置无空洞，不能夸大为数据库自动保护全部业务规则。

## Database Verification

实际 PostgreSQL 17 开发库：

- `alembic upgrade head` 成功，`alembic current` 为 **0004 (head)**。
- `alembic check`：**No new upgrade operations detected.**
- `app.db.check`：**PostgreSQL connectivity check passed (SELECT 1).**
- `psql \d itinerary_items`：12 列、INTEGER Identity、DATE、无时区 TIME、
  TIMESTAMPTZ/now()、3 CHECK、2 FK、复合 UNIQUE 和 creator 索引全部确认。
- 实际 SELECT 返回 Bob 的 Lunch（June 10, position 1）及 Alice 创建后被 Bob
  修改并移动的 Senso-ji morning（June 14, 09:30-10:00, position 1）。
  creator 保持 Alice/Bob 各自 ID，notes 更新可见，updated_at 晚于 created_at。
- Owner 删除 Trip 后，members/invitations/itinerary 对应行均为 0。
- 验证前/精确清理后五张业务表都为 0，残留 test schema 为 0；未重置序列。

## Tests

| Command | Passed | Skipped | Failed |
| --- | --- | --- | --- |
| python -m pytest -q | 231 | 121 | 0 |
| RUN_POSTGRES_TESTS=1 python -m pytest -q | 352 | 0 | 0 |

包含所有旧 health/注册/密码/JWT/auth-me/Trip/邀请/成员测试。
新增 84 个测试案例；没有 SQLite，未跳过 PostgreSQL 失败来伪造成功。
默认 skipped 是显式 opt-in 的 PostgreSQL 用例。

普通集成测试复用私有 schema 外层事务 + request savepoint，服务 commit 不污染开发数据。
并发测试复用 Step 7 的独立连接/已提交私有 schema fixture，并在锁前同步两请求。
并发创建均 201、最终位置 1/2；并发更新均 200；并发排序均 200且最终为一个完整排列；
缩短日期与创建竞争只允许 [200,422] 或 [409,201]，不存在越界行。
`pip check` 无依赖损坏。新增模块不需要新依赖。

## Manual Verification

实际临时 Uvicorn --reload 在 8018 启动成功，使用仅进程内随机 JWT 密钥：
三个用户注册/登录均 201/200；auth/me 和 health 200。
Alice 建 Trip/邀请 201，Bob 接受 200。
Alice 创建 Item 201 -> Bob GET 200 -> Bob PATCH 200 -> Alice GET 200 且值一致。
Bob 创建 201 -> Alice 列表 200 -> Alice reorder 200 -> Bob GET 验证顺序 200。
Charlie 六个操作全部 404，匿名六个全部 401。
Bob 修改/删除 Trip 和发邀请都 404；Owner 缩短日期冲突 409。
Bob 删除 Alice 的 Item 204；Owner 删除 Trip 204，数据库级联确认。
仅清理本任务账号/Trip，无凭据输出或 .env 修改。验证服务器已停止。
这次验收通过实际网络 HTTP，不是仅 TestClient；未声称完成浏览器交互验证。

自行重复步骤：

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

保持本地 DATABASE_URL/JWT 配置，打开 `http://127.0.0.1:8000/docs`。
注册三个一次性账号；登录后在 Authorize 填当前用户 token，不公开 token。
Alice POST /trips 设置 June 10-15；POST invitations 填 Bob 邮箱，Bob 接受。
创建 body 使用 `{"title":"Senso-ji","date":"2027-06-10","start_time":"09:30"}`。
按上面的实际角色顺序调用六个接口；排序必须使用返回的真实 ID。
在同一数据库的 psql 执行：

```sql
\d itinerary_items
SELECT id, trip_id, title, location, date, start_time, end_time, notes,
       position, created_by_user_id, created_at, updated_at
FROM itinerary_items ORDER BY date, position;
```

## Important Code

只选以下 8 个文件，按数据流阅读：

| File | 重点 / 解决问题 | 上游 | 下游 |
| --- | --- | --- | --- |
| backend/app/models/itinerary_item.py | __table_args__、FK、DATE/TIME 和时间戳；明确存储不变量 | Service/metadata | PostgreSQL |
| backend/app/schemas/itinerary.py | local_time、create 与 update 区别、extra forbid、完整 ID 列表 | HTTP JSON | API/Service |
| backend/app/services/itinerary.py | assign_positions、update_item、reorder_items；先锁、合并、flush、单 commit | Router | Session/Trip 服务 |
| backend/app/api/itinerary.py | Depends、静态 reorder 注册顺序、错误映射；不在路由写业务 | FastAPI | Service/Response |
| backend/app/services/trips.py | get_accessible_trip 与 get_owned_trip 分离、update_trip 越界查询 | Trip/Item API | SQLAlchemy |
| backend/migrations/versions/0004_create_itinerary_items.py | 对照模型读 upgrade/downgrade；只新增新表 | Alembic env | PostgreSQL DDL |
| backend/tests/test_itinerary.py | shared editing、reorder/compaction/move 和故障回滚；看业务可观察结果 | pytest fixtures | TestClient + PostgreSQL |
| backend/tests/test_itinerary_concurrency.py | 同步两个独立连接，尤其 shrink/create；验证并发不变量而非单线程假象 | Step 7 race fixture | 真实事务竞争 |

## Concepts to Understand

Shared State：只有 PostgreSQL 中的一份 Item。Bob 改的是 Alice 会再读取的同一行，
不是向 Alice 发送一个复制文件；这已经是共享数据。

Real-time Collaboration：需要服务端主动告诉 Alice 有更新。本阶段没有这种通知，
所以 Alice 下一次 GET 才看到变化；未来 WebSocket/push 是另一个独立能力。

One-to-Many：一个 Trip.id 可被多条 Item.trip_id 引用；每条 Item 只引用一个 Trip。
creator 的 User FK 是另一条“谁创建”的关系，不改变 Item 属于哪个 Trip。

Business Constraint：日期需要查询父 Trip 才能判断，放 Service，并用锁协调反向修改。
Database Constraint：NOT NULL/FK/CHECK/UNIQUE 拦住不合规则的 SQL，即便未经过 API；
例如 position>0 不需要知道其他表，因此适合 CHECK。

Ordering：created_at 只能告诉你创建先后，不能表达后来把午餐挪到景点前面。
position 是用户安排顺序的持久化结果，start_time 可空也不影响稳定展示。

Transaction/Atomicity：多条 SQL 可以是一件事。flush 发出 SQL、commit 一起生效、
rollback 一起撤回。排序不能只成功一半；原子性指全做或全不做，不是“只有一条 SQL”。

Last Write Wins：两个用户都成功改同一 title 时，后面的写覆盖前面的写。
行锁防止非法中间状态，不判断谁的编辑意图更正确。本阶段如实保留这个限制。

## OpenTrip Comparison

| Topic | OpenTrip | TripTogether |
| --- | --- | --- |
| Planning | Trip aggregate + days + stops | Trip + 一张 Item 表 |
| Time | 字符串 date/time/duration | 严格 DATE + 可空 TIME 对 |
| Order | Trip 全局从 0 开始的 order，day/index 移动 | Trip/date 从 1 开始，完整列表排序 |
| Place | 文本 + 坐标 + 地理补充 | 可空纯文本 location |
| Editing | owner/editor，viewer 只读，legacy 回退 | owner/member 编辑 Item，Trip 元数据 owner-only |
| Persistence | 聚合 save 删除/重插 | 局部 UPDATE，保留条目身份 |
| Collaboration | change publisher + Durable Object/WebSocket | 共享 PostgreSQL，下一次 GET 可见 |

未来如明确需要日级规划或推送，可以再参考它的 day 操作、通知失败隔离、
重连重放策略；本阶段不提前实现。

## Interview Questions

1. 如何建模共享行程？ItineraryItem 用 trip_id 连接唯一 Trip，参与者操作同一行。
2. 为什么是一对多？同一个 Trip.id 可被多条 Item 引用，每条只有一个 trip_id。
3. 怎样限制参与者访问？先 owner OR EXISTS membership，再用 trip_id/item_id 共同查询。
4. 为什么 Member 能改行程却不能改 Trip？操作权限不同；Trip 写仍走 get_owned_trip。
5. 日期如何限制？Service 在父行锁内检查 Trip 首尾日，边界包含当天。
6. 为什么分开 DATE/TIME？表示旅行日和当地钟表时间，不把未确定时间强制当成时刻。
7. 为什么要 position？创建时间和可空 start_time 都不能表达主动重排。
8. reorder 如何实现？要求该日所有 ID 的完整排列，服务按列表分配 1..N。
9. 为什么排序必须事务化？中途失败必须回到原顺序，不能让部分条目永久错位。
10. 如何避免唯一位置冲突？先移动到大于原最大值的临时正数位置，flush 后写最终值。
11. 移到另一日期会怎样？目标日 max+1，旧日压缩；一次 commit 一起生效。
12. 缩短 Trip 范围怎么办？已有 Item 越界就 409，不自动删改行程。
13. 业务约束和数据库约束区别？跨表日期在 Service 校验；本行正数/时间和 FK/UNIQUE 由 DB 兜底。
14. 这是实时协作吗？不是，Bob 提交后 Alice 下一次 GET 可见，没有服务端推送。
15. Alice/Bob 同时改同一条呢？父行锁串行化，后写同字段覆盖前写；Last Write Wins。
16. created_by 能限制编辑吗？不能，它是不可由客户端指定的审计字段，成员可互改。
17. flush 和 commit 区别？flush 执行 SQL 但未持久提交，后续失败仍可全部 rollback。
18. 唯一约束能保证连续位置吗？只能保证不重复；无空洞依赖服务压缩及统一锁策略。
19. 为什么不加 version？当前需求接受 LWW；乐观锁需要额外 API 冲突处理，不应假装已实现。
20. 怎么证明没扩大 Member 权限？回归测试和真实 HTTP 都验证 Member Trip PATCH/DELETE/invite 为 404。

## Problems Encountered

最初模型把字段命名为 date，同时用 date 类型注解，在 Python 3.9 类定义求值时
同名遮蔽导致 TypeError，迁移生成未执行。把类型导入别名设为 CalendarDay 后解决；
完整 default/live 测试都通过，无 schema 残留或业务数据影响。
外置磁盘 AppleDouble 是已知迁移风险，本次按既有文档执行
`dot_clean -m migrations/versions`，未修改 Alembic 或历史迁移。
原测试把最新 head 写死为 0003，只调整期望到 0004，保留往返测试。
网络/本机数据库与 HTTP 验收需要沙箱授权；pip cache 不可写仅禁用缓存，
`pip check` 正常，无运行依赖影响。

## RECORD.md

已按 AGENT 八小节补充 Step 8，记录设计、参考来源、文件、真实测试/HTTP/psql、
遇到的问题与 LWW/无推送限制，不把默认 skipped 说成已验证。

## Next Step

Step 9: Expense System。仅推荐，未开始实现。
