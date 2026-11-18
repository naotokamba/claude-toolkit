"""later: 別の日にやる残作業が、その日に issue を見れば進められる形で残っているかを確かめさせる。"""
import re

ORDER = 45
LATER_CMD_RE = re.compile(r"^\s*/later(?=\s|$)")


def on_prompt(sid, prompt, state, info):
    if not LATER_CMD_RE.match(prompt):
        return None
    return {
        "header": "ユーザーが /later で、別の日にやる残作業が issue に整って残っているかを確かめるよう求めた。",
        "extra": [
            f"紐づいたボード: {state.get('board') or 'なし'}",
            f"作業ディレクトリ: {info.get('cwd') or '不明'}",
            f"会話の記録ファイル: {info.get('transcript_path') or '不明'}",
        ],
    }
