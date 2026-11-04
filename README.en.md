# termux-control-phone

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Android](https://img.shields.io/badge/Android-16%20(SDK%2036)-3DDC84?logo=android&logoColor=white)](https://www.android.com/)

**[English](README.en.md) | [简体中文](README.md)**

A hands-on **skill** for AI agents: when the agent runs inside a container on an Android
phone and every built-in device shell (root / Shizuku / ADB) is unavailable, **borrow Termux
to open a command channel that can be called again and again — and that heals itself**.

> Every conclusion here comes from real hardware (OPPO PKM110 / Android 16 / Termux +
> Python 3.14), not from documentation. On a different device the body of the skill still
> applies, but the "measured facts" appendix has to be re-verified.

## The problems this skill solves

| # | Problem | Conclusion |
|---|---|---|
| 1 | Reaching for a relay right away | Compare the four channels first: container filesystem (uid=0 can read/write `/sdcard` directly) → app bridge `/app/*` → device shell → Termux last |
| 2 | Termux suddenly stops answering | Android 16's **cached-app freezer** freezes Termux in the background. The symptom is **the TCP handshake succeeds but not a single byte comes back**, so a successful `connect()` lies to you |
| 3 | Making the user type commands every time | Auto-start from `~/.bashrc` with an occupancy check, plus a client that does `/app/launch` to thaw Termux when the liveness probe fails, then retries |
| 4 | Over-promising to the user | Termux runs with ordinary app permissions (`untrusted_app_27`): `Android/data` and other apps' private data are always out of reach |

## Files

| File | Runs on | Purpose |
|---|---|---|
| [`SKILL.md`](SKILL.md) | — | The skill text: channel selection, capability boundaries, one-time setup, troubleshooting table, red lines, a runnable end-to-end example |
| [`tx_server.py`](tx_server.py) | Termux | Relay server. Standard library only, binds `127.0.0.1:8765` only, validates a random token on every request |
| [`txrun.py`](txrun.py) | Agent container | Client: 3-second liveness probe → auto-thaw if silent → retry; reports success via `[rc=N]` |

## Quick start

```bash
# 1) Termux side (the human does this exactly once)
termux-wake-lock
python3 /sdcard/dsh/tx.py

# 2) Agent side
python3 txrun.py "id; python3 -V" --timeout 30
```

Want the agent to be able to bring the relay up by itself? Install the two rc files from
Appendix D of `SKILL.md`; after that, one `/app/launch?pkg=com.termux` is enough to make the
relay come back (measured: recovered in under 3 seconds).

## How it works

```
Agent container                              Termux (com.termux, uid 10608)
┌───────────────────────────┐                ┌──────────────────────────────┐
│ txrun.py / tx.py          │  JSON + token  │ tx_server.py                 │
│  probe → thaw → retry     │ ─────────────► │  verify token → sh -c command│
│  /app/launch to thaw      │ ◄───────────── │  127.0.0.1:8765 only         │
└───────────────────────────┘   {rc,out,err} └──────────────────────────────┘
```

- **Protocol:** one line of JSON per request, `{"token","cmd","cwd","timeout"}`, answered
  with `{"rc","out","err"}`. Single command per call — no interactive session.
- **Self-healing:** `alive()` probes with `true` under a 3–4 s timeout (never trust a plain
  `connect()`), then `/app/launch?pkg=com.termux` to pull Termux to the foreground and thaw
  it, then polls every 1.5 s for up to 25 s before retrying the command.
- **Startup:** the interactive shell runs `~/.bashrc`, which checks port 8765 with
  `connect_ex` and only then starts the server via `setsid nohup`, so there is exactly one
  instance and it survives the session closing.

## Security

- The server listens on loopback only and always validates the token (`hmac.compare_digest`);
  there is no "debug" mode without a token.
- The token lives in `/sdcard/dsh/.token` and is generated from `os.urandom` on first run.
- Technically possible ≠ allowed: Section 6 of `SKILL.md` lists the red lines (never kill
  system apps, never change system settings, never mount, never send or modify SMS, `DCIM`
  is read-only by default, deletion work must be tiered and triple-checked).

## Requirements

- **Termux side:** Python 3 only (no pip, no extra packages). `termux-tools` is already
  enough for `termux-wake-lock`.
- **Agent side:** Python 3, plus the app bridge at `127.0.0.1:3090` for auto-thaw.
  Without the bridge the relay still works; you just cannot thaw a frozen Termux.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| TCP connects but not a byte comes back; client raises `TimeoutError` | Android 16 cached-app freeze. `connect_ex` returns 0 and lies to you | Don't touch the code, don't retry: `/app/launch?pkg=com.termux` to thaw. `txrun.py` does this for you |
| `ConnectionRefusedError: 127.0.0.1:8765` | Server is not running, or was killed | Launch Termux (the rc files auto-start it); only if that fails, ask the human to run the two-line setup again |
| `bad token` | `.token` was deleted or regenerated | Read `/sdcard/dsh/.token` again; the client picks it up automatically |
| `rc=127` / `command not found` | Termux's `sh` has no `which` | Use `command -v xxx` |
| Mojibake in Chinese output | Source file is GBK | `.decode('gbk')` in your script, or `iconv -f gbk` |
| Files written are invisible to the container | You wrote into Termux's private home | Always write to `/sdcard/...` |
| `ls /sdcard/Android/data` denied in the container | Android scoped storage | Cannot be bypassed (not even with ADB). Say so honestly |
| `/sdcard` is missing | Termux storage permission revoked | `termux-setup-storage` |

## Measured environment

- OPPO PKM110 / Android 16 (SDK 36) / Termux Python 3.14.6 / container uid=0
- `/sdcard` is a real mount of the same storage the container sees: use the container
  directly for bulk file work — it is an order of magnitude faster than going through Termux.
- Termux provides exactly three things the container cannot: its Python libraries,
  `termux-api` hardware access, and a daemon that survives outside the container.

## License

MIT — see [LICENSE](LICENSE).

---

*Chinese original: [`README.md`](README.md). The skill text itself ([`SKILL.md`](SKILL.md))
is currently written in Chinese.*
