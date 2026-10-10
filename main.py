"""WorkBuddy 自动签到 · 不忙脚本盒子入口。

盒子启动脚本时，把参数 JSON 文件的路径作为命令行第一个参数传入。
本文件解析 JSON 中的 environment / params，映射到 signin.py 的核心逻辑
（原 CLI 的 action 即 params.mode），并把盒子参数转成对应的环境变量。

手动运行（invoke_mode=manual）时，终端会实时显示执行进度（signin 通过
stderr 输出 [进度]），结束后展示结果并倒计时 5 秒自动关闭终端。

作者：88lin
仓库：https://github.com/88lin/workbuddy-auto-signin
协议：MIT
"""

import contextlib
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import signin  # noqa: E402

APP_NAME = "WorkBuddy 自动签到"
APP_VERSION = "1.0.0"
APP_TAGLINE = "每日签到 · 成长中心全自动 · 定时无忧"


def _as_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _print_banner(stream=None):
    """在终端打印脚本标头，让用户一眼看清正在运行什么。"""
    stream = stream or sys.stdout
    banner = (
        "╔══════════════════════════════════════════╗\n"
        "║  %s  v%s              ║\n"
        "║  %s    ║\n"
        "╚══════════════════════════════════════════╝\n"
    ) % (APP_NAME, APP_VERSION, APP_TAGLINE)
    print(banner, file=stream, flush=True)


def _countdown(seconds=5):
    """倒计时后自动退出，给用户留出阅读结果的时间。"""
    for i in range(seconds, 0, -1):
        print("\r%d 秒后自动关闭终端..." % i, end="", flush=True)
        time.sleep(1)
    print("\r终端即将关闭。                       ", flush=True)


def _write_envelope(env, code, out_dict):
    """无人值守时把结果写回 output_json（盒子信封契约：节点联动/定时任务记录结果）。"""
    out_path = env.get("output_json")
    if not out_path:
        return
    payload = out_dict if isinstance(out_dict, dict) else {}
    envelope = {
        "code": 0 if code == 0 else -1,
        "msg": str(payload.get("report") or ("ok" if code == 0 else "failed")),
        "result": payload.get("result", ""),
        "report": payload.get("report", ""),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)


def _run_and_capture(action):
    """执行 signin 逻辑并捕获其 stdout 输出（signin 以一行 JSON 汇报）。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = signin._run(action)
    return code, buf.getvalue()


def main():
    payload = json.load(open(sys.argv[1], encoding="utf-8"))
    env = payload.get("environment", {})
    params = payload.get("params", {})

    mode = str(params.get("mode", "auto"))
    budget = _as_int(params.get("budget_seconds", 0))
    auth_file = str(params.get("auth_file", "")).strip()

    if budget > 0:
        os.environ["WORKBUDDY_BUDGET_SECONDS"] = str(budget)
    if auth_file:
        os.environ["WORKBUDDY_AUTH_FILE"] = auth_file

    invoke_mode = env.get("invoke_mode")

    # 无人值守（节点联动 / 定时任务记录结果）：捕获输出并写回信封；不显示进度、不倒计时。
    # 定时任务触发时盒子会提供 output_json 用于记录结果；为 null 时兼容回退到普通 stdout。
    if invoke_mode == "node" or (invoke_mode == "scheduled" and env.get("output_json")):
        # 定时任务由盒子弹终端：启用进度输出到 stderr，避免只见黑框。
        if invoke_mode == "scheduled":
            os.environ["WORKBUDDY_PROGRESS"] = "1"
            _print_banner(sys.stderr)
        try:
            code, output = _run_and_capture(mode)
        except Exception as e:  # noqa: BLE001
            code = 1
            _write_envelope(env, code, {
                "result": "ERROR",
                "report": "脚本运行异常（%s: %s）" % (type(e).__name__, e),
            })
            return code
        parsed = None
        for line in reversed(output.splitlines()):
            try:
                parsed = json.loads(line)
                break
            except Exception:  # noqa: BLE001
                continue
        if not isinstance(parsed, dict):
            parsed = {"result": "ERROR", "report": output.strip() or "无输出"}
        _write_envelope(env, code, parsed)
        return code

    # 手动 / 定时（无信封）运行：启用分步进度；手动结束后展示结果并倒计时关闭终端。
    if invoke_mode in ("manual", "scheduled"):
        os.environ["WORKBUDDY_PROGRESS"] = "1"
        if invoke_mode == "scheduled":
            _print_banner(sys.stderr)
        else:
            _print_banner(sys.stdout)

    try:
        code = signin._run(mode)
    except Exception as e:  # noqa: BLE001
        code = 1
        print(json.dumps({
            "result": "ERROR",
            "report": "脚本运行异常（%s: %s）" % (type(e).__name__, e),
        }, ensure_ascii=False), flush=True)

    if invoke_mode == "manual":
        print("", flush=True)
        print("执行完成，退出码：%s" % code, flush=True)
        _countdown(5)

    return code


if __name__ == "__main__":
    sys.exit(main())