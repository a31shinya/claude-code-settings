---
name: feedback-to-slide
description: |
  スライド（PDF、またはClaude Codeで作ったHTML+CSSスライド）を画像化してレビューHTMLを生成し、
  ユーザーが矩形マーク＋コメントで書き込んだフィードバック(feedback.json、クリップボード貼付 or ファイル)を
  読み取ってスライドを修正する。既存ファイルの入力はPDF限定（PPTX/GoogleスライドはユーザーがPDFエクスポートして渡す）。
  「スライドにフィードバックしたい」「スライドをレビューして」「矩形でマークして直したい」
  「フィードバックした」（このスキルで生成したレビューHTMLに対する報告、JSON文字列が貼られることが多い）等の指示で使う。
---

# feedback-to-slide

詳細仕様（入力元別の対応表、UI仕様、JSONスキーマ、NG判定ロジック等）は必ず [`reference/spec.md`](./reference/spec.md) を参照すること。ここではオーケストレーション手順のみを記す。

このスキルは自己完結型（`scripts/`・`templates/`・`package.json`・`node_modules`を全てこのディレクトリ配下に持つ）。`.claude/skills/feedback-to-slide/` ごとコピーすれば、`~/.claude/skills/feedback-to-slide/` のようにユーザーレベルへ移動してどのプロジェクトからも呼び出せる。

## 前提

- **スクリプトの呼び出しは常にこのSKILL.mdと同じディレクトリを基準にした絶対パスで行うこと。** 例えば `node scripts/init.js ...` ではなく、このファイルが置かれているディレクトリ（＝このスキルのインストール場所）を基準に `node <このSKILL.mdのあるディレクトリ>/scripts/init.js ...` のように実行する。カレントディレクトリ（cwd）はユーザーの作業プロジェクトのままにしておくこと（`cd`しない）。
- 依存パッケージ（`node_modules`）はこのスキルのディレクトリ内に同梱・管理する。未導入または壊れている場合は、このスキルのディレクトリで `npm install` を実行するよう案内する。
- PDF入力には`pdftoppm`（poppler、システムにインストールされたコマンド）が必要。`which pdftoppm`で確認し、無ければ`brew install poppler`を案内する。
- セッション名はユーザーに確認するか、入力ファイル名から適当に生成する（例: `deck-20260910`）。作業ファイルは**呼び出し元のカレントディレクトリ**基準で `.feedback-to-slide/work/<セッション名>/` に置かれる（`scripts/lib/paths.js`参照）。プロジェクトごとに分離されるので、他プロジェクトのセッションと衝突しない。

## `init`（新規レビューを開始する）

呼び出し例: 「このPDFにフィードバックしたい」「このスライド(HTML)をレビューして」

1. ユーザーから入力（PDFファイルパス、またはClaude Code製HTML+CSSスライドのディレクトリパス）を受け取る。パスが未指定なら確認する。
2. `node <skill-dir>/scripts/init.js --input <path> --session <セッション名>` を実行する（`<skill-dir>`はこのSKILL.mdが置かれているディレクトリの絶対パス。cwdはユーザーの作業ディレクトリのまま）
   - PDFの場合: 内部で`pdftoppm`を呼び、`.feedback-to-slide/work/<セッション名>/pages/page-XX.png`を生成
   - HTML+CSSディレクトリの場合: 内部でPuppeteerを起動し、ページごとにスクリーンショットを生成
3. 生成された `.feedback-to-slide/work/<セッション名>/review.html` のパスをユーザーに提示し、ブラウザで開いて矩形マーク・コメント入力をするよう案内する（`open <path>` でも良い）
4. 「全ページ確認したらフィードバックしたと伝えてください」と伝えて待つ

## `apply`（フィードバックを反映する）

呼び出し例: ユーザーが「フィードバックした」と伝えてくる（JSON文字列が貼られている、またはダウンロードしたファイルパスを伝えてくる）

1. フィードバックJSONを `.feedback-to-slide/work/<セッション名>/feedback.json` として保存する
   - 会話にJSON文字列が貼られていればそれをそのままWriteする
   - ファイルパスが伝えられた場合はそのファイルを読み、同じ場所にコピー/保存する
2. `node <skill-dir>/scripts/apply.js --session <セッション名>` を実行し、`.feedback-to-slide/work/<セッション名>/apply-report.json` を得る（ページごとの `action`: `no-change` / `apply-annotations` / `rebuild-page` / `delete-page` / `unspecified`）
3. `apply-report.json` の内容とfeedback.json本文を照らし合わせながら、ページごとに対応する:
   - **HTML+CSS入力**の場合、Claude自身が該当ページの`.html`ファイルをEditツールで直接修正する（矩形の`rect`座標＋`comment`を手がかりに、該当箇所を特定して直す。`rebuild-page`はページ全体を書き直す。`delete-page`は該当ファイルを削除し以降のページ番号を振り直す）
   - **PDF入力**の場合、自動修正はできないため、`action`ごとの指摘内容をテキストでまとめてユーザーに提示する（実装方法は`reference/spec.md`の「入力元ごとの仕様・修正可否」参照）
4. HTML+CSS入力で修正を行った場合は `node <skill-dir>/scripts/init.js --input <同じhtmlディレクトリ> --session <セッション名>` を再実行して画像とreview.htmlを再生成し、更新後のパスをユーザーに提示する
5. 対応できなかった項目（`unspecified`、PDF入力での指摘等）があれば、その一覧を明示して終える

## `export`（最終成果物を書き出す）

呼び出し例: 「PDFで書き出して」「PPTXにして」「HTMLでちょうだい」

1. `node <skill-dir>/scripts/export.js --session <セッション名> --format <pdf|pptx|html>` を実行する
2. `.feedback-to-slide/work/<セッション名>/output/` 配下に生成されたファイルパスをユーザーに提示する

## 注意

- `<skill-dir>`は常にこのSKILL.mdファイル自身の絶対パスから求めること（`cd`でカレントディレクトリを変えない）。ユーザーの作業プロジェクトを跨いでも、作業ファイルの置き場所（`.feedback-to-slide/work/`）だけがcwd基準で変わり、スクリプト・テンプレート・依存パッケージは常に`<skill-dir>`基準で見つかる。
- 各スクリプトは `<skill-dir>/scripts/` 配下のNode.js実装（`init.js`/`apply.js`/`export.js`、共通処理は`scripts/lib/`）。挙動を変える場合はスクリプト本体を修正し、`reference/spec.md`の記述も合わせて更新すること。
- レビューHTMLのテンプレートは `<skill-dir>/templates/review-template.html`（vanilla HTML/CSS/JS、外部依存なし）。UIの見た目・操作感を変える場合はここを編集する。
