---
name: mcdk-tracy-profiling
description: 用 mcdk-mcp-tracy 对运行中的网易我的世界基岩版 MOD 做函数级 CPU 性能分析与优化验证。函数耗时通过游戏内嵌的原生 Tracy server(TCP 8086)抓取，无需白名单/画质要求，也不经 MCDK。做性能 review、定位热点函数、验证优化效果时使用。
---

# MCDK Tracy 性能分析工作流

`mcdk-mcp-tracy` 通过游戏客户端内嵌的**原生 Tracy server**（监听 TCP 8086，即 `tracy-profiler.exe` GUI 连的那个端口），用自带的 `tracy-capture` + `tracy-csvexport` 抓一小段 trace，归约成**每个函数的耗时**，用于 MOD 代码 review 与优化。原始数据在服务端归约，只把精简排行回传给 agent。

> **为什么走原生 Tracy**：网易正式发布版客户端的 `_utility.getCpuFrameData`（Python 侧 CPU profiler）通常**没有绑定**（受 1% 灰度控制），但同一客户端内嵌了原生 Tracy。所以本工作流不依赖该绑定、无需白名单、与画质/cocos 等级无关。

## 前置条件

1. 游戏在运行，客户端原生 Tracy server 在监听 8086（用 `tracy-profiler.exe` GUI 能连上即确认）。
2. `bin/tracy-capture.exe`、`bin/tracy-csvexport.exe` 存在，且版本与游戏内嵌 Tracy 一致（当前 v0.11.1）。
3. 仅 `tracy_jank_fps` 需要游戏由 `mcdk.exe` 启动、`.mcdev.json` 的 `mcp_server_config.enabled=true`；**函数耗时抓取不经 MCDK**。

## 核心原则

- **先探针后采样**：先 `tracy_status`，确认 `native_tracy.reachable=true`、`bin_present=true`。
- **采样期间制造真实负载**：窗口内让游戏跑代表性玩法；Tracy 记录窗口内实际执行的 zone，静止 = 没数据。
- **无需白名单**：原生 Tracy 抓全部已插桩 zone（含客户端 `MAIN_THREAD` 与 `MC_SERVER`）；用 `name_contains` 过滤你的 mod 即可。
- **用 diff 验证优化**：优化前后各采一次、打不同 `label`，用 `tracy_diff_captures` 量化收益，而非凭感觉。
- **数据不过 agent 上下文**：大数据在服务端归约；agent 只看 top-N 与 diff。

## 推荐流程

1. **探针**：`tracy_status()`
   - 通过：`ok=true`、`native_tracy.reachable=true`、`bin_present=true`。
   - 失败看 `reason`/`hint`：8086 不可达 → 游戏没起 / 没内嵌 Tracy / 端口不对；`bin_present=false` → 缺 CLI。
2. **基线采样**：制造负载 → `tracy_native_capture(seconds=8, name_contains="MyMod", label="before")`
   - 关注 `top`（按 self_ms 排序）、`frames`、`zones`、`unique_functions`。
   - `name_contains` 只过滤 inline 返回，全量仍存进 capture；返回空看 `warning`（多半负载不足或 8086 无数据）。
3. **看成本**：`tracy_get_function_costs(capture_id, name_contains="MyMod")`
   - 得到 MOD 函数的 self/total/calls —— 这就是 review 工件，定位热点。
4. **改代码 + 复测**：改热点函数 → 必要时用 game-testing MCP 的 `reload_addon_and_game` 热重载
   - 同样负载下 `tracy_native_capture(seconds=8, name_contains="MyMod", label="after")`。
5. **diff 验证**：`tracy_diff_captures(base_id=<before>, new_id=<after>, metric="self")`
   - 目标函数应出现在 `improved` 且 `delta_ms` 为负；看 `summary.pct` 总体收益。
6. **帧级交叉验证（可选）**：`tracy_jank_fps(action="sample_fps")` 前后对比 FPS 百分位（此工具经 MCDK）。

## 注意

- **Tracy 版本必须匹配**：`bin/` 的 CLI 与游戏内嵌 Tracy 协议版本敏感，换游戏版本时同步替换。
- **zone 命名**：原生 Tracy 的函数显示为 `"函数名 @ 源文件"`，`name_contains` 按此匹配（如脚本包前缀 `arrisCreate`）。
- **diff 要可比**：两次 capture 用尽量一致的玩法 + 同样的 `seconds`，否则 delta 不可信。
- **`seconds` 上限 60**。
- **`tracy_jank_fps` 才依赖 MCDK**（经 `execute_code` 读 `get_Fps()`）；函数耗时路径不依赖。
