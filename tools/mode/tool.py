"""モード: 目的・発散・収束・作業などを切り替え、そのルールを毎ターン AI に渡す。"""
import re
import sys
from pathlib import Path

from toolkit import core

ORDER = 10
HERE = Path(__file__).resolve().parent
MODES_DIR = HERE / "modes"
COMMON = HERE / "common.md"

MODE_ORDER = ["目的", "発散", "収束", "作業", "理解", "推理"]
# 打つときの正式な名前は英語。表示は日本語のまま
ENGLISH = {"目的": "purpose", "発散": "diverge", "収束": "converge", "作業": "work", "理解": "understand", "推理": "infer"}
ALIASES = {en: ja for ja, en in ENGLISH.items()}
ALIASES.update({en[0]: ja for ja, en in ENGLISH.items()})
ALIASES["実装"] = "作業"
OFF_WORDS = {"off", "q", "解除", "なし"}
MODE_CMD_RE = re.compile(r"^\s*/mode(?=\s|$)\s*(\S+)?", re.S)
SHORT_CMD_RE = re.compile(r"^\s*/([pdcwuqi])(?=\s|$)")
# /dc と /idc は、fork に任せた発散や調査のあとで収束に入る。モードは収束にする
COMBO_CMDS = {
    "dc": "発散を fork に任せてから収束に入る",
    "idc": "調査と発散を fork に任せてから収束に入る",
}
COMBO_CMD_RE = re.compile(r"^\s*/(dc|idc)(?=\s|$)")
# /n c のように /n に続けたコマンドは、そのコマンドを打ったのと同じに扱う
N_FOLLOW_RE = re.compile(r"^\s*/n\s+(p|d|c|w|u|i|dc|idc)(?=\s|$)(.*)$", re.S)


def available_modes():
    names = [p.stem for p in MODES_DIR.glob("*.md")]
    return [m for m in MODE_ORDER if m in names] + sorted(n for n in names if n not in MODE_ORDER)


def resolve_mode(arg):
    name = ALIASES.get(arg.lower(), arg)
    return name if name in available_modes() else None


def usable_names():
    modes = available_modes()
    en = [ENGLISH.get(m, m) for m in modes]
    initials = [ENGLISH[m][0] for m in modes if m in ENGLISH]
    return f"使えるのは {'・'.join(en)} と off。頭文字の {'・'.join(initials)} や、{'・'.join(modes)} でもよい"


def skill_body(name):
    """スキルの本文から、前書きと引数の行を除いたもの。"""
    text = (Path(__file__).resolve().parent / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        text = text.split("---", 2)[2]
    return [l for l in text.strip().splitlines() if l.strip() and not l.startswith("引数:")]


def follow_extra(name, rest):
    """/n に続けたコマンドの手順を、ファイルを読ませずにそのまま渡す。"""
    said = rest.strip() or "今の 1 件"
    if name in COMBO_CMDS:
        return [f"/n に続けて /{name} が打たれた。議題: {said}。次の手順に従う。"] + skill_body(name)
    return [f"/n に続けて /{name} が打たれた。「{said}」を、このモードでのユーザーの発言として扱い、そのモードのルールで応答する。"]


def on_prompt(sid, prompt, state, info):
    follow = N_FOLLOW_RE.match(prompt)
    if follow:
        result = on_prompt(sid, f"/{follow.group(1)}{follow.group(2)}", state, info) or {}
        result["extra"] = result.get("extra", []) + follow_extra(follow.group(1), follow.group(2))
        return result
    combo = COMBO_CMD_RE.match(prompt)
    if combo:
        state["mode"] = "収束"
        core.save_state(sid, state)
        name = combo.group(1)
        return {"header": f"ユーザーが /{name} で、{COMBO_CMDS[name]}よう求めた。モードは「収束」にした。"}
    short = SHORT_CMD_RE.match(prompt)
    m = MODE_CMD_RE.match(prompt)
    if not short and not m:
        return None
    arg = short.group(1) if short else m.group(1)
    if arg is None:
        return {"header": "ユーザーが今のモードを確認した。"}
    if arg.lower() in OFF_WORDS:
        state.pop("mode", None)
        core.save_state(sid, state)
        return {"header": "ユーザーがモードを解除した。"}
    name = resolve_mode(arg)
    if not name:
        return {"header": f"「{arg}」というモードはない。{usable_names()}。モードは変えていない。"}
    state["mode"] = name
    core.save_state(sid, state)
    return {"header": f"ユーザーがモードを「{name}」に切り替えた。"}


def mode_lines(sid, state):
    mode = state.get("mode")
    if not mode or not (MODES_DIR / f"{mode}.md").exists():
        return []
    goal = state.get("goal")
    lines = [
        f"今のモード: {mode}。モードを切り替えるのはユーザーだけ",
        f"記録済みの目的: {goal}" if goal else "記録済みの目的: まだない",
        f"{mode}モードのルール:",
    ]
    lines += [l.replace("{goal_cmd}", core.goal_command(sid)) for l in core.read_lines(MODES_DIR / f"{mode}.md")]
    lines.append("全モード共通のルール:")
    lines += core.read_lines(COMMON)
    return lines


def context(sid, state, info):
    lines = mode_lines(sid, state)
    if not lines and info.get("header"):
        return ["今のモード: なし"]
    return lines


def active(state):
    return bool(state.get("mode"))


def status(state):
    parts = []
    if state.get("mode"):
        parts.append(f"モード: {state['mode']}")
        goal = state.get("goal")
        if goal:
            parts.append(f"目的: {goal if len(goal) <= 40 else goal[:40] + '…'}")
    return parts


def cmd_goal(args):
    sid, rest = core.take_session(args)
    clear = "--clear" in rest
    text = [a for a in rest if a != "--clear"]
    state = core.load_state(sid)
    if clear:
        state.pop("goal", None)
        core.save_state(sid, state)
        print("目的の記録を消しました")
        return
    goal = " ".join(text).strip()
    if not goal:
        print(f"記録済みの目的: {state.get('goal') or 'まだない'}")
        return
    state["goal"] = goal
    core.save_state(sid, state)
    print(f"目的を記録しました: {goal}")


def cmd_mode(args):
    if len(args) != 2 or args[0] != "show":
        sys.exit(f"使い方: {core.NAME} mode show <モード>  使えるモード: {'・'.join(available_modes())}")
    name = resolve_mode(args[1])
    if not name:
        sys.exit(f"「{args[1]}」というモードはない。使えるのは {'・'.join(available_modes())}")
    print(core.build_context("SESSION_ID", {"mode": name}, [f"ユーザーがモードを「{name}」に切り替えた。"], []))


COMMANDS = {"goal": cmd_goal, "mode": cmd_mode}
ALLOW = ["goal"]
