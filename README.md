# termux-control-phone

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

## 安全

- 服务端只监听 loopback，token 落盘校验，不做免 token 分支。
- 技术可行 ≠ 允许执行：`SKILL.md` 第六节列了红线（不结束系统应用、不改系统设置、
  不 mount、不发/改短信、`DCIM` 默认只读、删除类任务必须分级 + 三重校验）。

## 环境

- 实测：OPPO PKM110 / Android 16 (SDK 36) / Termux Python 3.14.6 / 容器 uid=0
- 依赖：Termux 侧仅需 Python 3；Agent 侧仅需 Python 3

## License

MIT
