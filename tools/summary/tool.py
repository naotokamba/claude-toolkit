"""summary: 今このセッションで何をしているかを、決まった欄でまとめさせる。"""
import re

from toolkit import core

ORDER = 30
SUMMARY_CMD_RE = re.compile(r"^\s*/summary(?=\s|$)")


def on_prompt(sid, prompt, state, info):
    if not SUMMARY_CMD_RE.match(prompt):
        return None
    goal = state.get("goal")
    return {
        "header": "ユーザーが今の状況のまとめを求めた。",
        "extra": [
            f"記録済みの目的: {goal}" if goal else "記録済みの目的: まだない",
            f"紐づいたボード: {state.get('board') or 'なし'}",
            f"会話の記録ファイル: {info.get('transcript_path') or '不明'}",
        ],
    }
