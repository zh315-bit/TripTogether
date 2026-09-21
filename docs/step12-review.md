# Step 12 - Frontend Foundation Review

## Completed

React + TypeScript + Vite foundation implemented. This is an application shell,
not a dashboard or landing page. It calls the real public health endpoint and
shows Checking, Connected or Unavailable. User browser acceptance is pending.
No Step13 authentication UI/token storage or later business UI was implemented.
No backend Python, models, migrations, dependencies or actual `.env` changed.

## Environment

Verified on September20,2026: Node24.21.0, npm11.19.0, React/ReactDOM19.3.0,
TypeScript6.0.3, Vite8.3.0, React Router7.18.4, Vitest5.0.1, jsdom30.1.0,
ESLint10.11.0. Exact resolved versions are in `frontend/package-lock.json`.
Only npm is used. Node24 meets the installed Vite engine constraint.

## OpenTrip Frontend Reference Review

Inspected reference checkout `/private/tmp/triptogether-opentrip-reference`,
commit `cfc78a04d0eeba3daaec4b755b110d89938ae4fc`:

- `apps/web/src/app/router.tsx`: routing and page organization.
- `apps/web/src/app/App.tsx`: application composition.
- `apps/web/src/app/AppErrorBoundary.tsx`: error recovery boundaries.
- `apps/web/src/shared/api/client.ts`: centralized transport.
- `apps/web/src/shared/config/index.ts`: environment configuration.
- `apps/web/src/widgets/app-sidebar/AppSidebar.tsx`: navigation/responsiveness.
- `apps/web/src/app/providers/index.tsx`: provider responsibilities.
- `apps/web/src/pages/trips/TripsPage.tsx`: page loading/error boundaries.

Adopted ideas: a single transport layer, explicit request states, clear component
responsibilities and responsive layout. Did not adopt source/CSS/assets/branding,
Better Auth, cookie transport, React Query, a provider stack or a sidebar/dashboard.
Those would conflict with this small step or TripTogether's existing Bearer API.

## Files Created

All application files in `frontend/` are new this step:

- `package.json`, `package-lock.json`: dependencies and reproducible scripts.
- `index.html`: HTML root, title and description.
- `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`: official project
  references; strict application typing enabled.
- `vite.config.ts`: React transform and jsdom tests; excludes AppleDouble files.
- `eslint.config.js`: JavaScript/TypeScript and React Hooks lint rules.
- `.gitignore`, `.env.example`, `README.md`: generated-file exclusions and setup.
- `src/main.tsx`, `src/App.tsx`: React mounting, shell and two routes.
- `src/index.css`, `src/App.css`: plain responsive CSS and visible focus.
- `src/api/client.ts`, `src/types/api.ts`: HTTP adapter and contract types.
- `src/components/BackendStatus.tsx`: request state, cleanup and retry.
- `src/App.test.tsx`, `src/api/client.test.ts`, `src/test/setup.ts`:25 tests and cleanup.

Default logos, counter, hero image and icon sprite were removed.
Outside frontend, updated `.gitignore`, `README.md`, current status in `AGENT.md`,
`docs/client-integration.md`, `docs/known-limitations.md`, this review and
`RECORD.md`. Historical Step1-11 entries remain intact.

## Frontend Architecture

```text
React Component -> API Client -> FastAPI -> Service -> SQLAlchemy -> PostgreSQL
```

That is the future business request chain, not what `/health` does.
This step's actual request stops at FastAPI: `/health` never accesses PostgreSQL
and does not validate JWT. Connected therefore means HTTP application liveness,
not database readiness, authenticated access or production security.

No empty hooks/utils/domain directories are created merely to match a tree.
The two small page components remain in `App.tsx`.

## Routing

`BrowserRouter` selects `/` or `*` (Not Found). `Link` returns home without a
full-document reload. No login/register/trip placeholders are implemented.
A future static SPA deployment needs an index.html fallback; no deployment
configuration is added in this step.

## API Client

Native `fetch` needs no Axios dependency. `apiFetch` owns URL construction,
`Headers`, Accept, JSON decoding, HTTP error envelopes, 204 empty bodies,
network failure and a10-second timeout. It does not retry writes automatically.
Cancellation propagates so an unmounted component ignores obsolete results.

`ApiError` carries status/code/message/details. Error payload guards check
validation issues (`loc`, `msg`, `type`) instead of treating arbitrary JSON as
trusted types. `getHealth` validates `{status:"ok"}` at runtime.
Generic `apiFetch<T>` does not itself prove an arbitrary successful JSON schema;
future endpoint adapters need their own appropriately scoped contract checks.
Callers explicitly set Content-Type when sending JSON; GET does not add it.
Future auth can extend centralized header assembly; this step adds no tokens.

## Environment Configuration

`frontend/.env.example` contains only `VITE_API_BASE_URL=http://127.0.0.1:8000`.
Copy it to ignored `frontend/.env`. The client requires an HTTP(S) origin:
credentials, queries, fragments and paths such as `/api/v1` are rejected.
There is no hardcoded address fallback in application code.
System paths use `/health`; later business adapters pass `/api/v1/...`.

Root `.env` belongs to Python; frontend `.env` belongs to Vite.
VITE values are visible in browser code and must never contain passwords,
DATABASE_URL or JWT_SECRET_KEY. Restart dev server after changing settings;
rebuild for a different production API origin.

## Backend Connectivity

Started Uvicorn on `http://127.0.0.1:8000` and Vite on
`http://127.0.0.1:5173`. Real Chrome displayed TripTogether and Connected.
Real `GET /health` returned HTTP200 with `{"status":"ok"}`.
Desktop screenshot inspection found the heading, connection state and footer
readable without overlap. No frontend mock server/proxy was used in this check.

## CORS Verification

Set process-only `CORS_ORIGINS` to
`["http://127.0.0.1:5173","http://localhost:5173"]`; did not change real `.env`.
Verified:

- Health GET with the127.0.0.1 frontend Origin:200, matching Allow-Origin.
- OPTIONS `/api/v1/trips`, POST with Authorization/Content-Type:200,
  matching Allow-Origin, no Allow-Credentials.
- OPTIONS from `http://unlisted.test`:400, no Allow-Origin.
- Real Chrome read the health response and displayed Connected.

CORS is browser transport policy, not authentication. The preflight check
does not create trips or implement frontend JWT behavior.

## UI States

Loading: Checking... while the mount/retry request is pending.
Success: Connected only after validated health data.
Failure: Unavailable, a safe error message and Retry connection.
Missing configuration, network, malformed response and timeout have error paths.
Text accompanies the colored indicator; semantic headings/status and visible
focus support basic accessibility. There is no list, so Empty is not applicable.
The component does not poll. Stopping the server requires a page refresh to
initiate a new request and observe the outage.

## Tests

`npm test`: **25 passed, 0 failed, 2 test files**.
Application tests cover initial loading, StrictMode success, failure/retry,
configuration failure, invalid health data,404 and return-home navigation.
Transport tests cover configured origin, invalid settings, envelope/details,
network errors, non-JSON errors, malformed success,204, Headers, cancellation
and timeout classification.

## Lint

`npm run lint`: **passed**, no warnings/errors. The latest scaffold supplied
Oxlint; replaced it with requested ESLint plus TypeScript and Hooks rules.
No duplicate linter retained.

## Build

`npm run typecheck`: **passed**, zero TypeScript errors.
`VITE_API_BASE_URL=http://127.0.0.1:8000 npm run build`: **passed**.
Production output: HTML0.48kB, CSS2.19kB, JS262.96kB (gzip83.61kB JS).
This verifies compilation/bundling, not a production deployment.

## Backend Regression

No backend code changes; full PostgreSQL rerun not required.
As an extra check, default pytest was executed: **354 passed,184 skipped**.
The184 live PostgreSQL cases are intentionally opt-in. The earlier538-pass
PostgreSQL result is historical evidence, not a new execution.
Backend sorted SHA256 manifest digest remains:
`e830138090ee225eb4216191794df6af0910d651bf0dbca8181ba72f2113dde4`.

## Manual Verification

Terminal1:

```bash
cd /Volumes/Elements/TripTogether/backend
source /private/tmp/triptogether-step1-venv/bin/activate
CORS_ORIGINS='["http://127.0.0.1:5173","http://localhost:5173"]' \
  python -m uvicorn app.main:app --reload
```

Terminal2:

```bash
cd /Volumes/Elements/TripTogether/frontend
npm ci
cp -n .env.example .env
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

1. Open `http://127.0.0.1:5173`; expect TripTogether and Backend: Connected.
2. Stop backend with Ctrl+C, refresh frontend; expect Unavailable and Retry.
3. Restart backend, click Retry; expect Connected.
4. Open `/missing`; expect404 page, Return home restores the home route.
5. Check a narrow mobile viewport and desktop; no horizontal overflow or overlap.
6. Navigate with Tab; verify visible focus and keyboard activation.
7. Check Network for actual `/health`200, not a static Connected label.
8. Stop both servers with Ctrl+C. PostgreSQL running via brew services does
   not require a third persistent terminal.

Agent Chrome connectivity/desktop inspection does not replace user acceptance.
Mobile-width inspection and browser outage/recovery still require confirmation:
browser automation was interrupted when the user interacted with Chrome.
Unit tests of those request states passed, but are not a browser acceptance claim.
Please perform these steps and report any mismatch, with a screenshot if useful.

## Important Code

Read these seven files in this order:

1. `frontend/src/main.tsx`: `createRoot` mounts React into index.html's root.
   StrictMode wraps the application to expose unsafe lifecycle side effects.
2. `frontend/src/App.tsx`: `BrowserRouter/Routes/Route` are navigation, not
   backend API routes; Home composes the shell and BackendStatus.
3. `frontend/src/types/api.ts`: HealthResponse and the backend validation
   envelope keep the browser aligned with the real Python contract.
4. `frontend/src/api/client.ts`: read getBaseUrl, ApiError, apiFetch and
   getHealth. They separate configuration, transport and runtime health validation.
5. `frontend/src/components/BackendStatus.tsx`: read the discriminated state
   union, effect cleanup and retry. Old requests must not update a new mount.
6. `frontend/src/api/client.test.ts`: executable contracts for errors,204,
   environment boundaries and cancellation; not private-state tests.
7. `frontend/vite.config.ts`: React transform and Vitest jsdom setup.
   AppleDouble exclusion matters because the workspace is on an external disk.

## Concepts to Understand

1. **React**: 把界面拆成可组合组件。这里 App 组合页面，BackendStatus 单独显示请求状态。
   React 不接管 SQL、权限或费用计算；这些仍由现有 FastAPI 后端负责。
2. **SPA**: 浏览器先加载一个 HTML 入口，React 更新其中的界面。切换到 Not Found
   不需要每次向服务器下载另一份完整网页，但 API 请求仍是真实 HTTP 请求。
3. **Vite**: 开发时提供本地服务器和源码转换，修改代码可以快速更新；
   构建时生成可部署的 dist。它不是 FastAPI，也不是 PostgreSQL。
4. **TypeScript**: 编译时检查类型，例如 status 只能是约定值，错误需要先缩小 unknown。
   类型在运行时不存在，因此 getHealth 仍检查真实 JSON，不能只写一个类型断言。
5. **Component**: 返回 JSX 的函数。BackendStatus 把一块界面与相关请求状态放在一起，
   App 不需要知道底层 fetch 的细节。
6. **Props**: 父组件传给子组件的只读输入。当前 BackendStatus 没有必要接收自定义 props；
   Route 的 path/element 和 Link 的 to 是当前代码中实际使用的 props。
7. **State**: React 记住的、改变后会触发渲染的数据。state 保存请求状态，
   attempt 增加一次就触发一次重新检查；它们不是持久数据库。
8. **Effect**: 渲染后与外部系统同步。useEffect 发送 HTTP 请求，
   cleanup 中 abort 取消旧请求，避免退出页面后接受过期结果。
9. **Lifecycle**: 组件挂载、更新、卸载。这里挂载时检查，点击 Retry 更新 attempt 后
   重新检查，卸载时清理。StrictMode 在开发期额外执行 setup/cleanup，帮助发现副作用问题；
   保留它，不依赖请求“只发生一次”保证业务安全。
10. **API Client**: 集中重复的 URL/headers/解析/错误处理。页面只调用 getHealth；
    后续认证也应在同一个传输边界扩展，避免每页各自拼接 Bearer header。
11. **CORS**: 后端用响应头告诉浏览器哪些跨域页面可以读取响应。
    curl 通了不能单独证明浏览器通了，所以同时检查真实 Chrome 和 CORS headers。
12. **Origin**: scheme、host、port 的组合。127.0.0.1:5173 与127.0.0.1:8000
    端口不同；localhost 与127.0.0.1 主机名也不同，所以要明确列入配置。
13. **Environment Variable**: 把地址等环境差异从代码移出。这里 Vite 读取 frontend/.env
    或进程环境，backend 的根目录 .env 是另一套配置，不会自动互相代替。
14. **VITE_* 不是 Secret**: 构建工具会把值写入浏览器可下载的 JS。
    后端地址可公开，JWT_SECRET_KEY 和数据库密码绝不能放进去。
15. **Build vs Dev Server**: dev 帮助本地快速开发；build 先 tsc 检查类型再打包 dist。
    构建成功不表示已部署、完成 CORS 配置或数据库健康。
16. **Client-side Routing**: BrowserRouter 根据地址选择 React 组件；
    Link 更新地址与页面。正式部署需要 HTML fallback，否则直接访问深层路径可能404。

## Interview Questions

1. **Why React?** 组件化适合逐步接入共享行程产品；这里先把连接状态独立成组件，
   不为基础页引入复杂全局状态。
2. **Why TypeScript?** 在调用处发现契约和状态错误；严格类型不替代运行时 JSON 校验。
3. **What does Vite do?** 本地开发服务、React 转换、环境变量注入与生产打包。
4. **What is an SPA?** 一个 HTML 入口由 React 更新界面；不是不需要服务器。
5. **How communicate with FastAPI?** Component -> getHealth -> apiFetch -> fetch ->
   GET /health -> 校验 status -> 更新界面。
6. **Why centralized client?** URL、headers、HTTP 和网络错误规则只维护一处。
7. **How configure different URLs?** 配置 VITE_API_BASE_URL；开发重启，生产重新构建，
   同时让后端 CORS 匹配实际前端 origin。
8. **Why no VITE secrets?** 浏览器能下载和检查构建内容；客户端不能保守服务器签名密钥。
9. **What is CORS?** 浏览器跨 origin 读响应的规则，不是身份认证或资源授权。
10. **Why do5173 and8000 differ?** 端口是 origin 的一部分；同一台机器不代表同源。
11. **How handle failures?** ApiError 区分网络/超时/HTTP/配置/响应错误，UI 显示 Unavailable
    与 Retry；没有自动重试写请求。
12. **Loading vs error?** Loading 表示等待结果，error 表示一次尝试失败并提供恢复操作；
    10秒超时防止无限等待。
13. **What does StrictMode do?** 开发期额外检查渲染和 effect cleanup；
    AbortController 与忽略旧响应让重复 setup/cleanup 安全。
14. **What happens on build?** tsc -b 检查工程，再由 Vite 输出 dist；
    环境值在此阶段固化，命令不部署任何服务器。
15. **How add JWT next?** Step13 审查存储安全后建立认证状态与集中 Bearer 注入，
    再接入注册/登录/me；本阶段没有提前选择 localStorage 或 cookie。
16. **Why health rather than ready or me?** health 测 HTTP 连接，不依赖数据库或 token，
    因此适合尚未实现认证的前端基础验收。

## Problems Encountered

- Initial patch attempted delete/add of the same file in one operation; the
  tool rejected it without changes. Split replacement patches.
- Early checks found missing npm scripts and TypeScript parameter-property
  syntax incompatible with the scaffold's erasableSyntaxOnly option.
  Added scripts and explicit ApiError fields.
- External-disk `._*.test.*` were discovered as tests and failed with null
  characters. Excluded `**/._*` in Vitest, preserving default exclusions.
- Latest scaffold used Oxlint rather than required ESLint. Replaced it and
  removed the unused dependency. ESLint now passes.
- Browser connector reported unsupported auth. Native Chrome UI successfully
  demonstrated Connected; later user interaction stopped further automation.
- npm warned about optional fsevents install-script approval. No blanket approval
  was granted; dev server/tests/build ran successfully with the installed setup.
- Git has no initial commit, so diff-stat is empty although files exist.
  Used explicit inventory, check-ignore and backend hash comparison instead.

## Known Limitations

User visual/mobile/outage acceptance remains pending. No full E2E framework,
polling, auth, business UI, global state library, external images or deployment.
Browser support currently assumes modern AbortSignal timeout/any APIs.
Generic successful response types are not global runtime schema validation.
`/health` does not prove PostgreSQL, readiness or authentication.

## RECORD.md

Step12 entry appended using AGENT's required headings, with this review for
the detailed reference inspection, seven-file reading guide,16 concepts and
16 interview Q&As. Earlier development records are not rewritten.

## Git Status

Repository still has no commits; project files are untracked. No commit was
created. node_modules, dist, coverage and real frontend .env are ignored.
`.env.example`, source, package.json and package-lock.json are eligible to track,
but are not claimed committed. No yarn/pnpm lockfile exists.

## Next Step

Step 13 - Authentication UI + API Integration, after Step12 user acceptance.
Recommended only; not started.
