---
name: mode
description: 会話のモードを切り替える。purpose・diverge・converge・work・understand・infer・off。頭文字 p・d・c・w・u・i や日本語名でも指定できる。引数なしで今のモードと目的を表示
disable-model-invocation: true
argument-hint: "purpose | diverge | converge | work | understand | infer | off [続けて話す内容]"
---

引数: $ARGUMENTS

モードの切り替えはフックが処理済みで、その結果を `<claude-toolkit>` として渡している。

- 渡された内容に沿って、今のモードを 1 行で伝える。例: 「発散モードにしました。」
- 引数がなければ、今のモードと記録済みの目的を 1 行ずつ伝えて終える
- モード名のあとに文が続いていれば、それを新しいモードでのユーザーの発言として扱い、そのモードのルールで応答する
- 続く文がなければ、1 行伝えて終える。作業や提案を始めない
- `<claude-toolkit>` が渡されていなければ、フックが入っていない。「モードのフックが入っていません。claude-toolkit の install を実行してください」とだけ伝えて終える
