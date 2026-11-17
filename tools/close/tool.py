"""close: このセッションを閉じてよいかを判断させる。"""
import re

ORDER = 40
CLOSE_CMD_RE = re.compile(r"^\s*/close(?=\s|$)")


def on_prompt(sid, prompt, state, info):
    if not CLOSE_CMD_RE.match(prompt):
        return None
    goal = state.get("goal")
    return {
        "header": "ユーザーが、このセッションを閉じてよいかを聞いた。",
        "extra": [
            f"記録済みの目的: {goal}" if goal else "記録済みの目的: まだない",
            f"紐づいたボード: {state.get('board') or 'なし'}",
            f"作業ディレクトリ: {info.get('cwd') or '不明'}",
            f"会話の記録ファイル: {info.get('transcript_path') or '不明'}",
        ],
    }
