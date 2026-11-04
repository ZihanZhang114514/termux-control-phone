# termux-control-phone

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Android](https://img.shields.io/badge/Android-16%20(SDK%2036)-3DDC84?logo=android&logoColor=white)](https://www.android.com/)

**[English](README.en.md) | 简体中文**

一个给 AI Agent 用的实操 **skill**：当 Agent 跑在 Android 手机的容器里、自带的设备 shell
（root / Shizuku / ADB）全都不可用时，**借 Termux 打通一条能反复调用、并且能自愈的命令通道**。

> 所有结论来自真机实测（OPPO PKM110 / Android 16 / Termux + Python 3.14），不是抄文档。
> 换机型时正文结论仍适用，但文末的「实测事实清单」需要重新核验。

## 这个 skill 解决的核心问题

| # | 问题 | 结论 |
|---|---|---|
| 1 | 一上来就想搭中转 | 先比四条通道：容器文件系统（uid=0 直接读写 `/sdcard`）→ App 桥 `/app/*` → 设备 shell → 最后才是 Termux |
| 2 | Termux 突然不理人 | Android 16 的 **cached-app freezer** 会冻住后台的 Termux，症状是 **TCP 能握手、一个字节都不回**，`connect` 成功会骗人 |
| 3 | 每次都让用户手敲命令 | `~/.bashrc` 里挂带占用检测的自动拉起 + 客户端探活失败时自动 `/app/launch` 解冻重试 |
| 4 | 对用户承诺过头 | Termux 是普通应用权限（`untrusted_app_27`）：`Android/data`、其它 App 私有数据一律进不去 |

## 文件说明

| 文件 | 跑在哪 | 作用 |
|---|---|---|
| [`SKILL.md`](SKILL.md) | —— | skill 正文：通道选择、能力边界、一次性布置、故障排查表、红线、可照抄的实战流程 |
| [`tx_server.py`](tx_server.py) | Termux | 中转服务端，只用标准库，仅绑 `127.0.0.1:8765`，每次请求校验随机 token |
| [`txrun.py`](txrun.py) | Agent 容器 | 调用器：3 秒探活 → 没响应就自动解冻 → 重试；`[rc=N]` 判成败 |

## 最短上手

```bash
# 1) Termux 侧（人类只需做这一次）
termux-wake-lock
python3 /sdcard/dsh/tx.py

# 2) Agent 侧
python3 txrun.py "id; python3 -V" --timeout 30
```

想要「Agent 自己就能把服务拉起来」：把 `SKILL.md` 附录 D 的两个 rc 文件铺好，
之后 Agent 只要 `/app/launch?pkg=com.termux` 就能让中转自动回来（实测 3 秒内恢复）。

## 工作原理

```
Agent 容器                                   Termux（com.termux，uid 10608）
┌───────────────────────────┐                ┌──────────────────────────────┐
│ txrun.py / tx.py          │  JSON + token  │ tx_server.py                 │
│  探活 → 解冻 → 重试        │ ─────────────► │  校验 token → sh -c 执行命令  │
│  /app/launch 拉起 Termux   │ ◄───────────── │  仅监听 127.0.0.1:8765       │
└───────────────────────────┘  {rc,out,err}  └──────────────────────────────┘
```

- **协议**：每次请求一行 JSON `{"token","cmd","cwd","timeout"}`，回一行 `{"rc","out","err"}`。
  一次一条命令，不支持交互式会话。
- **自愈**：`alive()` 用 `true` 探活（3–4 秒超时，**别信 `connect()` 成功**）→ 不通就
  `/app/launch?pkg=com.termux` 把 Termux 拉到前台解冻 → 每 1.5 秒轮询、最多 25 秒后重试。
- **常驻**：交互式 shell 启动时跑 `~/.bashrc`，用 `connect_ex` 检测 8765 端口，没监听才
  `setsid nohup` 拉起服务，保证只有单实例、且活过会话关闭。

## 常见症状速查

| 症状 | 原因 | 处理 |
|---|---|---|
| TCP 能连上但一个字节都不回 | Android 16 cached-app 冻结 | 别重试：`/app/launch?pkg=com.termux` 解冻（`txrun.py` 自动做） |
| `ConnectionRefusedError: 8765` | 服务没起或被系统杀了 | 拉起 Termux（装了 rc 文件会自动起）；仍不行才让人类重跑步骤 1 |
| `bad token` | `.token` 被删/重建 | 重读 `/sdcard/dsh/.token`，客户端会自动读 |
| `rc=127` / `command not found` | Termux 的 `sh` 里没有 `which` | 用 `command -v xxx` |
| 容器看不到刚写的文件 | 写进了 Termux 私有目录 | 一律写 `/sdcard/...` |

完整的排查表见 `SKILL.md` 第五节。

## 安全

- 服务端只监听 loopback，token 落盘校验，不做免 token 分支。
- 技术可行 ≠ 允许执行：`SKILL.md` 第六节列了红线（不结束系统应用、不改系统设置、
  不 mount、不发/改短信、`DCIM` 默认只读、删除类任务必须分级 + 三重校验）。

## 环境

- 实测：OPPO PKM110 / Android 16 (SDK 36) / Termux Python 3.14.6 / 容器 uid=0
- 依赖：Termux 侧仅需 Python 3；Agent 侧仅需 Python 3

## License

MIT — 见 [LICENSE](LICENSE)。

---

*English version: [`README.en.md`](README.en.md). skill 正文 [`SKILL.md`](SKILL.md) 目前为中文。*
