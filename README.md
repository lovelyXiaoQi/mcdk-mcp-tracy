# mcdk-mcp-tracy

> 一个 MCP 服务器：直接从**运行中的**网易我的世界基岩版 MOD 里，拿到**每个函数的耗时**，
> 用来做代码 review、定位性能热点、验证优化效果。

它驱动游戏客户端内嵌的**原生 Tracy server**（监听 TCP 8086，就是 `tracy-profiler.exe` GUI
连的那个端口），用自带的 `tracy-capture` + `tracy-csvexport`（见 `bin/`）抓取一小段 trace，
归约成**精简的函数耗时排行**返回给 AI。原始逐帧数据不会进 AI 上下文。

它能帮你回答这些问题：

- 这段玩法里，**哪些函数最耗时**？（self / total / 调用次数）
- 我改完代码后，**那个热点函数真的变快了吗**？（前后 diff，按毫秒量化）
- 掉帧时 **FPS 分布**怎么样？

> **为什么走原生 Tracy？** 网易引擎的 Python 侧 CPU profiler（`_utility.getCpuFrameData`）
> 在绝大多数**正式发布版**客户端里**没有绑定**（它是受灰度控制的内部能力）。但同一个客户端
> 通常**内嵌了原生 Tracy server**（8086）——所以本服务器走原生路径，无需该 Python 绑定、
> 无需白名单、也不依赖画质/cocos 等级。

---

## 工作原理（一张图）

```text
# 函数耗时（主路径）—— 不经游戏 Python，直连原生 Tracy
AI (Claude) --MCP/stdio--> mcdk-mcp-tracy --TCP 8086--> 游戏内嵌的原生 Tracy server
                                  └─ bin/tracy-capture.exe + tracy-csvexport.exe

# 帧率 / jank（辅助路径）—— 经 MCDK 注入 get_Fps()
AI --MCP/stdio--> mcdk-mcp-tracy --MCP/SSE--> MCDK(mcdk.exe) --execute_code--> 游戏(Python2)
```

- **函数耗时**走原生 Tracy（8086），**不经过 MCDK**：只要游戏在跑、8086 在听、`bin/` 里的
  CLI 在，就能抓。
- **采样窗口内你得让游戏真的在跑**（动起来、触发你要测的逻辑）：Tracy 记录的是窗口内实际
  执行的 zone，静止画面 = 没什么数据。
- 只有 `tracy_jank_fps` 走 MCDK，所以那一个工具才需要游戏由 MCDK 启动、且 MCP 已开。

> `bin/tracy-capture.exe` / `bin/tracy-csvexport.exe` 取自 Tracy **v0.11.1** 官方 Windows 包，
> **版本须与游戏内嵌的 Tracy client 一致**（协议版本敏感）；换游戏版本时同步替换。

---

## 前置条件

1. **游戏在运行**，且客户端内嵌的原生 Tracy server 在监听 8086（用 `tracy-profiler.exe` GUI
   能连上、看到 `MAIN_THREAD` / `MC_SERVER` 即可确认）。
2. `bin/tracy-capture.exe` 和 `bin/tracy-csvexport.exe` 存在（随仓库附带；也可用 `TRACY_BIN_DIR`
   指向别处）。
3. **（仅 `tracy_jank_fps` 需要）** 游戏由 MCDK（`mcdk.exe`）启动，且工程 `.mcdev.json` 里开了 MCP：

   ```json
   { "mcp_server_config": { "enabled": true, "server_ip": "localhost", "server_port": 19133 } }
   ```

4. **Python 3.10+**（开发用 3.13）。推荐装 [`uv`](https://docs.astral.sh/uv/)。

---

## 安装

```bash
# 1) 拿到代码后，在项目目录装依赖并建虚拟环境
uv --directory <path>/mcdk-mcp-tracy sync

# 2) 自检（不需要游戏，应输出 36 passed）
uv --directory <path>/mcdk-mcp-tracy run pytest -q
```

`uv sync` 会在 `mcdk-mcp-tracy/.venv/` 下建好环境并把本包装成可用模块。

---

## 注册到 Claude Code

### 方式 A：全局（user scope，所有项目可用）—— 推荐

```bash
claude mcp add mcdk-mcp-tracy --scope user -- \
  "<path>/mcdk-mcp-tracy/.venv/Scripts/python.exe" -m mcdk_mcp_tracy \
  --stdio --mcdk-url http://127.0.0.1:19133
```

- 直接用 venv 里的 `python.exe`，不依赖 PATH，最稳。
- `--mcdk-url http://127.0.0.1:19133` 写死 MCDK 端口（仅 `tracy_jank_fps` 用得到；函数耗时
  抓取不经 MCDK，与端口无关）。
- 注册后**新开一个会话**才会出现 `mcp__mcdk-mcp-tracy__*` 工具（当前会话不会热加载）。

### 方式 B：跟着 MOD 工程走（按 `.mcdev.json` 自动找端口）

```jsonc
// 放进全局 ~/.claude.json 的 mcpServers，或工程根目录的 .mcp.json
"mcdk-mcp-tracy": {
  "type": "stdio",
  "command": "<path>/mcdk-mcp-tracy/.venv/Scripts/python.exe",
  "args": ["-m", "mcdk_mcp_tracy", "--stdio", "--project-dir", "C:/你的MOD工程目录"]
}
```

> 端口解析优先级：`--mcdk-url` > `--mcdev-json <文件>` > `--project-dir <目录>/.mcdev.json` > 环境变量 `MCDK_MCDEV_JSON` > 从当前工作目录向上找 `.mcdev.json`。

卸载：`claude mcp remove mcdk-mcp-tracy --scope user`

---

## 快速上手（标准流程）

下面用工具名 + 关键参数说明，AI 会按需调用。

### 第 0 步 · 探针（每次开测先跑）

```text
tracy_status()
```

确认原生路径是否就绪。期望返回：

```json
{
  "ok": true,
  "native_tracy": { "reachable": true, "address": "127.0.0.1", "port": 8086 },
  "bin_present": true,
  "mcdk": { "url": "http://127.0.0.1:19133/sse", "note": "MCDK is only needed for tracy_jank_fps; native capture is independent" }
}
```

（要点：`ok=false` 时看 `reason`/`hint` —— `native_tracy.reachable=false` 说明游戏没起 / 没内嵌
Tracy / 端口不对；`bin_present=false` 说明 `bin/` 缺 CLI。）

### 第 1 步 · 制造负载 + 抓取排行

先在游戏里**触发你要测的玩法**（站到卡顿场景、开打、刷实体、跑你的机器……），然后：

```text
tracy_native_capture(seconds=8, name_contains="YourMod", label="before")
```

- `name_contains` 可选，按 `"函数名 @ 源文件"` 过滤（如你的 mod 脚本前缀），只看自己的函数；
  **全量数据仍会存进 capture**，过滤只影响返回的 inline top-N。
- 原生 Tracy **自动抓全部 zone，无需白名单**。

返回（已按 self 耗时降序）：

```json
{
  "ok": true,
  "capture_id": "cap-1",
  "label": "before",
  "source": "native_tracy",
  "frames": 2632,
  "zones": 645899,
  "unique_functions": 209,
  "unit": "ms",
  "total_self_ms": 327.0,
  "top": [
    { "name": "onRenderTick @ YourMod.Client.Main", "self_ms": 134.2, "total_ms": 328.1, "calls": 2628 }
  ]
}
```

（要点：窗口内必须有真实负载；返回为空看 `warning`。记下 `capture_id`，diff 要用。）

### 第 2 步 · 细看某些函数的成本

```text
tracy_get_function_costs(capture_id="cap-1", name_contains="YourMod")
```

返回匹配函数的 self/total/calls —— 给你做 review 的"成本清单"。

### 第 3 步 · 改代码 + 复测

改完热点后，**用同样的负载**再抓一次，打不同 label：

```text
tracy_native_capture(seconds=8, name_contains="YourMod", label="after")
```

### 第 4 步 · diff 验证优化效果

```text
tracy_diff_captures(base_id="cap-1", new_id="cap-2", metric="self")
```

```json
{
  "ok": true, "metric": "self",
  "summary": { "base_total_ms": 86.4, "new_total_ms": 61.0, "delta_ms": -25.4, "pct": -29.4 },
  "improved": [ { "name": "YourMod.combat.update", "delta_ms": -16.8, "base_ms": 21.3, "new_ms": 4.5 } ],
  "regressed": [], "added": [], "removed": []
}
```

（`delta_ms` 为负 = 变快；目标函数出现在 `improved` 且总量 `pct` 下降，就说明优化生效。）

---

## 工具速查表

| 工具 | 作用 | 关键参数 |
| --- | --- | --- |
| `tracy_status` | **先跑**。探测原生 Tracy(8086)可达性、bundled CLI、MCDK 端点（信息性） | `address`, `port`(8086), `project_dir?` |
| `tracy_native_capture` | **核心**。从原生 Tracy(8086)抓函数耗时 top-N，存为 `capture_id`，无需白名单 | `seconds`(≤60), `name_contains`, `top_n`, `address`, `port`, `label` |
| `tracy_get_function_costs` | 从某次 capture 查指定函数/子串 | `capture_id`(必填), `names?`, `name_contains?`, `limit` |
| `tracy_diff_captures` | 前后两次 capture 按函数对比 | `base_id`, `new_id`(必填), `metric`(self/total), `top_n` |
| `tracy_jank_fps` | 帧级健康（经 MCDK）：FPS 百分位 / 抓 jank 日志 | `action`(sample_fps\|read_jank_logs), `duration_seconds`, `log_lines` |
| `tracy_list_captures` | 列出已存的 capture，方便挑 id 做 diff | 无 |

所有工具都返回结构化 JSON：成功 `{"ok": true, ...}`，失败 `{"ok": false, "reason": "...", "error": "..."}`。

---

## 要点 / 注意事项（务必读）

1. **函数耗时走原生 Tracy，不经 MCDK**：只要游戏在跑、8086 在听、`bin/` 在，就能抓；和画质、
   cocos 等级、`getCpuFrameData` 绑定都无关。
2. **采样期间要有真实负载**：Tracy 记录窗口内实际执行的 zone，游戏静止 = 没什么数据。
3. **无需白名单**：原生 Tracy 抓全部已插桩 zone（含客户端 `MAIN_THREAD` 与 `MC_SERVER` 线程）；
   用 `name_contains` 过滤你的 mod 即可。
4. **Tracy 版本必须匹配**：`bin/` 的 CLI 与游戏内嵌 Tracy client 协议版本敏感，换游戏版本时同步
   替换（当前 v0.11.1）。
5. **数据不进 AI 上下文**：大数据在服务端归约，AI 只看 top-N 和 diff，放心采。
6. **`seconds` 上限 60s**。
7. **diff 要可比**：两次 capture 用尽量一致的玩法 + 同样的 `seconds`，否则 delta 不可信。
8. **`tracy_jank_fps` 才依赖 MCDK**：它经 `execute_code` 读 `get_Fps()`，所以那一个工具需要游戏由
   MCDK 启动、MCP 已开。

---

## 排查表（按 `reason` / 字段）

| 现象 | 含义 | 怎么修 |
| --- | --- | --- |
| `native_tracy.reachable=false`（`reason=profiler_unavailable`） | 连不上 8086 的原生 Tracy server | 确认游戏在跑、内嵌了 Tracy；用 `tracy-profiler.exe` GUI 验证能否连上；检查 `address`/`port` |
| `bin_present=false`（`reason=profiler_unavailable`） | 找不到 bundled Tracy CLI | 确认 `bin/tracy-capture.exe`、`bin/tracy-csvexport.exe` 存在，或设 `TRACY_BIN_DIR` |
| `tracy_native_capture` 返回空 + `warning` | 窗口内没有负载，或 8086 没数据 | 采样时让游戏真的在跑你要测的逻辑；确认 8086 可达 |
| `mcdk_unreachable`（仅 `tracy_jank_fps`） | 连不上 MCDK（端口没开/游戏没起） | 确认游戏由 MCDK 启动、19133 在跑 |
| `bad_request` | 参数非法（如 `seconds>60`） | 按文档改参数 |
| `unknown_capture` | `capture_id` 不存在（可能被淘汰，只留最近 ~20 个） | 重新抓样拿新 id |

---

## 设计说明：为什么没有"游戏内 Profiler"工具

早期版本还提供过一条走 `_utility.getCpuFrameData` 的"游戏内 Profiler"路径
（`tracy_capture_and_rank` / `tracy_set_profiled_modules` / `tracy_start` / `tracy_stop`）。
实测在正式发布版客户端上，`_utility` **没有** `getCpuFrameData` / `enableCpuProfiler` 绑定
（CpuProfiler 是 1% 灰度的受控功能），那条路径**不可用**——故已移除。`tracy_jank_fps` 里
依赖 `setSimpleProfilerEnable` 的开关 action 同理（实测返回 `False`）也已移除，只保留可用的
`sample_fps` 与 `read_jank_logs`。函数级耗时统一走原生 Tracy。

---

## 开发

```bash
uv --directory mcdk-mcp-tracy run pytest -q   # 36 passed
```

测试覆盖：`.mcdev.json` 发现、原生 Tracy CSV 归约/统计解析、diff、capture store、FPS 采样编排
（假客户端）、`execute_code` 结果解析、注入片段的 Py2 语法 sanity。

完整工作流策略见 [skills/mcdk-tracy-profiling/SKILL.md](skills/mcdk-tracy-profiling/SKILL.md)。
