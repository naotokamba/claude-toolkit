"""issue: /issue new で、作る先のリポジトリの決まりに沿って issue を作らせる。"""
import re

ORDER = 46
ISSUE_CMD_RE = re.compile(r"^\s*/issue(?=\s|$)")


def on_prompt(sid, prompt, state, info):
    if not ISSUE_CMD_RE.match(prompt):
        return None
    return {
        "header": "ユーザーが /issue を使った。",
        "extra": [
            f"紐づいたボード: {state.get('board') or 'なし'}",
            f"作業ディレクトリ: {info.get('cwd') or '不明'}",
            f"会話の記録ファイル: {info.get('transcript_path') or '不明'}",
        ],
    }
