# Finance Manager — 个人财务管家 MVP

## 项目简介
24/7 部署在 VPS 上的个人财务后端:
- 浏览器(电脑/手机)访问 Web UI(Next.js + shadcn/ui)
- 上层 Agent(OpenClaw 小龙虾 / Hermes Agent 爱马仕)通过 **MCP 协议** 读写数据
- **后端零 LLM 依赖** —— 所有 AI 推理在 Agent 那侧

## 关键文档(按阅读顺序)
1. `docs/superpowers/specs/2026-05-08-finance-manager-mvp.md` — **整体 spec**(11 个 lock 的决策、数据模型、去重算法、MCP 工具集)
2. `docs/superpowers/plans/2026-05-08-mvp-overview.md` — **5 切片地图** + 全局 DoD + slice A 遗留问题登记 + 命名规约
3. `docs/superpowers/plans/2026-05-08-mvp-slice-X-*.md` — 各切片详细 plan(slice A 已存在,作为后续切片的写作体例参考)

## 5 切片进度
- ✅ **A. 数据库基础**(2026-05-08 完成,merged to main,DoD verify ALL PASS)
- ✅ **B. 4 个账单解析器**(2026-05-09 完成,DoD verify ALL PASS;含 slice A 遗留 I-1/I-3 修复)
- ✅ **C. 导入流水线 + 去重 + 分类 + REST API**(2026-05-09 完成,DoD verify ALL PASS;含 4 项遗留 fix:B-poly-1/2、I-5、Rec #5)
- ⏳ **D. Web UI**(下一步,5 大板块,响应式)
- ⏳ **E. MCP server(10 工具)+ 部署**(Caddy + Cloudflare DNS-01,端口 8443/9443)

## 标准工作流(每个新切片)
1. 起 `slice-X-NAME` 分支(从 main):`git checkout -b slice-b-parsers`
2. 用 `superpowers:writing-plans` 技能写详细 plan(参考 slice-a-database.md 的体例)
3. 用 `superpowers:subagent-driven-development` 跑实施(implementer + spec reviewer + code quality reviewer)
4. 切片完成 → `superpowers:finishing-a-development-branch` 决定 merge 策略(slice A 选了 fast-forward 保留 commits)

整体 brainstorming 已完成,后续切片**不要再做** brainstorming;有疑问回 spec 找答案。

## 环境与命令规约
- **OS**:Windows 11 + PowerShell 7(Bash 工具也可用)
- **Backend Python**:3.11(venv 在 `backend/.venv/`,**不要用全局 3.14**;用 `py -3.11 -m venv .venv` 创建)
- **Frontend Node**:20+(切片 D 用)
- **Docker**:用 `docker-compose`(横线版,**不是** `docker compose` 子命令 —— 用户机器 `~/.docker/config.json` 未注册 cli-plugins 路径)
- **`.env`**:在仓库根 `finance-manager/.env`(被 `.gitignore`),**不**在 `backend/`。Settings 用 `Path(__file__).parent.parent.parent.parent / ".env"` 绝对路径解析,任何 cwd 都能跑
- **Postgres**:容器内 5432,本机 venv 连 `localhost:5432`,容器间互连用 host `db`
- **commit 规约**:`feat / fix / refactor / docs / test / chore` 前缀;中英文混排但代码术语必英文;每步立即 commit 不批量

## 遗留问题(slice D/E 处理)

slice C 已闭环 4 项(B-poly-1/2、I-5、Rec #5),后续切片如有新 polish 在 overview.md 已知遗留问题段累积。

其余 overview.md 中登记的低优先级条目(I-4、M-1 至 M-6、B-poly-3/4)留给后续切片处理。

## 真实账单样本(slice B 解析器测试用,GBK/PDF/xlsx 都已被验证可读)
- 支付宝 CSV:`C:\Users\WINDOWS\Desktop\财务记录\alipay_record_20260326_2219\alipay_record_20260326_2219_1.csv`(**GBK** 编码,跳前 4 行元信息,16 列)
- 微信 xlsx:`D:\Download\IDM\微信支付账单流水文件(20251226-20260326)——【解压密码可在微信支付公众号查看】\微信支付账单流水文件(20251226-20260326)——【解压密码可在微信支付公众号查看】.xlsx`(跳前 17 行,11 列,关键"支付方式"列含底层卡)
- 交行借记卡 PDF:`C:\Users\WINDOWS\Desktop\财务记录\交通银行交易流水(申请时间2026年03月26日22时25分06秒)\交通银行交易流水(申请时间2026年03月26日22时25分06秒).pdf`(13 页,6 列)
- 建行信用卡 PDF:`C:\Users\WINDOWS\Desktop\xykmx_20260508202125\xykmx_20260508202125.pdf`(9 列,**含外币 + 银联还款入账 + 财付通/支付宝前缀**)

## 仓库状态
- 本地 git 仓库,**无 remote**(单人项目)
- main 分支 68 commits(2 brainstorm/spec + 22 slice A + 19 slice B + 25 slice C)
- DoD 验证脚本:slice A 是 `backend/scripts/verify_slice_a.ps1`(从 finance-manager/ 根跑);后续切片各自添加 `verify_slice_X.ps1`
