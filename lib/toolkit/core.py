"""claude-toolkit の共通部分。

道具は tools/<名前>/tool.py に置く。core はそれを読み込み、フックとコマンドに組み込む。
tool.py に置けるもの。どれも省略できる。
  ORDER                 フックで渡す文の並び順。小さいほど先
  on_prompt(sid, prompt, state, info)  発言を受けたとき。{"header": 文, "extra": [文...]} を返す
  context(sid, state, info)            毎ターン AI に渡す文の配列
  active(state)                        会話の要約・再開の直後にも渡すべき状態なら True
  status(state)                        ステータスラインに出す文の配列
  COMMANDS              {サブコマンド名: 関数(引数の配列)}
  ALLOW                 確認なしで通すサブコマンド名の配列
"""
import datetime
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

NAME = "claude-toolkit"
REPO = Path(__file__).resolve().parents[2]
SELF = REPO / "bin" / NAME
TOOLS_DIR = REPO / "tools"
RULES_DIR = REPO / "rules"
STATE_BASE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
STATE_DIR = STATE_BASE / NAME
OLD_STATE_DIRS = [STATE_BASE / "claude-modes"]
SESSIONS_DIR = STATE_DIR / "sessions"
ERROR_LOG = STATE_DIR / "error.log"
SID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
OUR_COMMAND_RE = re.compile(r"claude-(?:modes|toolkit)\s+(hook|statusline)\b")
OUR_ALLOW_RE = re.compile(r"claude-(?:modes|toolkit) \S+ \*\)$")


# ---------- 状態 ----------

def state_path(sid):
    if not sid or not SID_RE.match(sid):
        return None
    return SESSIONS_DIR / f"{sid}.json"


def load_state(sid):
    p = state_path(sid)
    if not p or not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(sid, state):
    p = state_path(sid)
    if not p:
        raise ValueError(f"不正なセッション ID: {sid!r}")
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def take_session(args):
    """--session を取り出し、セッション ID と残りの引数を返す。"""
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID")
    rest = []
    it = iter(args)
    for a in it:
        if a == "--session":
            sid = next(it, None)
        else:
            rest.append(a)
    if not sid:
        sys.exit("セッション ID が分からない。--session で渡してください")
    return sid, rest


def read_lines(path):
    return [l.rstrip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def log_error(where):
    # フックは失敗しても何も出さず終了コード 0 で抜ける。原因はログにだけ残す
    try:
        import traceback
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        if ERROR_LOG.exists() and ERROR_LOG.stat().st_size > 200_000:
            ERROR_LOG.write_text("", encoding="utf-8")
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"--- {datetime.datetime.now().isoformat(timespec='seconds')} {where}\n{traceback.format_exc()}\n")
    except Exception:
        pass


# ---------- 道具の読み込み ----------

_TOOLS = None


def tools():
    global _TOOLS
    if _TOOLS is not None:
        return _TOOLS
    loaded = []
    for d in sorted(p for p in TOOLS_DIR.iterdir() if (p / "tool.py").exists()):
        try:
            spec = importlib.util.spec_from_file_location(f"toolkit_tool_{d.name}", d / "tool.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.TOOL_NAME = d.name
            loaded.append(mod)
        except Exception:
            log_error(f"load tool {d.name}")
    _TOOLS = sorted(loaded, key=lambda m: getattr(m, "ORDER", 100))
    return _TOOLS


def each(fn_name, *args):
    """各道具の fn_name を呼び、(道具, 戻り値) を返す。失敗した道具は飛ばしてログに残す。"""
    for t in tools():
        fn = getattr(t, fn_name, None)
        if fn is None:
            continue
        try:
            yield t, fn(*args)
        except Exception:
            log_error(f"{t.TOOL_NAME}.{fn_name}")


def skill_dirs():
    return sorted(p.parent for p in TOOLS_DIR.glob("*/skills/*/SKILL.md"))


# ---------- フック ----------

def build_context(sid, state, headers, extras, transcript_path=None):
    info = {"header": bool(headers), "transcript_path": transcript_path}
    lines = [f"<{NAME}>"] + headers + extras
    for _, ls in each("context", sid, state, info):
        lines += ls or []
    lines.append("ユーザーへの返答の書き方:")
    lines += read_lines(RULES_DIR / "writing.md")
    lines.append(f"</{NAME}>")
    return "\n".join(lines)


def on_prompt(sid, prompt, transcript_path=None, cwd=None):
    state = load_state(sid)
    info = {"transcript_path": transcript_path, "cwd": cwd}
    headers, extras = [], []
    for _, r in each("on_prompt", sid, prompt or "", state, info):
        if r:
            if r.get("header"):
                headers.append(r["header"])
            extras += r.get("extra") or []
    return build_context(sid, state, headers, extras, transcript_path)


def on_session_start(sid):
    state = load_state(sid)
    if not any(v for _, v in each("active", state)):
        return None
    return build_context(sid, state, ["会話が要約または再開された。モードとボードの紐づけは引き続き有効。"], [])


def cmd_hook(args):
    try:
        data = json.load(sys.stdin)
        event = data.get("hook_event_name")
        sid = data.get("session_id")
        if os.environ.get("CLAUDE_TOOLKIT_DEBUG"):
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            with (STATE_DIR / "debug.log").open("a", encoding="utf-8") as f:
                f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {event} {data.get('source', '')} {sid}\n")
        if event == "UserPromptSubmit":
            ctx = on_prompt(sid, data.get("prompt", ""), data.get("transcript_path"), data.get("cwd"))
        elif event == "SessionStart":
            ctx = on_session_start(sid)
        else:
            return
        if ctx:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": ctx}},
                             ensure_ascii=False))
    except Exception:
        log_error("hook")


def cmd_statusline(args):
    try:
        data = json.load(sys.stdin)
        state = load_state(data.get("session_id"))
        parts = []
        for _, ls in each("status", state):
            parts += ls or []
        if parts:
            print(" ｜ ".join(parts))
    except Exception:
        log_error("statusline")


# ---------- インストール ----------

HOOK_EVENTS = ["UserPromptSubmit", "SessionStart"]


def allow_rules():
    rules = []
    for t in tools():
        for sub in getattr(t, "ALLOW", []):
            rules.append(f"Bash({SELF} {sub} *)")
    return rules


def merge_settings(settings):
    """settings を書き換え、変えた内容の説明を返す。"""
    changes = []
    hook_cmd = f"{SELF} hook"
    hooks = settings.setdefault("hooks", {})
    for event in HOOK_EVENTS:
        groups = hooks.setdefault(event, [])
        found = False
        for g in groups:
            for h in g.get("hooks", []):
                if isinstance(h.get("command"), str) and OUR_COMMAND_RE.search(h["command"]):
                    found = True
                    if h["command"] != hook_cmd:
                        h["command"] = hook_cmd
                        changes.append(f"{event} のフックの場所を更新")
        if not found:
            groups.append({"hooks": [{"type": "command", "command": hook_cmd, "timeout": 10}]})
            changes.append(f"{event} にフックを追加")

    status_cmd = f"{SELF} statusline"
    sl = settings.get("statusLine")
    if sl is None:
        settings["statusLine"] = {"type": "command", "command": status_cmd}
        changes.append("ステータスラインを追加")
    elif isinstance(sl.get("command"), str) and OUR_COMMAND_RE.search(sl["command"]):
        if sl["command"] != status_cmd:
            sl["command"] = status_cmd
            changes.append("ステータスラインの場所を更新")
    else:
        changes.append("注意: 別のステータスラインが設定済みなので触っていない")

    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    wanted = allow_rules()
    for r in [r for r in allow if isinstance(r, str) and OUR_ALLOW_RE.search(r) and r not in wanted]:
        allow.remove(r)
        changes.append(f"許可リストから外す: {r}")
    for rule in wanted:
        if rule not in allow:
            allow.append(rule)
            changes.append(f"許可リストに追加: {rule}")
    return changes


def ours_or_dangling(link):
    """前の場所を指したままのリンクなら True。"""
    target = os.readlink(link)
    return not link.exists() or "/claude-modes/" in target or "/claude-toolkit/" in target


def link_skills(config_dir, dry_run):
    for skill in skill_dirs():
        link = config_dir / "skills" / skill.name
        if link.is_symlink():
            if link.resolve() == skill.resolve():
                print(f"  スキル {skill.name}: リンク済み")
                continue
            if not ours_or_dangling(link):
                print(f"  スキル {skill.name}: 注意: {link} は別の場所 {os.readlink(link)} を指しているので触っていない")
                continue
            print(f"  スキル {skill.name}: {link} を {skill} に張り替える")
            if not dry_run:
                link.unlink()
                link.symlink_to(skill)
        elif link.exists():
            print(f"  スキル {skill.name}: 注意: {link} がリンクではない実体なので触っていない")
        else:
            print(f"  スキル {skill.name}: {link} -> {skill} を作る")
            if not dry_run:
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(skill)


def install_one(config_dir, dry_run):
    print(f"== {config_dir}")
    if not config_dir.is_dir():
        print("  ディレクトリがないので飛ばした")
        return
    link_skills(config_dir, dry_run)

    path = config_dir / "settings.json"
    original = path.read_text(encoding="utf-8") if path.exists() else "{}"
    settings = json.loads(original)
    changes = merge_settings(settings)
    new_text = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    if new_text == original or json.loads(new_text) == json.loads(original):
        print("  settings.json: 変更なし" + "".join(f"\n    {c}" for c in changes if c.startswith("注意")))
        return
    for c in changes:
        print(f"  settings.json: {c}")
    if dry_run:
        return
    if path.exists():
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"settings.json.bak-{NAME}-{stamp}")
        backup.write_text(original, encoding="utf-8")
        print(f"  バックアップ: {backup}")
    path.write_text(new_text, encoding="utf-8")


def migrate_state(dry_run):
    """前の名前の状態のフォルダから、セッションの状態を引き継ぐ。"""
    for old in OLD_STATE_DIRS:
        old_sessions = old / "sessions"
        if not old_sessions.is_dir():
            continue
        moved = 0
        for f in old_sessions.glob("*.json"):
            dest = SESSIONS_DIR / f.name
            if dest.exists():
                continue
            moved += 1
            if not dry_run:
                SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
                os.replace(f, dest)
        print(f"== 状態: {old_sessions} から {moved} 件を {SESSIONS_DIR} に移す")


def cmd_install(args):
    dry_run = "--dry-run" in args
    dirs = [Path(a).expanduser() for a in args if a != "--dry-run"]
    if not dirs:
        # ホーム直下の .claude と .claude-* のディレクトリを、すべてプロファイルとして扱う
        dirs = sorted(p for p in Path.home().glob(".claude*") if p.is_dir() and re.fullmatch(r"\.claude(-.+)?", p.name))
    for d in dirs:
        install_one(d, dry_run)
    migrate_state(dry_run)
    if dry_run:
        print("(--dry-run なので何も書き換えていない)")


# ---------- 入口 ----------

USAGE = f"""{NAME}: Claude Code で使う道具の集まり

共通のサブコマンド:
  hook            Claude Code のフックから呼ばれる。標準入力にフックの JSON を受け取る
  statusline      ステータスラインから呼ばれる
  install [--dry-run] [設定ディレクトリ...]
                  スキルのリンクと settings.json の設定を入れる。省略時はホーム直下の .claude と .claude-* すべて
道具ごとのサブコマンド:
"""


def main():
    commands = {"hook": cmd_hook, "statusline": cmd_statusline, "install": cmd_install}
    tool_cmds = {}
    for t in tools():
        for name, fn in getattr(t, "COMMANDS", {}).items():
            tool_cmds[name] = (t.TOOL_NAME, fn)
    if len(sys.argv) < 2 or (sys.argv[1] not in commands and sys.argv[1] not in tool_cmds):
        sys.exit(USAGE + "".join(f"  {n}  ({tool})\n" for n, (tool, _) in sorted(tool_cmds.items())))
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd in commands:
        commands[cmd](args)
    else:
        tool_cmds[cmd][1](args)
