# Step 17 学习复盘：产品化前端与端到端验证

## 核心概念

### Application Shell 是什么？

Application Shell 是 SPA 每个页面共享的外壳：品牌、顶部导航、主内容区和页脚。它让未登录用户看到 Login/Register，让已登录用户看到 Trips、Account 和 Logout，避免每个页面重复实现导航。

### SPA Navigation 与 Client-side Routing

SPA（单页应用）通常只加载一次 HTML。点击导航时，React Router 根据 URL 在浏览器内替换页面组件，而不是整页刷新；这就是 client-side routing。服务器仍必须在 API 层做认证和授权，路由保护只是前端体验。

### Responsive Design 是什么？

响应式设计用弹性宽度、网格与媒体查询，让同一份页面在桌面、笔记本、平板和窄屏手机上都可读、可操作。本项目在窄屏将多列卡片和表单收为单列，导航允许换行，避免内容被裁切。

### 为什么 Empty / Loading / Error State 很重要？

网络请求不是瞬时完成的。Loading 说明系统正在工作，Empty 告诉用户当前没有数据并给出下一步，Error 用可理解的话说明失败并提供重试。三者避免“空白页面到底是没数据还是坏了”的歧义。

### 为什么前端不能重新计算金额？

JavaScript 浮点数可能产生精度误差，而且前端自行分摊会和服务端规则不一致。TripTogether 将金额、份额、余额、结算建议都视为后端事实，前端只显示后端返回的精确字符串。

### 为什么隐藏按钮不能代替 Backend Authorization？

用户可以修改浏览器 DOM、直接调用 API，或使用另一个客户端。隐藏 Owner 按钮只减少误操作；FastAPI 的成员关系与角色校验才是安全边界。

### E2E、Unit 与 Integration Test 的区别

Unit Test 测一个小函数或组件的独立行为。Integration Test 测多个模块或真实服务边界协作，例如 FastAPI 与 PostgreSQL。E2E Test 按用户旅程验证多个层次串起来，例如注册、登录、邀请、编辑行程、添加费用和查看结算。Step 17 的真实 PostgreSQL 脚本覆盖 API/数据库旅程；前端组件测试覆盖界面交互。正式发布前可再加入真实浏览器自动化。

### Production Build 和 Dev Server 的区别

Vite dev server 为快速开发提供热更新。`npm run build` 会做 TypeScript 检查并生成优化的静态生产资源；构建成功不等于已经部署，也不应依赖开发服务器才能运行。

### 为什么 `.env` 不能提交 GitHub？

`.env` 往往含数据库密码、JWT 密钥或本机地址。一旦进入 Git 历史就难以完全收回，所以 `.gitignore` 排除它，只提交没有密钥的 `.env.example`。

### 为什么 `VITE_*` 不能保存 Secret？

Vite 会把 `VITE_*` 环境变量编进浏览器 bundle，任何访问者都能查看。它们只适合公开信息，例如 API origin，绝不能放 JWT 签名密钥、数据库密码或服务端 token。

### 为什么 Portfolio 项目需要 README 与可复现启动流程？

招聘者首先通过 README 判断项目边界、技术选择和工程习惯。明确的环境变量、迁移、启动和测试命令使他人能验证项目，而不是只能相信截图。

## Step 17 UI Architecture

- `App.tsx` 负责 Application Shell 与路由；Landing Page 不再把健康检查当作产品内容。
- `/trips` 是 dashboard：卡片显示目的地、日期和 Owner/Member 角色，并保留邀请收件箱。
- `/trips/:tripId` 以 Trip Header、Overview、Itinerary、Expenses & Balances、Members 的 section navigation 组织既有功能。
- 各面板继续调用原有 REST API；没有修改领域模型、后端计算或授权规则。

## OpenTrip 参考与边界

查看了 OpenTrip 的公开仓库 README、Trips home、day-by-day schedule 和 Budget & settle-up 的信息架构说明。TripTogether 借鉴了“旅程工作区优先、按日期组织行程、费用与结算放在同一信息区域、响应式页面”的设计思想。

没有采用其地图、PWA、预订、投票、评论、AI agent、多币种展示、Tailwind 或其源码/CSS/文案，因为它们超出本 MVP 的后端 Domain 与 Step 17 的 polish 范围。

## 面试问题与简答

1. **为什么使用 React Context 管理认证？** 小型 MVP 中认证状态范围有限，Context 足够清晰，避免 Redux 的额外复杂度。
2. **JWT 放在哪里？** 当前放在 `sessionStorage`，刷新同一标签页可恢复；它不是 XSS 防护方案。
3. **前端如何验证已有 token？** 启动时调用 `/auth/me`，而不是只相信本地 token 字符串。
4. **Protected Route 是否安全边界？** 不是；真正安全边界是后端 Bearer JWT 与授权校验。
5. **Owner 与 Member UI 为何不同？** 角色决定可见的管理操作，减少误操作；API 仍会拒绝未授权请求。
6. **为什么使用 React Router？** 它让 URL、浏览器历史和组件渲染保持同步。
7. **Landing Page 为什么移除 health 信息？** 普通用户关心价值与下一步，健康检查是开发/运维信息。
8. **Empty State 的作用？** 告诉用户没有数据并给出明确行动，例如创建第一个 trip。
9. **Loading State 的作用？** 将等待转化为明确反馈，避免空白造成的误解。
10. **错误信息为何不展示 raw exception？** 原始异常可能泄露内部细节，也不利于用户理解。
11. **删除为什么需要 confirm？** 为破坏性动作提供轻量、无依赖的防误触保护。
12. **行程为何按 date 分组？** 用户按旅行日规划活动，这比平铺列表更贴近任务。
13. **reorder 的正确性由谁保证？** 后端验证并保存顺序，前端只发送 item ID 顺序。
14. **金额为何是 string？** 保持十进制精确表达，避免 JavaScript float 误差。
15. **Equal Split 在哪里执行？** FastAPI 服务层；前端只选择参与者。
16. **Balance 在哪里计算？** 服务端基于持久化费用与 splits 派生。
17. **Settlement Suggestion 是支付吗？** 不是，它只是建议谁向谁支付多少。
18. **为什么要测试真实 PostgreSQL？** SQLite 与 PostgreSQL 的约束、事务和 SQL 行为可能不同，真实数据库验证更可信。
19. **测试数据如何清理？** 验证脚本生成唯一用户名，并在 finally 块删除相应 trip 与 users。
20. **生产 build 验证什么？** TypeScript 类型、模块解析和 Vite 打包可在非开发模式下成功。
21. **`.gitignore` 为什么要包含 `._*`？** 外置磁盘可能产生 AppleDouble 元数据文件，它们会干扰解释器和 Git。
22. **Step 17 为什么没有新 Domain？** 目标是把已完成流程变得可理解、可演示、可验证，而不是扩大风险面。
