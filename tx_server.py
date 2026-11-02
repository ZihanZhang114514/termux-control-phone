#!/usr/bin/env python3
# DSHA <-> Termux 中转服务。只用标准库，Termux 自带 python 即可运行。
# 在 Termux 里执行:  python3 /sdcard/dsh/tx.py
# 仅监听 127.0.0.1:8765，只接受带 token 的请求。
import json, os, socket, subprocess, sys, threading, time, hmac, hashlib

TOKEN_FILE = "/sdcard/dsh/.token"
PORT = 8765
HOST = "127.0.0.1"


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
            env={**os.environ, "PATH": os.environ.get("PATH", "/usr/bin:/bin")
                 + ":/data/data/com.termux/files/usr/bin",
                 "TERM": "dumb", "LANG": "C.UTF-8"},
        )
        out = p.stdout.decode("utf-8", "replace")
        err = p.stderr.decode("utf-8", "replace")
        return {"rc": p.returncode, "out": out[-200000:], "err": err[-40000:],
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
        line = buf.split(b"\n", 1)[0]
        try:
            req = json.loads(line.decode("utf-8", "replace"))
        except Exception:
            conn.sendall(b'{"rc":2,"out":"","err":"bad json"}\n')
            return
        if not hmac.compare_digest(str(req.get("token", "")), TOKEN):
            conn.sendall(b'{"rc":3,"out":"","err":"bad token"}\n')
            return
        resp = run(req)
        conn.sendall((json.dumps(resp) + "\n").encode())
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
    s.bind((HOST, PORT))
    s.listen(16)
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
