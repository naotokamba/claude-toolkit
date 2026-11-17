"""diagnose: 会話の記録から、AI がそのターンに渡された決まりを破ったところを探させる。"""
import json
import re
import sys
from pathlib import Path

from toolkit import core

ORDER = 50
DIAGNOSE_CMD_RE = re.compile(r"^\s*/diagnose(?=\s|$)")
CONTEXT_RE = re.compile(rf"<{core.NAME}>\n?(.*?)\n?</{core.NAME}>", re.S)
MODE_RE = re.compile(r"^今のモード: ([^。\s]+)", re.M)
RULE_STARTS = ("今のモード:", "ユーザーへの返答の書き方:")
NOTICE_PREFIXES = ("<task-notification>", "<agent-message", "<local-command", "<system-reminder>")
PROMPT_LIMIT = 600
SAME = object()


def on_prompt(sid, prompt, state, info):
    if not DIAGNOSE_CMD_RE.match(prompt):
        return None
    return {
        "header": "ユーザーが、会話の記録から AI が決まりを破ったところを探すよう求めた。",
        "extra": [
            f"このセッションの ID: {sid}",
            f"会話の記録ファイル: {info.get('transcript_path') or '不明'}",
            f"要約するコマンド: {core.SELF} diagnose digest <記録ファイルかセッション ID> --out <書き出すファイル>",
        ],
    }


# ---------- 記録の要約 ----------

def find_transcript(arg):
    p = Path(arg).expanduser()
    if p.is_file():
        return p
    if core.SID_RE.match(arg):
        hits = sorted(Path.home().glob(f".claude*/projects/*/{arg}.jsonl"))
        if hits:
            return hits[0]
    return None


def text_of(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def prompt_text(raw):
    raw = raw.strip()
    if raw.startswith(NOTICE_PREFIXES):
        return "(通知。ユーザーの発言ではない)"
    name = re.search(r"<command-name>(.*?)</command-name>", raw, re.S)
    if name:
        args = re.search(r"<command-args>(.*?)</command-args>", raw, re.S)
        raw = f"{name.group(1).strip()} {args.group(1).strip() if args else ''}".strip()
    return raw if len(raw) <= PROMPT_LIMIT else raw[:PROMPT_LIMIT] + "…"


def read_turns(path):
    """フックが決まりを渡したところでターンを区切る。発言、渡された決まり、AI の返答の文をまとめる。"""
    turns, pending = [], None

    def start(context, time, prompt):
        turns.append({"context": context, "time": time, "prompt": prompt, "replies": []})

    def take_prompt(p):
        nonlocal pending
        if turns and turns[-1]["prompt"] is None and not turns[-1]["replies"]:
            turns[-1]["prompt"] = p
        else:
            pending = p

    for line in path.open(encoding="utf-8"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("isSidechain"):
            continue
        kind = d.get("type")
        if kind == "attachment":
            a = d.get("attachment") or {}
            if a.get("type") == "hook_additional_context" and a.get("hookEvent") == "UserPromptSubmit":
                m = CONTEXT_RE.search("\n".join(c for c in a.get("content") or [] if isinstance(c, str)))
                start(m.group(1).strip() if m else "", d.get("timestamp", ""), pending)
                pending = None
            elif a.get("type") == "queued_command" and isinstance(a.get("prompt"), str):
                take_prompt(prompt_text(a["prompt"]))
        elif kind == "user" and not d.get("isMeta"):
            raw = text_of((d.get("message") or {}).get("content"))
            if raw.strip():
                take_prompt(prompt_text(raw))
        elif kind == "assistant":
            text = text_of((d.get("message") or {}).get("content")).strip()
            if not text:
                continue
            if pending is not None or not turns:
                # フックを通らずに届いた発言や通知への返答。決まりは前のターンのまま
                start(SAME, d.get("timestamp", ""), pending)
                pending = None
            turns[-1]["replies"].append(text)
    return turns


def split_context(context):
    lines = context.splitlines()
    for i, l in enumerate(lines):
        if l.startswith(RULE_STARTS):
            return lines[:i], "\n".join(lines[i:])
    return lines, ""


def render(path, turns):
    out = [f"# 会話の要約: {path}", f"ターン数: {len(turns)}", ""]
    index = []
    last_rules, mode = None, "なし"
    for n, t in enumerate(turns, 1):
        if t["context"] is SAME:
            notices, rules = [], last_rules
        else:
            notices, rules = split_context(t["context"])
            m = MODE_RE.search(rules or "")
            mode = m.group(1) if m else "なし"
        index.append((n, sum(x.count("\n") + 1 for x in out) + 1))
        out.append(f"## ターン {n} · {t['time'][:16]} · モード: {mode}")
        out += [f"フックからの知らせ: {x}" for x in notices]
        out.append("### 渡された決まり")
        if rules is None:
            out.append("記録に無い")
        elif rules == last_rules:
            out.append("前のターンと同じ")
        else:
            out.append(rules)
        last_rules = rules
        out.append("### ユーザー")
        out.append(t["prompt"] or "記録に無い")
        out.append("### AI")
        out.append("\n\n".join(t["replies"]) or "文の返答なし")
        out.append("")
    return "\n".join(out) + "\n", index


def cmd_diagnose(args):
    usage = f"使い方: {core.NAME} diagnose digest <記録ファイルかセッション ID> [--out <書き出すファイル>]"
    if not args or args[0] != "digest":
        sys.exit(usage)
    rest, out = [], None
    it = iter(args[1:])
    for a in it:
        if a == "--out":
            out = next(it, None)
            if not out:
                sys.exit(usage)
        else:
            rest.append(a)
    if len(rest) != 1:
        sys.exit(usage)
    path = find_transcript(rest[0])
    if not path:
        sys.exit(f"記録ファイルが見つからない: {rest[0]}")
    text, index = render(path, read_turns(path))
    if not out:
        print(text, end="")
        return
    Path(out).expanduser().parent.mkdir(parents=True, exist_ok=True)
    Path(out).expanduser().write_text(text, encoding="utf-8")
    print(f"書き出し先: {out}")
    print(f"ターン数 {len(index)}、行数 {text.count(chr(10))}、字数 {len(text)}")
    print("各ターンの始まりの行: " + "、".join(f"{n}:{line}" for n, line in index))


COMMANDS = {"diagnose": cmd_diagnose}
ALLOW = ["diagnose"]
