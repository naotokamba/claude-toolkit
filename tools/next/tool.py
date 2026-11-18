"""順番: 決めた順番どおりに 1 件ずつ進める。今の 1 件を毎ターン AI に渡す。"""
import re
import sys

from toolkit import core

ORDER = 15
N_CMD_RE = re.compile(r"^\s*/n(?=\s|$)")
# 件が切り替わった直後は、読み手が経緯を覚えていないので、返事の最初に概要を置かせる
OVERVIEW = ("返事の最初に、「この件」として、今の 1 件が何をする件かと、どんな困りごとから生まれた件かを 1 行ずつ書く。"
            "読み手は、別の件から切り替わってきたばかりで、この件の経緯を覚えていない。起点の issue やカードが分かっていれば、その言葉にリンクを付け、分からなければ分からないと書く")


def queue(state):
    return state.get("queue") or []


def set_cmd(sid):
    return f'{core.SELF} next set --session {sid} -- "<1 件目>" "<2 件目>" ...'


def split_cmd(sid):
    return f'{core.SELF} next split --session {sid} -- "<分けた 1 件目>" "<分けた 2 件目>" ...'


def clear_cmd(sid):
    return f"{core.SELF} next clear --session {sid}"


def on_prompt(sid, prompt, state, info):
    if not N_CMD_RE.match(prompt):
        return None
    q = queue(state)
    if not q:
        return {"header": "ユーザーが /n で次の 1 件を求めたが、順番がまだ無い。",
                "extra": [f"順番を記録するコマンド: {set_cmd(sid)}"]}
    done = q.pop(0)
    if q:
        state["queue"] = q
    else:
        state.pop("queue", None)
    core.save_state(sid, state)
    if not q:
        return {"header": f"ユーザーが /n で次に進んだ。「{done}」で、順番の最後まで終わった。"}
    return {"header": f"ユーザーが /n で次の 1 件に進んだ。終えた件: {done}", "extra": [OVERVIEW]}


def context(sid, state, info):
    q = queue(state)
    if not q:
        return []
    return [
        f"今の 1 件: {q[0]}。順番の残り: {len(q) - 1} 件",
        "話すのは今の 1 件だけ。ほかの件は、今の 1 件の判断材料になるときだけ出す",
        f"今の 1 件を分けるときは {split_cmd(sid)}、順番を作り直すときは {set_cmd(sid)}、やめるときは {clear_cmd(sid)}",
    ]


def active(state):
    return bool(queue(state))


def status(state):
    q = queue(state)
    if not q:
        return []
    now = q[0] if len(q[0]) <= 30 else q[0][:30] + "…"
    return [f"今: {now}（残り {len(q) - 1}）"]


def cmd_next(args):
    usage = f"使い方: {core.NAME} next set|split|clear|show --session <ID> [-- 件...]"
    sid, rest = core.take_session(args)
    if not rest:
        sys.exit(usage)
    sub, items = rest[0], [a for a in rest[1:] if a != "--" and a.strip()]
    state = core.load_state(sid)
    q = queue(state)
    if sub == "set":
        if not items:
            sys.exit(usage)
        state["queue"] = items
        print(f"順番を記録しました。今の 1 件: {items[0]}（残り {len(items) - 1} 件）")
    elif sub == "split":
        if not q or len(items) < 2:
            sys.exit("今の 1 件が無いか、分けた件が 2 つ未満です")
        state["queue"] = items + q[1:]
        print(f"「{q[0]}」を {len(items)} 件に分けました。今の 1 件: {items[0]}")
    elif sub == "clear":
        state.pop("queue", None)
        print("順番を消しました")
    elif sub == "show":
        print("\n".join(f"{i + 1}. {x}" for i, x in enumerate(q)) or "順番はありません")
        return
    else:
        sys.exit(usage)
    core.save_state(sid, state)


COMMANDS = {"next": cmd_next}
ALLOW = ["next"]
