---
name: q
description: モードを抜ける。/mode off と同じ。続けて文を書くと、モードなしで話す
disable-model-invocation: true
argument-hint: "[続けて話す内容]"
---

引数: $ARGUMENTS

モードの解除はフックが処理済みで、その結果を `<claude-toolkit>` として渡している。

- 引数がなければ、「モードを解除しました。」と 1 行だけ伝えて終える。作業や提案を始めない
- 引数があれば、それをモードなしでのユーザーの発言として扱って応答する
- `<claude-toolkit>` が渡されていなければ、「モードのフックが入っていません。claude-toolkit の install を実行してください」とだけ伝えて終える
