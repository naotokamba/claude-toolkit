---
name: i
description: 推理モードに入る。/mode i と同じ。続けて文を書くと、そのモードで話す
disable-model-invocation: true
argument-hint: "[続けて話す内容]"
---

引数: $ARGUMENTS

モードの切り替えはフックが処理済みで、その結果を `<claude-toolkit>` として渡している。

- 引数がなければ、「推理モードにしました。」と 1 行だけ伝えて終える。作業や提案を始めない
- 引数があれば、それを推理モードでのユーザーの発言として扱い、そのモードのルールで応答する
- `<claude-toolkit>` が渡されていなければ、「モードのフックが入っていません。claude-toolkit の install を実行してください」とだけ伝えて終える
