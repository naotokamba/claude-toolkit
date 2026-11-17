"""ボード: 作業の全体をカードで並べたアーティファクトを、セッションに紐づける。"""
import json
import re
import sys
from pathlib import Path

from toolkit import core

ORDER = 20
HERE = Path(__file__).resolve().parent
UPDATE_DOC = HERE / "skills" / "board" / "update.md"
BOARD_CMD_RE = re.compile(r"^\s*/board(?:-issue)?(?=\s|$)")
BOARD_URL_RE = re.compile(r"^https://claude\.ai/(?:code/)?artifact/[A-Za-z0-9_-]+$")


def on_prompt(sid, prompt, state, info):
    if not BOARD_CMD_RE.match(prompt):
        return None
    extra = [
        f"このセッションの ID: {sid}",
        f"ボードを紐づけるコマンド: {core.SELF} board attach --session {sid} <ボードの URL>",
        f"検査するコマンド: {core.SELF} board check <フォルダ>",
        f"会話の記録ファイル: {info.get('transcript_path') or '不明'}",
    ]
    if not state.get("board"):
        extra.append("このセッションに紐づいたボード: まだない")
    return {"header": "ユーザーがボードのコマンドを使った。", "extra": extra}


def context(sid, state, info):
    url = state.get("board")
    if not url:
        return []
    return [
        f"このセッションのボード: {url}",
        "ボードは節目で更新する。節目は、論点にユーザーが答えたとき、作業をしてターンを返すとき、目的を記録したとき。"
        f"手順: {UPDATE_DOC}。検査: {core.SELF} board check <フォルダ>",
    ]


def active(state):
    return bool(state.get("board"))


def status(state):
    return ["ボードあり"] if state.get("board") else []


def cmd_board(args):
    usage = f"使い方: {core.NAME} board attach|detach|show|check ..."
    if not args:
        sys.exit(usage)
    sub, rest = args[0], args[1:]
    if sub == "check":
        if len(rest) != 1:
            sys.exit(f"使い方: {core.NAME} board check <フォルダ>")
        errors, summary = check_board_dir(Path(rest[0]))
        if errors:
            print(f"検査に通りませんでした。{len(errors)} 件")
            for e in errors:
                print(f"- {e}")
            sys.exit(1)
        print(f"検査に通りました。{summary}")
        return
    sid, rest = core.take_session(rest)
    state = core.load_state(sid)
    if sub == "attach":
        if len(rest) != 1 or not BOARD_URL_RE.match(rest[0]):
            sys.exit(f"使い方: {core.NAME} board attach [--session ID] https://claude.ai/artifact/<id>")
        state["board"] = rest[0]
        core.save_state(sid, state)
        print(f"ボードを紐づけました: {rest[0]}")
    elif sub == "detach":
        state.pop("board", None)
        core.save_state(sid, state)
        print("ボードの紐づけを外しました")
    elif sub == "show":
        print(f"このセッションのボード: {state.get('board') or 'まだない'}")
    else:
        sys.exit(usage)


COMMANDS = {"board": cmd_board}
ALLOW = ["board"]


# ---------- 検査 ----------
# skills/board/format.md と同じ決まり。ここに無い欄は通さない

LIMITS = {
    "title": 40, "purpose": 80, "goal": 80, "report.text": 80, "decision.text": 80,
    "card.title": 30, "card.goal": 80, "task.text": 60,
    "question": 80, "material": 80, "recommend": 120, "shaken": 80, "ifDo": 80, "ifDont": 80, "notFound": 80,
}
BOARD_KEYS = {"title", "purpose", "goal", "updated", "report", "decisions", "issue"}
CARD_KEYS = {"title", "goal", "state", "order", "issue", "tasks"}
TASK_KEYS = {"id", "text", "kind", "owner", "issue", "ronten"}
RONTEN_KEYS = {"question", "materials", "recommend", "shaken", "ifDo", "ifDont", "notFound"}
CARD_STATES = {"進行中", "issueに移した", "別途やる", "済み"}
TASK_KINDS = {"やるだけ", "判断待ち", "済み"}
OWNERS = {"あなた", "AI", "ほかの人"}
REPORT_RESULTS = {"完遂した", "完遂できなかった"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DOC_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def check_board_dir(folder):
    errors = []

    def unknown(where, obj, allowed):
        for k in obj:
            if k not in allowed:
                errors.append(f"{where}: 「{k}」という欄は無い。使える欄は {', '.join(sorted(allowed))}")

    def text_field(where, obj, key, limit, required=False):
        v = obj.get(key)
        if v is None or v == "":
            if required:
                errors.append(f"{where}: {key} が無い")
            return
        if not isinstance(v, str):
            errors.append(f"{where}: {key} は文字列にする")
        elif len(v) > limit:
            errors.append(f"{where}: {key} が {len(v)} 字。上限は {limit} 字")

    def link(where, v):
        if v is None:
            return
        if not isinstance(v, dict):
            errors.append(f"{where}: {{url, label}} の形にする")
            return
        unknown(where, v, {"url", "label"})
        if not isinstance(v.get("url"), str) or not v["url"].startswith("https://"):
            errors.append(f"{where}: url は https:// で始める")

    def str_list(where, v, limit, max_items):
        if v is None:
            return
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errors.append(f"{where}: 文字列の配列にする")
            return
        if len(v) > max_items:
            errors.append(f"{where}: {len(v)} 個。上限は {max_items} 個")
        for i, x in enumerate(v):
            if len(x) > limit:
                errors.append(f"{where}[{i}]: {len(x)} 字。上限は {limit} 字")

    def date(where, obj, key):
        if key in obj and not (isinstance(obj[key], str) and DATE_RE.match(obj[key])):
            errors.append(f"{where}: {key} は YYYY-MM-DD にする")

    def load(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"{path}: JSON として読めない ({e})")
            return None
        if not isinstance(data, dict):
            errors.append(f"{path}: 中身はオブジェクトにする")
            return None
        return data

    board_file = folder / "meta" / "board.json"
    if board_file.exists():
        b = load(board_file)
        if b is not None:
            w = "meta/board"
            unknown(w, b, BOARD_KEYS)
            text_field(w, b, "title", LIMITS["title"], required=True)
            text_field(w, b, "purpose", LIMITS["purpose"])
            text_field(w, b, "goal", LIMITS["goal"])
            date(w, b, "updated")
            rep = b.get("report")
            if rep is not None:
                if not isinstance(rep, dict):
                    errors.append(f"{w}.report: {{result, text}} の形にする")
                else:
                    unknown(f"{w}.report", rep, {"result", "text"})
                    if rep.get("result") not in REPORT_RESULTS:
                        errors.append(f"{w}.report: result は {'、'.join(sorted(REPORT_RESULTS))} のどれか")
                    text_field(f"{w}.report", rep, "text", LIMITS["report.text"])
            decs = b.get("decisions")
            if decs is not None:
                if not isinstance(decs, list):
                    errors.append(f"{w}.decisions: 配列にする")
                else:
                    for i, d in enumerate(decs):
                        dw = f"{w}.decisions[{i}]"
                        if not isinstance(d, dict):
                            errors.append(f"{dw}: {{text, date}} の形にする")
                            continue
                        unknown(dw, d, {"text", "date"})
                        text_field(dw, d, "text", LIMITS["decision.text"], required=True)
                        date(dw, d, "date")
            rule = b.get("issue")
            if rule is not None:
                if not isinstance(rule, dict):
                    errors.append(f"{w}.issue: {{repo, prefix, parentPrefix}} の形にする")
                else:
                    unknown(f"{w}.issue", rule, {"repo", "prefix", "parentPrefix"})
                    if "repo" in rule and not (isinstance(rule["repo"], str) and re.match(r"^[\w.-]+/[\w.-]+$", rule["repo"])):
                        errors.append(f"{w}.issue: repo は owner/name の形にする")

    cards = sorted((folder / "cards").glob("*.json")) if (folder / "cards").is_dir() else []
    n_wait = 0
    for path in cards:
        cid = path.stem
        w = f"cards/{cid}"
        if not DOC_ID_RE.match(cid):
            errors.append(f"{w}: id は英数字と - _ だけにする")
        c = load(path)
        if c is None:
            continue
        unknown(w, c, CARD_KEYS)
        text_field(w, c, "title", LIMITS["card.title"], required=True)
        text_field(w, c, "goal", LIMITS["card.goal"], required=True)
        if c.get("state") not in CARD_STATES:
            errors.append(f"{w}: state は {'、'.join(sorted(CARD_STATES))} のどれか")
        if not isinstance(c.get("order"), (int, float)) or isinstance(c.get("order"), bool):
            errors.append(f"{w}: order は数にする")
        link(f"{w}.issue", c.get("issue"))
        tasks = c.get("tasks", [])
        if not isinstance(tasks, list):
            errors.append(f"{w}.tasks: 配列にする")
            continue
        seen = set()
        for i, t in enumerate(tasks):
            tw = f"{w}.tasks[{i}]"
            if not isinstance(t, dict):
                errors.append(f"{tw}: オブジェクトにする")
                continue
            unknown(tw, t, TASK_KEYS)
            tid = t.get("id")
            if not isinstance(tid, str) or not tid:
                errors.append(f"{tw}: id が無い")
            elif tid in seen:
                errors.append(f"{tw}: id「{tid}」がカードの中で重なっている")
            seen.add(tid)
            text_field(tw, t, "text", LIMITS["task.text"], required=True)
            kind = t.get("kind")
            if kind not in TASK_KINDS:
                errors.append(f"{tw}: kind は {'、'.join(sorted(TASK_KINDS))} のどれか")
            if "owner" in t and t["owner"] not in OWNERS:
                errors.append(f"{tw}: owner は {'、'.join(sorted(OWNERS))} のどれか")
            link(f"{tw}.issue", t.get("issue"))
            r = t.get("ronten")
            if kind == "判断待ち":
                n_wait += 1
                if not isinstance(r, dict):
                    errors.append(f"{tw}: 判断待ちには ronten が要る")
                    continue
                rw = f"{tw}.ronten"
                unknown(rw, r, RONTEN_KEYS)
                text_field(rw, r, "question", LIMITS["question"], required=True)
                text_field(rw, r, "recommend", LIMITS["recommend"], required=True)
                for key in ("shaken", "ifDo", "ifDont"):
                    text_field(rw, r, key, LIMITS[key])
                str_list(f"{rw}.materials", r.get("materials"), LIMITS["material"], 5)
                str_list(f"{rw}.notFound", r.get("notFound"), LIMITS["notFound"], 3)
            elif r is not None:
                errors.append(f"{tw}: ronten は判断待ちのときだけ書く")
    if not board_file.exists() and not cards:
        errors.append(f"{folder}: meta/board.json も cards/*.json も無い")
    return errors, f"カード {len(cards)} 枚、判断待ち {n_wait} 件"
