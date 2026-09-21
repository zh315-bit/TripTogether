# Step 13 - Authentication UI + API Integration

## Completed

Implemented `/register`, `/login`, protected `/account`, centralized auth state,
sessionStorage access-token persistence, `/me` verification, local logout and
safe failure/loading states. No Trip UI or Step14 work.
Implementation and automated/live integration checks passed. Step13 user browser
acceptance remains pending. Step12 connectivity is user-accepted, as confirmed
in the Step13 task; earlier historical pending entries remain unchanged.

## OpenTrip Authentication Reference Review

Reviewed the existing OpenTrip reference at
`cfc78a04d0eeba3daaec4b755b110d89938ae4fc`:

- `apps/web/src/features/auth/AuthForm.tsx`: labels, pending submission,
  autocomplete and mode-specific feedback.
- `apps/web/src/pages/auth/AuthPage.tsx`: focused, narrow auth form layout.
- `apps/web/src/app/auth-session-state.ts`: resolving a session before showing
  authenticated content.
- `apps/web/src/shared/auth/index.ts`: separation of session and API concerns.

Referenced ideas, not source/CSS/branding/assets. Did not adopt Better Auth,
cookies, OAuth, CAPTCHA, OTP, MFA, reset flows or its large multipurpose form.
TripTogether uses its existing JWT Bearer contract and a much smaller form.

## Backend Auth Contract

Source: `app/api/auth.py`, `api/dependencies.py`, `schemas/user.py`,
`services/authentication.py`, `core/security.py`, and `api/errors.py`.
The requested `core/errors.py` does not exist; actual errors live in `api/errors.py`.

| Action | Request | Success | Important failures |
| --- | --- | --- | --- |
| POST `/api/v1/auth/register` | JSON `{username,email,password}` | 201 `{id,username,email,created_at}` | 409 username/email duplicate;422;503 |
| POST `/api/v1/auth/login` | JSON `{email,password}` | 200 `{access_token,token_type:"bearer"}` | 401 INVALID_CREDENTIALS;422;503 |
| GET `/api/v1/auth/me` | `Authorization: Bearer <access_token>` | 200 same User fields | 401 invalid/expired/missing/deleted user;503 |

`id` is integer, `created_at` is an ISO datetime string. No password/hash in
User responses. Registration does not issue JWT or automatically log in.
Login uses JSON, not OAuth form data. Passwords are never trimmed.
Username: trimmed ASCII letters/digits/underscore,1-50 characters.
Registration password8-128; login password1-128. Email normalized by backend.
Client performs basic UX checks; backend remains authoritative.
Errors: `{error:{code,message,details:[{loc,msg,type}]}}`.
Duplicate codes are USERNAME_ALREADY_EXISTS and EMAIL_ALREADY_EXISTS.
Login failures retain the same generic message for unknown email/wrong password.

## Files Changed

New:

- `frontend/src/types/auth.ts`: request, token and user types.
- `frontend/src/api/auth.ts`: register/login/me adapters and runtime guards.
- `frontend/src/auth/tokenStorage.ts`: the only token storage access point.
- `frontend/src/auth/AuthContext.tsx`: AuthProvider, useAuth and session actions.
- `frontend/src/auth/ProtectedRoute.tsx`: route guard and restore failure UI.
- `frontend/src/components/AuthForm.tsx`: shared form, labels, validation and errors.
- `frontend/src/components/LogoutButton.tsx`: coordinated logout/navigation.
- `frontend/src/pages/LoginPage.tsx`, `RegisterPage.tsx`, `AccountPage.tsx`.
- `frontend/src/api/auth.test.ts`, `auth/AuthContext.test.tsx`,
  `pages/Authentication.test.tsx`, `auth/realAuth.test.tsx`.
- `frontend/scripts/verify_auth.py`: opt-in real HTTP/PostgreSQL integration runner.
- `docs/step13-review.md`: this report and learning material.

Modified: `frontend/src/api/client.ts`, `App.tsx`, `App.css`,
`api/client.test.ts`, `test/setup.ts`, `frontend/README.md`, root `README.md`,
`AGENT.md` (status/storage decision), `docs/client-integration.md`,
`docs/known-limitations.md`, and `RECORD.md`.

Local only: generated the previously missing JWT_SECRET_KEY in ignored root
`.env`, with no displayed value and no overwrite of an existing key.
No backend Python/model/migration/API architecture or dependency changes.
No new npm dependencies or package-lock changes in this step.

## Authentication Architecture

```text
Login/Register Page
        |
Auth Layer (Context + auth API)
        |
API Client (explicit Bearer on authenticated calls)
        |
FastAPI -> SQLAlchemy -> PostgreSQL
```

Public register/login/health calls have no automatic Bearer header.
`apiFetch` accepts an optional accessToken; it knows nothing about React Router.
AuthProvider's `request` wrapper centralizes authenticated401 invalidation.
Current user lookup is an auth adapter taking an explicit candidate token.
There is no hidden global callback or unrelated state library.

## Token Storage Decision

Only the access token is saved, under `triptogether.accessToken` in sessionStorage.
No password, User object or signing key is persisted by application code.
sessionStorage survives a reload in the same tab and normally has a shorter
lifetime than localStorage. Same-origin JavaScript, including XSS, can read it.
It is not equivalent to HttpOnly cookies and is not production-grade session security.

Tab/session behavior is not a revocation guarantee: opener-created/duplicated
tabs may inherit a copy; browser session/tab restoration can preserve state.
Tabs do not implement synchronized global logout. Log out explicitly on shared
devices. Same-tab restore was tested; actual browser close/reopen behavior still
needs user verification and can vary with browser settings.

## Registration Flow

Labelled username/email/password fields -> basic validation -> authApi.register
->201 User -> `/login` with an Account created message. No auto-login.
Submission disables controls and shows Creating account...
The field's password is cleared when sending; request payload references are
discarded after completion. No password in navigation state or storage.
409 maps to the relevant field;422 details show beside known fields.
No duplicate-write retry after transport failure: a timed-out registration may
already have committed.

## Login Flow

JSON credentials -> TokenResponse guard -> sessionStorage -> `/auth/me` ->
User guard -> authenticated state -> `/account`.
User identity is never constructed from a decoded JWT payload.
Signing in... lasts until `/me` resolves, not merely until a token is returned.
If candidate verification fails, remove that login candidate and show a safe
error; submitting again requires re-entering the password.

## Auth Restore Flow

On mount: read storage, then verify a saved token using `/me`.
No token -> anonymous. Valid token -> authenticated User.
401 -> clear storage/user and require login.
Network/503 -> keep the token pending, show retry, deny protected content.
This avoids confusing an outage with invalid credentials.
Storage failures fail closed with a readable message.
StrictMode cleanup aborts old requests. Logout cancels the active auth operation,
and aborted results are ignored so late responses cannot restore an old login.
Restoring state is authoritative only once the backend confirms it.

## Protected Route

Loading -> Checking session...
Restore failure -> retry or local logout.
Anonymous -> replace with `/login`.
Authenticated -> render nested `/account`.
Login/register pages send already-authenticated users to `/account`.
Post-login destination is fixed `/account`: no untrusted return URL to validate.
The guard is UX only; FastAPI still verifies JWT and resource authorization.

## Logout Flow

The shared LogoutButton clears the token/User and navigates home in a coordinated
React transition, avoiding a competing guard redirect.
No nonexistent logout endpoint is called.
JWT logout currently means removing the client-held access token.
The server does not revoke individual tokens; stolen copies remain valid until
expiration or another backend condition rejects them.

## Error Handling

ApiError carries status/code/message/details; forms use backend-safe messages
and known field details as React text, never raw HTML or an object stringify.
An authenticated401 is handled in AuthProvider, not by Router code inside fetch.
A public login401 remains form feedback. Protected503 does not log out the user.
Cancel/timeout/network errors are distinct; old requests cannot clear a newer
auth operation. No refresh loop or automatic credential resubmission.

## Security Review

- Passwords remain in input/request memory only; cleared on submission, never
  stored in web storage, logs, URLs, test snapshots, records or Git as credentials.
- No raw JWT in rendered UI, URL, logs or docs. Unit tests use non-JWT dummy tokens.
- Only sessionStorage contains the current access token; localStorage is unused.
- VITE config still contains only the public API origin. Backend signing key
  stays in ignored server `.env`.
- Auth responses checked structurally before use; no client-side password
  hashing, JWT signature verification or client-invented User.
- Explicit Bearer assembly in the API layer. URL backslashes/double slash paths
  rejected; redirects fail rather than following a request carrying credentials.
- Requests omit cookies. CORS remains explicit origin configuration, not auth.
- Frontend storage errors do not grant authenticated UI.
- React text escaping is used for errors. This is not a general XSS defense
  guarantee; dependencies, CSP, HTTPS and deployment controls remain important.

## Tests

Normal `npm test`: **62 passed,0 failed,1 opt-in live test skipped**.
The separate live run: **1 passed,0 failed**.
Coverage includes:

- Existing shell/health loading/success/error, malformed JSON,204 and network handling.
- Register fields, payload, navigation, duplicate username/email,422,503 and local validation.
- Login success, failed credentials, network/503, loading through `/me`.
- Bearer injection vs public requests and malformed auth responses.
- No-token, restore valid/invalid, storage failure, logout and late-response races.
- Protected routes, session waiting, refresh-style remount, local logout navigation.
- Authenticated401 clears session;503 preserves it.
- HTML-like validation errors render as text.

Live case is not silently run by the normal test command because it writes
a disposable development account and requires real PostgreSQL.

## Backend Integration

`frontend/scripts/verify_auth.py` creates a private temporary Uvicorn process on
a free loopback port, with a generated in-memory signing key and existing DB.
The real frontend components/API client run in jsdom with actual fetch, no fake
API responses. It records only path/status for assertions, never credentials.

Verified: registration201, login200, me200; invalid password401,
missing token401, invalid token401. Also verified restore across a React remount,
logout and protected-route redirection. Bearer CORS preflight passed.
Each run used a unique generated identity; **one test user removed** with an
exact username+email predicate, and the temporary server stopped in finally.
No existing user was deleted. No test identity/password/token remains in files.
This is real UI/API/PostgreSQL integration, not a claim of browser E2E acceptance.

The user's existing backend initially returned `/ready`503 because local
JWT_SECRET_KEY was absent. After generating only that missing local setting,
the same backend returned `/ready`200 without changing Python code.

## Lint

`npm run lint`: passed, no ESLint errors/warnings.

## Build

`npm run build`: passed, including TypeScript. The live test file explicitly
references installed Node typings; no Node runtime imports in application code.

## Backend Regression

Executed with real PostgreSQL:

```bash
cd /Volumes/Elements/TripTogether/backend
RUN_POSTGRES_TESTS=1 /private/tmp/triptogether-step1-venv/bin/python -m pytest -q \
  tests/test_authentication.py tests/test_registration.py tests/test_jwt.py \
  tests/test_health.py tests/test_api_contract.py
```

**102 passed,0 failed**. These existing tests isolate schemas/transactions.
Backend source digest remains
`e830138090ee225eb4216191794df6af0910d651bf0dbca8181ba72f2113dde4`.
No full538-test regression claimed.

## Manual Verification

Existing services were not killed. Current Vite URL: `http://127.0.0.1:5173`.
When starting afresh, use two terminals (do not launch duplicate port listeners):

```bash
# Terminal 1
cd /Volumes/Elements/TripTogether/backend
source /private/tmp/triptogether-step1-venv/bin/activate
CORS_ORIGINS='["http://127.0.0.1:5173"]' python -m uvicorn app.main:app --reload
```

```bash
# Terminal 2
cd /Volumes/Elements/TripTogether/frontend
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

PostgreSQL running through brew services does not need another terminal.
Confirm `/ready`200 for real auth; health alone is insufficient.

1. Visit home and click Create account.
2. Enter a disposable username/email/password, not a private reused password.
3. Confirm redirect to login and Account created feedback.
4. Log in and verify `/account` username/email.
5. Refresh: Checking session... then the same user after `/auth/me`.
6. Log out: home, anonymous navigation, no authenticated user.
7. Visit `/account`: redirected to login.
8. Check invalid password and duplicate registration feedback.
9. Check Tab/Enter, focus, disabled submit and a narrow viewport.
10. Verify actual tab-close/reopen behavior separately from page refresh.
11. Stop only your own development servers with Ctrl+C when finished.

Agent observed a readable login desktop screenshot with labels and navigation.
Further native browser automation was interrupted by concurrent user activity;
mobile and full browser workflow acceptance remain pending.
Please perform the above steps and report mismatches/screenshots. Tests do not
substitute for your browser acceptance. Accounts created manually persist;
the automatic integration script only cleans its own random identity.

## Important Code

Read these ten files:

1. `frontend/src/api/client.ts`: ApiRequestOptions and header assembly.
   Explicit accessToken enters here; no router or storage code belongs here.
2. `frontend/src/api/auth.ts`: register/login/getCurrentUser plus runtime guards.
   It translates backend JSON, never guesses identity from a token.
3. `frontend/src/auth/tokenStorage.ts`: one storage key, read/write/clear.
   This is the only production code that touches sessionStorage.
4. `frontend/src/auth/AuthContext.tsx`: restore/login/logout/request and useAuth.
   Follow the401 vs network branches and cancellation checks.
5. `frontend/src/auth/ProtectedRoute.tsx`: loading/error/anonymous/authenticated
   branching; authenticated UI is not backend authorization.
6. `frontend/src/components/AuthForm.tsx`: submit lock, labels, validation,
   safe error mapping, abort cleanup and password disposal.
7. `frontend/src/pages/LoginPage.tsx`: form -> provider -> `/account`.
   Navigation waits for the provider's complete login/me operation.
8. `frontend/src/pages/RegisterPage.tsx`: form -> register -> login success flag.
   Only a boolean goes into Router state, not password or token.
9. `frontend/src/pages/AccountPage.tsx`: displays only confirmed username/email.
   Shared LogoutButton handles local logout and navigation.
10. `frontend/src/App.tsx`: provider scope, header links and route tree.
    `/account` is nested under a single reusable guard.

## Concepts to Understand

1. **Authentication**：确认“你是谁”。这里凭邮箱密码获得 JWT，再由 `/me` 确认当前用户。
2. **Authorization**：确认“你能做什么”。未来 Trip 所有者/成员权限仍由 FastAPI 检查，
   不是前端隐藏一个按钮就安全。
3. **JWT**：后端签名的声明载体。当前内容含用户 subject 和过期时间；前端把它作为凭据发送。
4. **Bearer Token**：谁持有谁可使用的凭据。请求头是 Authorization: Bearer token，
   所以泄漏 token 的风险类似泄漏临时通行证。
5. **Access Token**：访问受保护 API 的有期限凭据。当前没有 refresh token，失效后重新登录。
6. **JWT 不是加密**：编码不是保密，payload 可以被读取。不要把密码或私密数据塞进 JWT。
7. **Signature**：让后端检查 token 是否由可信签名方签发、内容是否被篡改；
   浏览器没有签名密钥，也不代替后端验证。
8. **sessionStorage**：浏览器按 origin/page session 管理的存储；本项目只存 access token。
9. **与 localStorage 的区别**：localStorage 通常长期保留，sessionStorage 以页面会话为范围，
   刷新仍在。两者都能被同源 JavaScript 读取，都不能抵抗已发生的 XSS。
10. **有 token 不等于认证有效**：可能过期、伪造、签名密钥已更换或用户已删除；必须问后端。
11. **`/auth/me` 的作用**：验证凭据并读取数据库中的当前 User，作为 Context 的身份来源。
12. **React Context**：向 Header、页面和 guard 共享认证状态，避免每个组件维护自己的副本。
13. **Provider**：提供 Context 值并拥有生命周期。AuthProvider 启动时恢复，退出时清理。
14. **Custom Hook**：useAuth 封装 useContext，调用者获得同一份状态/actions，
    Provider 外使用会明确报错。
15. **Protected Route**：等待身份确认、拦截匿名导航。它改善 UX，但不是安全边界。
16. **Client-side Redirect**：React Router 在浏览器中切换路径，登录去 account，退出回 home；
    不是 FastAPI 发出的 HTTP redirect。
17. **401 与403**：401 表示身份凭据不可接受；403 通常表示身份已知但权限不足。
    TripTogether 的许多资源权限故意返回404，不能一律当作 token 失效。
18. **为什么登录不透露邮箱存在性**：区分“邮箱不存在”和“密码错”方便枚举账号。
    登录保留统一消息；现有注册409确实区分重复字段，这是仍需记录的后端产品取舍。
19. **XSS 与 token**：恶意同源脚本能读 sessionStorage 并冒用请求；
    不输出 raw HTML 是基础措施，不意味着已解决全部 XSS/生产安全。
20. **前端不验证密码哈希**：Argon2 校验必须由可信后端执行，浏览器不应收到数据库哈希。
    前端校验长度改善体验，不能代替认证；传输保密还需要生产 HTTPS。

## Interview Questions

1. **How does authentication work?** JSON 登录取得 JWT，用 Bearer 调 `/me`，确认 User 后更新 Context；
   注册是独立操作。
2. **Why JWT?** 沿用现有 FastAPI Bearer 契约，不为 UI 替换认证架构。
3. **Where is the access token stored?** sessionStorage 的单一项目键，由 tokenStorage 模块封装。
4. **Why sessionStorage rather than localStorage?** 避免默认长期持久登录，符合无 refresh token 的简单 MVP。
5. **Is it completely secure?** 否，同源 JS/XSS 能读，标签恢复等行为也不能当作撤销。
6. **What happens after login?** token 校验形状、保存、请求 `/me`、确认用户，再跳转 account。
7. **Why call me?** token payload 不能提供可靠的完整当前用户；后端还检查用户是否仍存在。
8. **How do protected routes work?** 等待恢复；失败可重试；匿名去 login；认证成功才显示 Outlet。
9. **What happens when JWT expires?** 后端受保护请求返回401后清理本地会话，要求重新登录；
   本阶段不持续轮询、不 silent refresh。
10. **Authentication vs authorization?** 身份与操作权限不同；Context 显示身份，资源权限由后端执行。
11. **Why no frontend password hash?** 浏览器不拥有可信哈希校验环境，服务端 Argon2 校验是权威。
12. **How attach Bearer?** Auth layer 显式把 token 交给 apiFetch，由统一 Headers 构造添加。
13. **How handle401?** 受保护请求由 Provider 清会话；公开 login 的401仅表单反馈，不让 API 层导航。
14. **How survive refresh?** sessionStorage 保留 token，新的 Provider 用 `/me` 重新验证后恢复 User。
15. **What happens on logout?** 中止认证操作、删项目 storage 键、清 User、导航首页。
16. **Does logout revoke the server JWT?** 不会；当前没有黑名单或 logout API。
17. **Current limitations?** 无 refresh/revocation/OAuth/MFA/验证邮件/重置密码；
   sessionStorage 暴露于 XSS，且没有跨标签统一退出。
18. **Production improvements?** 后续评估 HTTPS/CSP、XSS 防护、限流、受审查的会话/刷新与撤销设计；
   不在本步擅自实现。
19. **How avoid leaking tokens?** 不渲染、不记录、不放 URL/Git/VITE 配置；只通过明确 API header 发送。
20. **How tested?**62个前端单元/组件测试，加真实 HTTP/PostgreSQL 前端流程，102个后端认证契约回归；
   另有桌面截图检查，用户浏览器验收待完成。

## Problems Encountered

- Backend health was200 but readiness503: missing local JWT_SECRET_KEY.
  Generated a random key only when absent, using dotenv's structured setter;
  did not print it or overwrite an existing credential. Existing backend then ready200.
- Logout initially landed on login because guard and navigation raced.
  Shared LogoutButton batches both in a React transition; regression now passes.
- Live test initially lacked Node type context and assigned an unused password
  value. Added a test-only Node type reference and removed the unused assignment;
  no application dependency changed.
- Task mentioned a nonexistent core/errors.py; read actual api/errors.py.
- Native Chrome automation encountered concurrent user activity; did not claim
  mobile/full browser acceptance or interfere with user actions.
- No tracked Git baseline; verified backend hash and explicit file inventory.

## Known Limitations

No refresh token, server-side token revocation, OAuth, email verification,
password reset, MFA, trip UI, deployment or production-grade security claim.
sessionStorage is exposed to XSS; tab restore/copy behavior and cross-tab logout
are limitations. No background expiry polling. Registration duplicate feedback
can reveal existing accounts even though login messages do not.
Live tests use a real backend but jsdom is not a real browser CORS/layout engine.
Some errors (CORS vs network) cannot be distinguished by fetch alone.

## RECORD.md

Appended the Step13 entry with goal, contract, files, code guide, architecture,
storage/security decisions, tests, PostgreSQL cleanup, manual acceptance,
problems, learning material and one next step. No historical entry rewritten.

## Git Status

No commit created; repository still has no tracked baseline. Real .env files,
node_modules, dist and coverage are ignored. Only fake tokens/disposable test
input literals occur in unit tests; no generated JWT/password/key was written
to source/docs. Generated local JWT_SECRET_KEY stays in ignored root .env.

## Next Step

Step 14 - Trip Dashboard + Trip Management, after Step13 user acceptance.
Recommended only; not started.
