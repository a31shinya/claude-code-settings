---
name: save-x-article
description: X（Twitter）の記事・ポストのURLを渡されたら、本文・見出し・画像・コード/プロンプト枠まで忠実に再現したMarkdownを ~/x-article に保存する。保存済みURLは ~/x-article/articles.csv で管理し、登録済みURLは保存せずスキップする。「このX記事を保存して」「x.com/... をMarkdownにして」「この記事をローカルに残したい」「Xの記事をアーカイブして」など、x.com / twitter.com / x.com/i/article のURLを保存・アーカイブ・Markdown化したい指示で必ず使う。
---

# X記事をMarkdownで忠実に保存する

X（Twitter）のポストURL・記事URLを受け取り、`~/x-article/` 配下に
`<タイトル>.md` ＋ `images/` ＋ `raw.json` として保存する。保存したURLは
`~/x-article/articles.csv` に台帳として記録し、登録済みURLは再取得せずスキップする。

## 前提

- 保存先ルートは `~/x-article`（環境変数 `X_ARTICLE_DIR` で上書き可）
- 保存済みURLの台帳は `~/x-article/articles.csv`（1行目はヘッダ `URL,記事フォルダ名`）
- 本文は fxtwitter の公開API（`api.fxtwitter.com`）から取得する。X本体はログイン必須で取れない
- 変換スクリプト: `scripts/x_article_to_md.py`（Python3標準ライブラリのみ、追加インストール不要）
- ネットワークアクセスの許可を求められたら、そのまま実行してよい旨をユーザーに伝えて進める

## 手順

### 1. 保存する

URLは複数まとめて渡せる。

```bash
python3 ~/.claude/skills/save-x-article/scripts/x_article_to_md.py \
  "https://x.com/<user>/status/<id>" "https://x.com/<user2>/status/<id2>"
```

出力は各記事ごとに以下の構成になる。

```
~/x-article/
    articles.csv                             保存済み台帳（1行目にヘッダ URL,記事フォルダ名）
    2026-09-08_ai_jitan_<タイトル>/
        <タイトル>.md  本文（YAMLフロントマター付き。ファイル名もタイトル）
        images/       cover.jpg, img-01.jpg, ...
        raw.json      取得した生JSON（再生成用）
```

### 重複スキップ

渡されたURLが `articles.csv` にすでにあれば、取得も保存もせず `SKIP` を出して次のURLに進む。
判定はステータスID（`/status/<id>`）で行うので、`x.com` と `twitter.com`、
クエリ文字列付きURLの違いは吸収される。意図的に取り直すときだけ `--overwrite` を付ける。

主なオプション:

| オプション | 用途 |
| --- | --- |
| `--outdir DIR` | 保存先ルートを変える |
| `--no-images` | 画像を落とさずリモートURL参照にする |
| `--from-json FILE` | `raw.json` から再取得なしで作り直す |
| `--overwrite` | 同名ディレクトリを上書きし、CSV登録済みURLでも再保存する（既定は `_2` 等を付けて別保存） |
| `--list-blocks` | 記事のブロック一覧を番号付きで表示する |
| `--fence-blocks 91,93,95` | 指定ブロックを生テキストのままコードブロック化する |

### 2. 実行結果を確認する

スクリプトは以下を標準出力に出す。必ず目を通すこと。

- `SKIP <url> (登録済み: <dir>)` … `articles.csv` にある既存URL。保存していない
- `SAVED <path>` … 出力先
- `blocks: N / code_entities: N` … 記事ブロック数と、X側でコード枠として書かれた数
- `images: N 件 / 未取得 N 件` … `MISSING` が出たら、その画像だけ取得に失敗している
- `CSV: articles.csv に追記 (<dir>)` … 台帳への登録結果

`MISSING` が出た場合は、そのURLを個別に `curl -o` で取り直して `images/` に置き、
本文Markdownの該当 `![](...)` を相対パスに直す。

### 3. コード・プロンプト部が本文と混ざっていないか点検する（重要）

X記事の書き手がコード枠（`MARKDOWN` エンティティ）を使っていれば、
スクリプトが自動でフェンス付きコードブロックにする。この場合 `code_entities` が1以上になる。

`code_entities: 0` なのに、記事中にプロンプト例やコードが載っている場合は、
書き手が普通の段落としてプロンプトを書いている。この状態だと本文と混ざるので、次の手順で直す。

1. ブロック一覧を出す（`raw.json` を使えば再取得は不要）

```bash
python3 ~/.claude/skills/save-x-article/scripts/x_article_to_md.py \
  --from-json ~/x-article/<dir>/raw.json --list-blocks
```

2. プロンプト・コード本体にあたるブロック番号を特定する。
   目印は「先頭に `Copy` が付いている」「`⏎`（改行）を多く含む」「直前の見出しが
   『プロンプト』『指示文』などになっている」。見出しや解説文は含めない。

3. その番号を指定して作り直す。

```bash
python3 ~/.claude/skills/save-x-article/scripts/x_article_to_md.py \
  --from-json ~/x-article/<dir>/raw.json --fence-blocks 91,93,95 \
  --overwrite
```

`--fence-blocks` は指定ブロックのテキストを一切加工せずフェンスで囲むだけなので、
文面が変わる心配はない。連続する複数ブロックが1つのプロンプトなら `91-95` のように範囲指定する。

### 4. ユーザーに報告する

保存先パス、画像枚数、コードブロックの扱い（自動 or `--fence-blocks` で指定）を簡潔に伝える。
スキップしたURLがあれば、その旨と登録済みフォルダ名も伝える。

## 忠実さのために守っていること

スクリプトは以下を保証しているので、本文Markdownを手で編集して整えないこと。
手直しが必要になった場合は、原因をスクリプト側で直すか `--fence-blocks` で対処する。

- 見出し階層: 記事タイトル → `#`、`header-one` → `##`、`header-two` → `###`
- 太字は Draft.js のインラインスタイル範囲を UTF-16 オフセットどおりに `**` で再現する
  （絵文字を含む文でもズレない）
- 段落内の改行は Markdown の強制改行（行末2スペース）として保持する
- 箇条書き・番号リストは種類と入れ子の深さを保持し、番号は連番で振る
- 記事内の区切り線（`DIVIDER`）は `---`
- 画像は `images/` に元解像度（`?name=orig`）で保存し、相対パスで参照する。
  画像キャプションは画像直下にイタリックで置く
- コード枠はフェンスで囲む。中身に ` ``` ` が含まれる場合はフェンスを4本以上に伸ばして壊さない
- 記事以外の通常ポストの場合は、本文・展開済みURL・添付画像・投票・引用ポストを保存する

## トラブルシューティング

- **`取得に失敗しました`**: 対象が鍵アカウント・削除済み・センシティブ設定の可能性。
  URLをブラウザで開いて公開状態か確認する。fxtwitter 側の一時障害なら少し待って再実行する
- **本文が空**: `raw.json` の `tweet.article.content.blocks` を直接確認する。
  記事ではなくスレッドの場合、記事本文は存在しない
- **タイトルが長すぎる**: ディレクトリ名は60文字で切っている。フロントマターの `title` は全文が入る
- **同じ記事を再保存したい**: `--overwrite` を付ける。CSVの重複スキップも同時に無視される
- **スキップされたが保存し直したい**: `--overwrite` を付けるか、`~/x-article/articles.csv` の該当行を削除する
