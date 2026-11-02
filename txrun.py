#!/usr/bin/env python3
"""DSHA -> Termux 自适应调用器。

Termux 在后台会被 Android 16 冻结（TCP 能握手但进程不响应）。本脚本在调用前
先探测，探测失败就把 Termux 拉到前台解冻（/app/launch），再重试。

用法:
    python3 /root/txrun.py "命令" [--cwd DIR] [--timeout SEC] [--no-wake] [--quiet]
"""
import json, socket, sys, time, urllib.parse, urllib.request

SOCK = ("127.0.0.1", 8765)
TOKEN_FILE = "/sdcard/dsh/.token"
BRIDGE_TOKEN_FILE = "/root/.dsh/.bridge_token"
BRIDGE = "http://127.0.0.1:3090/app/launch"


def _token():
    with open(TOKEN_FILE) as f:
        return f.read().strip()


def call(cmd, cwd=None, timeout=120, recv_wait=None):
    req = {"token": _token(), "cmd": cmd, "timeout": timeout}
    if cwd:
        req["cwd"] = cwd
    s = socket.create_connection(SOCK, 3)
    s.settimeout(recv_wait if recv_wait is not None else timeout + 10)
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        d = s.recv(65536)
        if not d:
            break
        buf += d
    s.close()
    if not buf:
        raise ConnectionError("empty response (frozen?)")
    return json.loads(buf.decode())


def alive(wait=4):
    try:
        return call("true", timeout=wait, recv_wait=wait).get("rc") == 0
    except Exception:
        return False


def thaw(quiet=False):
    """把 Termux 拉到前台，解除 cached-app 冻结。会让 Termux 抢到前台。"""
    if not quiet:
        print("[txrun] 中转无响应（大概率被系统冻结），正在把 Termux 拉到前台……",
              file=sys.stderr)
    try:
        with open(BRIDGE_TOKEN_FILE) as f:
            tok = f.read().strip()
        url = BRIDGE + "?" + urllib.parse.urlencode({"pkg": "com.termux", "token": tok})
        urllib.request.urlopen(url, timeout=20).read()
        return True
    except Exception as e:
        print("[txrun] 唤醒失败: %s" % e, file=sys.stderr)
        return False


def ensure(quiet=False, budget=25):
    """保证中转可用；返回 True/False。"""
    if alive():
        return True
    if not thaw(quiet):
        return False
    t0 = time.time()
    while time.time() - t0 < budget:
        time.sleep(1.5)
        if alive(wait=3):
            if not quiet:
                print("[txrun] 已恢复（%.0fs）" % (time.time() - t0), file=sys.stderr)
            return True
    return False


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__.strip())
        return 2
    cmd = cwd = None
    timeout, quiet, no_wake = 120, False, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--cwd":
            cwd, i = args[i + 1], i + 2
        elif a == "--timeout":
            timeout, i = int(args[i + 1]), i + 2
        elif a == "--quiet":
            quiet, i = True, i + 1
        elif a == "--no-wake":
            no_wake, i = True, i + 1
        else:
            cmd, i = a, i + 1
    if not cmd:
        print("[txrun] 缺少命令", file=sys.stderr)
        return 2

    if not no_wake and not ensure(quiet):
        print("[txrun] 中转不可用：Termux 未在前台、或服务没起。"
              "请在 Termux 里执行 termux-wake-lock && python3 /sdcard/dsh/tx.py",
              file=sys.stderr)
        return 9

    try:
        r = call(cmd, cwd, timeout)
    except Exception as e:
        # 可能在执行途中被冻结，再唤一次重试一遍
        if no_wake or not ensure(quiet):
            print("[txrun] 调用失败: %s: %s" % (type(e).__name__, e), file=sys.stderr)
            return 9
        r = call(cmd, cwd, timeout)

    sys.stdout.write(r.get("out", ""))
    if r.get("err"):
        sys.stderr.write(r["err"])
    print("[rc=%s]" % r.get("rc"))
    return 0 if r.get("rc") == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
