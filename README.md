# claude-toolkit

Claude Code で使うスキルを置くリポジトリ。

| スキル | 何をするか |
|---|---|
| `/hearing` | 要求を聞き取って、4 行にまとめる。今、こうなってほしい、今回の範囲、気にしていること。Fable 5.2 の medium のセッションで使う想定 |
| `/fable-prompting` | Fable 5.2 の別セッションに渡す指示文を、対話で作る。Fable が設計と判断をし、実装は Opus 5.5 のサブエージェントに渡す |
| `/opus-prompting` | Opus 5.5 の別セッションに渡す指示文を、対話で作る。Opus が 1 つのセッションで最後まで進める。1 段易しい仕事向け |

## インストール

リポジトリを clone し、各スキルのフォルダを Claude Code の設定ディレクトリの `skills/` にリンクする。

```bash
git clone https://github.com/naotokamba/claude-toolkit.git ~/claude-work/naotokamba/claude-toolkit
mkdir -p ~/.claude/skills
for s in hearing fable-prompting opus-prompting; do
  ln -sfn ~/claude-work/naotokamba/claude-toolkit/skills/$s ~/.claude/skills/$s
done
```

設定ディレクトリを `~/.claude` 以外にも持っているときは、それぞれの `skills/` に同じリンクを張る。

新しく開いたセッションで `/hearing`、`/fable-prompting`、`/opus-prompting` と打つと使える。リンクなので、`git pull` すれば中身は最新になる。

## アンインストール

```bash
rm ~/.claude/skills/hearing ~/.claude/skills/fable-prompting ~/.claude/skills/opus-prompting
```

## 以前の道具

2026-11-20 に、それまでの道具をすべて削除した。中身は git の履歴の a645112 にある。
