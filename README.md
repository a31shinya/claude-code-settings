
# 各種設定ファイルについて

## home
ホームディレクトリに配置するファイルを格納。
そのままコピーする想定。

### CLAUDE.md
- 全セッション共通のルールを書く。言語設定とリアクション系を禁止することだけ。

### settings.json
- 全セッション共通のルールを書く。.envの読み取りとファイル削除だけ禁止している。


## project
### CLAUDE.md
以下のセクションを定義する。
- Environment
- Work Rules & Principles
- Commands
- Project Conventions
- Compaction Rules

### settings.json
- NotebookLMの操作を許可するときはBash(nlm *)を許可。

# 各種スキルについて

## daily-news-summary
Notebook（[nikkei-news]YYYY/MM/DD）の内容をまとめるスキル。

