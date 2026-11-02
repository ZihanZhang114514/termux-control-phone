# Skill：通过 Termux 控制 Android 手机

> 适用场景：DSHA（Agent）运行在 Android 手机的容器里，自带的设备 shell 通道（root / Shizuku / ADB）
> 都不可用，但手机上装了 Termux（含 Python），需要一条能真正执行命令、访问 Termux Python 库、
> 并且能反复调用的通路。
>
> 本文件所有结论都来自一次真实会话的实测，机型 OPPO PKM110 / Android 16 (SDK 36)。
> 换机型时代号可以直接用，但「实测状态」需要重新核验。

---

## 一、动手前先选通道

不要一上来就搭 Termux 中转。按下面顺序判断，能省掉一半工作量。

| 通道 | 前提 | 本次实测 | 适合干什么 |
|---|---|---|---|
| 容器自带文件系统 | 无前提 | ✅ **uid=0，`/sdcard` 直接挂载** | **批量文件处理首选**，最快 |
| App 桥 `/app/*` | 无前提（`127.0.0.1:3090`） | ✅ 可用 | 读屏、点按、启应用、读宽松目录、通知 |
| 设备 shell `adb-shell` | root 授权 / Shizuku / 无线调试配对 | ❌ 三条全不通 | 只能走它的时候 |
| **Termux 中转** | 用户手动起一次服务 | ✅ 可用 | Termux 的 Python 库、termux-api、常驻任务 |

### 判断脚本

```bash
# 1) 设备 shell 通不通
/root/dsh-bin/adb-shell "id" 2>&1 | head -3
#   CONNECT_FAIL / [POLICY_BLOCKED] 未允许 root shell  → 不通

# 2) 容器是不是 root、/sdcard 是不是真挂载
id; echo test > /sdcard/.probe && echo WRITE_OK && rm /sdcard/.probe

# 3) Termux 装没装
T=$(cat /root/.dsh/.bridge_token)
curl -s -G "http://127.0.0.1:3090/app/apps" --data-urlencode "q=termux" --data-urlencode "token=$T"

# 4) 中转在不在跑（已布置过的话）
python3 -c "import socket;s=socket.socket();s.settimeout(2)
try: s.connect(('127.0.0.1',8765)); print('RELAY: OPEN')
except Exception as e: print('RELAY: DOWN', e)"
```

**关键结论：容器是 uid=0 且 `/sdcard` 是同一份存储的真挂载。**
所以凡是「读/写/统计/批处理共享存储里的文件」，直接用容器，别绕 Termux——快一个量级。
Termux 的价值只在三件事：它的 Python 库、termux-api 的硬件能力、脱离容器的常驻。

---

## 二、能力边界（别对用户承诺过头）

| 能力 | Termux 中转 | 容器 |
|---|---|---|
| 执行任意 shell 命令 | ✅ 带管道/重定向 | ✅ |
| 身份 | uid 10608 `untrusted_app_27`（普通应用） | uid=0 |
| `/sdcard` 读 | ✅ | ✅ |
| `/sdcard` 写 | ✅ | ✅ |
| `/sdcard/Android/data`、`obb` | ❌ Permission denied | ❌ 同 |
| `/data/data/<其他应用>` | ❌ | ❌ **容器里 `/data/data` 是空壳 stub** |
| 改系统设置 / 结束系统应用 / mount | ❌ 权限不够，**且禁止尝试** | 同 |
| Python 版本 | 3.14.x | 3.12.x |
| 联网 | 走手机网络 | ✅（pypi 可达，可 pip install） |

**必须主动告诉用户的一句**：Termux 用的是普通应用权限，**拿不到任何新特权**，
读不到微信聊天记录那种 App 私有数据；要做到那一步只有 root。

---

## 三、一次性布置（Agent 做）

### 步骤 1：写服务端到共享存储

服务端必须放在 `/sdcard` 下，因为 Termux 和容器都能看到它。推荐 `/sdcard/dsh/tx.py`，
全文见 **附录 A**。要点：

- 只用标准库（Termux 自带的 python 就能跑，不用 pip）
- 只 `bind 127.0.0.1`，外部网络连不进来
- 每次请求校验随机 token，token 落在 `/sdcard/dsh/.token`
- 单行 JSON 协议：`{"token","cmd","cwd","timeout"}` → `{"rc","out","err"}`

### 步骤 2：写客户端到容器

`/root/tx.py`，全文见 **附录 B**。用法：

```bash
python3 /root/tx.py "命令" [--cwd 目录] [--timeout 秒]
```

### 步骤 3：交付给人一句话（不要多）

**人类只需要做这一件事**，把下面两行原样给他，告诉他粘进 Termux 回车、别关：

```bash
termux-wake-lock
python3 /sdcard/dsh/tx.py
```

- `termux-wake-lock` 是必须的：OPPO/ColorOS 这类系统会把 Termux 后台进程杀掉。
- 让他看到 `tx server ready on 127.0.0.1:8765` 才算成功。
- **不要**让他装包、配 SSH、改配置文件、授权存储——都不需要。
- 用 `ask_user_question` 确认「已运行 / 报错了 / 不想开常驻」，别干等。

### 步骤 4：验证（必须做，别假设成功）

```bash
python3 /root/tx.py "id; python3 -V; uname -m"
# 期望: uid=10608(u0_a608) ... context=u:r:untrusted_app_27:s0:...
```

> **实测补充（2026-10-29 第二次会话）**：Termux 的 shell 是 `bash -l`（登录 shell），
> 所以 `~/.bash_profile` → `~/.bashrc` 这条链路可用；而**用户这台机器的 `~/.bashrc`、`~/.bash_profile`
> 原本都不存在**（全新状态，没有 rc 文件）。创建它们是安全的，也是下面「自愈」的关键。

### 步骤 5：让 Agent 能自己把中转拉起来（第二次会话新增，强烈建议）

用户的要求很直白：**"直接开本地服务器，别每次让我敲命令"**。机器上无障碍没开，
Agent 没法用 UI 自动化代打命令，但 `bash -l` + rc 文件 + `/app/launch` 三件事组合起来就够了：

1. 把 **附录 D** 的两个文件铺到 `/sdcard/dsh/`，然后
   `cp /sdcard/dsh/termux_bashrc $HOME/.bashrc`、`cp /sdcard/dsh/termux_bash_profile $HOME/.bash_profile`。
   内容很短：交互式 shell 启动时探一下 8765，**没监听才** `setsid nohup` 拉起服务。
2. 之后 Termux 被系统杀掉/重启/冻结，Agent 只要
   `curl "/app/launch?pkg=com.termux"` → 新会话 → `.bashrc` → 服务自动回来。
3. 调用一律走 `/root/txrun.py`（**附录 E**）：先探测，没响应就自动 `/app/launch` 解冻再重试。

**实测验证过**：`kill -9` 掉 Termux 主进程 → `/app/launch` → **3 秒内**中转自动恢复，
`~/.dsha-tx.log` 里有新的 `tx server ready`。

### 步骤 6（可选）：给 Termux 装 termux-api

用户这台只装了 `termux-tools`（`am`/`pm`/`pkg`/`ffmpeg`/`git`/`ssh`/`sshd` 都有，
但 `termux-notification`/`termux-battery-status`/`termux-toast` 全缺）。
需要电池/剪贴板/通知这类硬件 API 时：`pkg install termux-api` **并且**装 Termux:API 应用，
两者缺一不可。不是刚需就别动用户的包。

再顺手盘点一次库，后面决定任务放哪边：

```bash
python3 /root/tx.py "python3 -c \"
import importlib
for m in ['numpy','PIL','lxml','requests','pandas','cv2','termux']:
    try: print(m, getattr(importlib.import_module(m),'__version__','ok'))
    except Exception: print(m,'MISSING')\""
```

---

## 四、Agent 日常调用规矩

1. **一条命令一调**。客户端不支持交互式会话，`vim`、`top`、`ssh` 这类会卡到超时。
   日常一律用 `python3 /root/txrun.py "命令"`（会自愈），`/root/tx.py` 只当诊断用。
2. 默认超时 120s，长任务显式加 `--timeout 600`，或干脆放容器里跑。
3. 输出上限：stdout 200 KB / stderr 40 KB，超出截断（保留尾部）。要全量就写文件再读。
4. 复杂脚本别硬塞进命令行引号地狱：**写到 `/sdcard/xxx.py`，再 `python3 /sdcard/xxx.py`**。
5. `cwd` 默认是 Termux 家目录 `/data/data/com.termux/files/home`，不是 `/sdcard`。
6. 判断成败看 `[rc=N]`，rc=0 才算过。

---

## 五、故障排查

| 症状 | 原因 | 处理 |
|---|---|---|
| **TCP 能连上但一个字节都不回，客户端 `TimeoutError`** | **Android 16 的 cached-app 冻结**：Termux 在后台被 freeze，socket 由内核 backlog 收下，进程不被调度。`connect_ex` 返回 0 会骗人 | **别改代码、别重试**：`/app/launch?pkg=com.termux` 拉到前台解冻，几秒内恢复。用 `/root/txrun.py` 它自动做 |
| `ConnectionRefusedError: 127.0.0.1:8765` | 服务没起，或被系统杀了 | 先 `/app/launch com.termux`（装了附录 D 的 rc 文件就会自动起来）；还不行才让人类重跑步骤 3 |
| `bad token` | `.token` 被删/重建了 | 重读 `/sdcard/dsh/.token`，客户端会自动读，确认文件存在 |
| `rc=127` / `command not found` | Termux 的 `sh` 里没有 `which` | 用 `command -v xxx` |
| 中文乱码 | 源文件是 GBK | 在脚本里 `.decode('gbk')`，或 `iconv -f gbk` |
| 写的文件容器看不到 | 写到了 Termux 私有目录 | 一律写 `/sdcard/...` |
| 容器里 `ls /sdcard/Android/data` 被拒 | Android 隔离存储 | 无法绕过（ADB 也一样），如实告知 |
| `/sdcard` 目录不见了 | 用户关了 Termux 存储权限 | `termux-setup-storage` |

**屏幕操作被拒时不要去重试**：本次实测 `/app/ui/dump` 返回
`[ERR] 你拒绝了这次屏幕读取`，`/app/ui/screenshot` 返回 `你拒绝了这次截屏`。
这是用户侧没授权，重试一百次也一样，改走文件通道或者直接问用户。

---

## 六、红线（违反即停手）

1. **不得用 Termux 绕过设备策略**。`tx.py` 用的是 `shell=True`，技术上能执行任何命令，
   但 adb-shell 那套保护仍然有效：不许结束系统应用/关键进程、不许 `settings put`、
   不许 mount / 刷机 / 碰块设备、不许发短信或改短信、不许卸载清数据。
   技术可行 ≠ 允许执行。
2. **删除类任务必须分级 + 校验**，见第八节，不许一把 `rm -rf`。
3. `/sdcard/DCIM`、`Pictures` 默认只读。要动必须逐项批准，且删前确认保留件存在。
4. 服务只绑 `127.0.0.1`。不改成 `0.0.0.0`，不加「方便调试」的免 token 分支。
5. 用户不给权限就别绕：`DISABLED` / `NO_PERMISSION` / `拒绝` 都照原话告诉他去哪儿开。

---

## 七、给用户的沟通模板

- 布置时：「需要你粘两行到 Termux，别的我来。」（只要求这一件事）
- 收尾时：「服务还挂着，随时能用；不想用了在 Termux 按 Ctrl+C。」
- 边界不清时：「Termux 是普通应用权限，读不到其他 App 的私有数据，这个只有 root 能解决。」

---

## 八、实战案例：全盘存储清理（可照抄的流程）

这是本次会话真正跑通的完整链路，清理类任务建议原样复用。

### 1. 只读扫描，先不动手
写 `/root/scan.py`，`os.walk('/sdcard')` 收集 `(path, size, mtime)`，跳过
`Android/data`、`Android/obb`、`Android/media`。8.7 万文件约 83 秒，正常。

### 2. 重复检测要分级过滤，否则会毁项目
朴素做法（同 size + 部分哈希 + 全量 sha1）能找出 524 组重复，但直接删会出事。本次拦下的坑：

- `minecraftWorlds/.../db/*.log` 是 LevelDB 日志，**删了可能丢存档**
- 46 个 `yolov8n.pt` 模型权重、38 个 `.jar`、79 个无扩展名文件，是**各工程目录各自需要**的
- `DCIM/MyAlbums` 里的副本是用户相册，删了相册会缺图

所以删除候选必须同时满足：扩展名在白名单（媒体/文档/压缩包）**且**不在
`/yolo/`、`dataset`、`/train/`、`.git`、`node_modules`、`minecraftWorlds`、`termux` 等目录下。

### 3. 分档
- **A**：临时文件、缓存目录内容、0 字节文件 —— 直接删
- **B1**：重复文件，原件保留 —— 建议删
- **B2**：相册内副本 / 工程文件 —— **不动**
- **B3**：120 天未动的安装包压缩包 —— 需确认
- **C**：照片、视频、文档、代码 —— 只统计，一个不碰

本次比例很说明问题：151.73 GB 里 A 只有 69 MB，C 占 136 GB。
**要老实告诉用户「真正占空间的是照片视频，而那些不该乱删」。**

### 4. 执行前三重校验（缺一不可）
1. 保留件 `os.path.isfile(keep)` 必须为真，且大小一致
2. 待删文件 `st_size` 必须等于扫描时记录的大小
3. 路径必须在 `/sdcard/` 下、无 `..` 组件、不在 `DCIM`

逐条记录删除结果，产出 `已删除清单.csv` / `跳过清单.csv`，让用户可复核。

### 5. 空间对不上时怎么查（重要经验）
本次删了 7.91 GB，可用空间只涨 3.45 GB。查证顺序：

1. 文件真删了吗 → 抽查路径 + `/app/readfile` 双向确认，`NOT_FOUND` 即真删
2. 硬链接？ → 全盘统计 `st_nlink > 1`，本次为 **0 组**
3. 统计准不准？ → 写 512 MB 再删，观察 statvfs 增减，本次**准**
4. 看文件系统 → `/proc/mounts`

```bash
grep " /data " /proc/mounts
# /dev/block/dm-76 /data f2fs rw,...,background_gc=on,...,discard
```

**`/data` 是 f2fs。空间按 segment 归还**：散落删除的 836 个文件，其所在 segment
仍混着活数据，要等后台 GC（`background_gc=on`）腾空才回到可用池，手机空闲/充电时进行。
所以「删了多少 ≠ 立刻多出多少」是正常的，别误报成失败，也别去反复重试。

### 6. 交付
报告 + CSV 放 `/sdcard/Download/DSHA/`，用 `present` 交给用户，聊天里只报数字和结论。

---

## 附录 A：服务端 `/sdcard/dsh/tx.py`

```python
#!/usr/bin/env python3
# DSHA <-> Termux 中转。只用标准库。Termux 里运行: python3 /sdcard/dsh/tx.py
import json, os, socket, subprocess, sys, threading, hmac, hashlib

TOKEN_FILE = "/sdcard/dsh/.token"
PORT, HOST = 8765, "127.0.0.1"


def load_token():
    try:
        with open(TOKEN_FILE) as f:
            t = f.read().strip()
        if t:
            return t
    except Exception:
        pass
    t = hashlib.sha256(os.urandom(32)).hexdigest()[:32]
    with open(TOKEN_FILE, "w") as f:
        f.write(t)
    return t


TOKEN = load_token()


def run(req):
    cmd = req.get("cmd", "")
    if not cmd or not isinstance(cmd, str):
        return {"rc": 2, "out": "", "err": "empty cmd"}
    cwd = req.get("cwd") or os.environ.get("HOME") or "/"
    timeout = req.get("timeout", 120)
    try:
        p = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, timeout=timeout,
            env={**os.environ,
                 "PATH": os.environ.get("PATH", "/usr/bin:/bin")
                         + ":/data/data/com.termux/files/usr/bin",
                 "TERM": "dumb", "LANG": "C.UTF-8"})
        return {"rc": p.returncode,
                "out": p.stdout.decode("utf-8", "replace")[-200000:],
                "err": p.stderr.decode("utf-8", "replace")[-40000:],
                "cwd": cwd}
    except subprocess.TimeoutExpired:
        return {"rc": 124, "out": "", "err": "timeout after %ss" % timeout}
    except Exception as e:
        return {"rc": 1, "out": "", "err": "%s: %s" % (type(e).__name__, e)}


def handle(conn):
    try:
        conn.settimeout(300)
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
        try:
            req = json.loads(buf.split(b"\n", 1)[0].decode("utf-8", "replace"))
        except Exception:
            conn.sendall(b'{"rc":2,"out":"","err":"bad json"}\n'); return
        if not hmac.compare_digest(str(req.get("token", "")), TOKEN):
            conn.sendall(b'{"rc":3,"out":"","err":"bad token"}\n'); return
        conn.sendall((json.dumps(run(req)) + "\n").encode())
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT)); s.listen(16)
    print("tx server ready on %s:%d  token=%s" % (HOST, PORT, TOKEN), flush=True)
    print("python:", sys.version.split()[0], "uid:", os.getuid(), flush=True)
    while True:
        try:
            c, _ = s.accept()
        except KeyboardInterrupt:
            break
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
```

## 附录 B：客户端 `/root/tx.py`

```python
#!/usr/bin/env python3
"""容器端调用器: python3 /root/tx.py "命令" [--cwd DIR] [--timeout SEC]"""
import json, socket, sys

SOCK = ("127.0.0.1", 8765)
TOKEN_FILE = "/sdcard/dsh/.token"


def call(cmd, cwd=None, timeout=120):
    req = {"token": open(TOKEN_FILE).read().strip(), "cmd": cmd, "timeout": timeout}
    if cwd:
        req["cwd"] = cwd
    s = socket.create_connection(SOCK, 5)
    s.settimeout(timeout + 10)
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    return json.loads(buf.decode())


def main():
    args = sys.argv[1:]
    if not args:
        print("usage: tx.py 'command' [--cwd DIR] [--timeout SEC]"); return 2
    cmd = cwd = None; timeout = 120; i = 0
    while i < len(args):
        if args[i] == "--cwd":
            cwd = args[i + 1]; i += 2
        elif args[i] == "--timeout":
            timeout = int(args[i + 1]); i += 2
        else:
            cmd = args[i]; i += 1
    r = call(cmd, cwd, timeout)
    sys.stdout.write(r.get("out", ""))
    if r.get("err"):
        sys.stderr.write(r["err"])
    print("[rc=%s]" % r.get("rc"))
    return 0 if r.get("rc") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

## 附录 C：本次实测事实清单（换机型请重新核验）

| 项目 | 值 |
|---|---|
| 机型 | OPPO PKM110，Android 16 / SDK 36 |
| 容器身份 | uid=0(root)，SELinux 组含 `aid_20217` |
| `/sdcard` | 真挂载，460.03 GB 分区，可读写 |
| App 桥 | `127.0.0.1:3090`，token 在 `/root/.dsh/.bridge_token` |
| 手机内网 IP | 10.x.x.x（局域网 IP，此处已脱敏；无线调试 5555 未开） |
| `/data` 文件系统 | **f2fs**，`background_gc=on` |
| Termux 包名 / uid | `com.termux` / 10608 |
| Termux Python | 3.14.6，pip 可用，有 numpy 2.4.4 / Pillow 12.3.0 / lxml 6.1.2 |
| Termux 缺 | requests、pandas、cv2、termux-api |
| 容器 Python | 3.12.3，pip 26.2.1，pypi 可达（几乎什么都没装） |
| 中转端口 | 8765（loopback） |
| Termux 默认 shell | `bash -l`（登录 shell，进程树里是 `bash -l`） |
| Termux rc 文件 | 原本 **不存在** `~/.bashrc`、`~/.bash_profile`、`~/.profile` |
| `termux-wake-lock` | 存在（termux-tools 自带），**挡不住 cached-app 冻结** |
| 冻结实测 | 后台十几秒到一分钟就可能冻住；刚 launch / 前台时正常 |
| 解冻手段 | 只有 `/app/launch pkg=com.termux`（无障碍未开，UI 自动化不可用） |
| 自愈 | `~/.bashrc` 自动拉服务 + `/root/txrun.py` 自动解冻，均已实测通过 |

---

## 附录 D：`~/.bashrc` 与 `~/.bash_profile`（源文件放在 `/sdcard/dsh/`）

`termux_bashrc`：

```bash
# ~/.bashrc — Termux（由 DSHA 生成；此前该文件不存在，删掉即可撤销）
# 作用：交互式 shell 启动时自动拉起「DSHA ↔ Termux 中转服务」(127.0.0.1:8765)
date +%s > "$HOME/.dsha-rc.last" 2>/dev/null

case $- in
  *i*)
    command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock 2>/dev/null
    if python3 -c "import socket,sys;sys.exit(0 if socket.socket().connect_ex(('127.0.0.1',8765))==0 else 1)" 2>/dev/null; then
      :
    else
      setsid nohup python3 /sdcard/dsh/tx.py >>"$HOME/.dsha-tx.log" 2>&1 &
    fi
    ;;
esac
```

`termux_bash_profile`：

```bash
# ~/.bash_profile — Termux（由 DSHA 生成；此前该文件不存在）
[ -f "$HOME/.bashrc" ] && . "$HOME/.bashrc"
```

要点：`case $- in *i*)` 保证只有交互式 shell 才拉服务（非交互的 ssh/scp 不会污染）；
`connect_ex` 做占用检测，不会起第二个实例；`setsid nohup` 让服务活过会话关闭和 Ctrl+C。
`~/.dsha-rc.last` 是「rc 到底有没有被执行」的探针，`~/.dsha-tx.log` 是服务日志。

## 附录 E：`/root/txrun.py`（自适应调用器，日常就用它）

```bash
python3 /root/txrun.py "命令" [--cwd DIR] [--timeout SEC] [--no-wake] [--quiet]
# 退出码：0 成功 / 1 命令非零 / 9 中转不可用
```

三步：`alive()` 用 `true` 探活（**超时 3–4 秒，别信 `connect` 成功**）→ 不通就
`/app/launch?pkg=com.termux` 解冻 → 每 1.5s 轮询、最多 25s 再执行命令；执行中途又被冻结会再自愈重试一次。

**必须主动告诉用户**：解冻等于把 Termux 抢到前台，会打断他正在看的界面。

---

*最后更新：2026-10-29（第二次会话：冻结原因与自愈）；初版 2026-10-28，基于一次真实的「Termux 接入 + 全盘清理」会话。*
