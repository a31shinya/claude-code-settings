# feedback-to-slide 詳細仕様

SKILL.mdから参照される詳細資料。実装・修正作業の前に該当セクションを確認すること。

このスキルは自己完結型で、`scripts/`・`templates/`・`package.json`・`node_modules`は全てこのSKILL.mdと同じディレクトリ（`<skill-dir>`）配下にある。セッションの作業ファイル（`work/`以下）だけは呼び出し元のカレントディレクトリ基準（`<cwd>/.feedback-to-slide/work/`）に置かれる。以下、パス表記は `<skill-dir>` と `.feedback-to-slide/work/` で統一する。

## ハード制約

- **商用ツールは導入しない。** Node.js / Python のOSSライブラリのみ使用可。
- **既存ファイルの入力形式はPDF限定。** PPTXやGoogleスライドはユーザー側で標準機能を使いPDFエクスポートしてから渡してもらう。PPTXの直接取り込み・LibreOffice等の変換ツールは導入しない。
- レビューHTMLの表示形式は入力元によらず「画像化したスライド」に統一する（HTML/CSSスライドも一旦スクリーンショットして画像として見せる）。ライブHTML埋め込み表示はしない。
- 依存を追加する場合は下記「依存ツール」に明記すること（隠れた依存を作らない）。

## 依存ツール

- PDF → 画像変換: `pdftoppm`（poppler-utils、外部コマンド。`brew install poppler`）
- HTML+CSS → 画像変換: `puppeteer`（npm, ヘッドレスChromiumでスクリーンショット）
- 画像 → PDF生成（エクスポート時）: `pdf-lib`（npm, 純JS、外部バイナリ不要）
- 画像 → PPTX生成（エクスポート時）: `pptxgenjs`（npm）

## 入力元ごとの仕様・修正可否

### 1. Claude Codeで生成したHTML+CSSスライド
- 想定フロー: 別セッションでClaude Codeとスライド内容を相談し、HTML+CSSのスライドを先に作成する。1ページ=1つの`.html`ファイルとして`<スライドディレクトリ>/page-01.html`のように連番で並べておく。その後このスキルにディレクトリパスを渡してレビュー・修正を依頼する。
- 修正方法: Claudeがそのページに対応するHTML/CSSファイルを直接編集する。最も確実に自動修正できる入力元。
- **キャンバスサイズの規約**: `<skill-dir>/scripts/init.js`のPuppeteerビューポートは`1241×1754px`（A4 @150dpi相当）に固定している。スライドHTMLの`html,body`は`width:1241px`とし、`height`は各ページで固定して`overflow:hidden`にすること（実例として`pdf-feedback-tool`プロジェクトの`sources/paper-tower/style.css`を参照）。これにより`fullPage`スクリーンショットが常に同じキャンバスサイズになり、レビューHTML上の矩形座標(`%`指定)がページ間で一貫する。
- 表示用画像化: Puppeteerで各HTMLファイルをスクリーンショットして生成（`<skill-dir>/scripts/init.js`が自動実行）。

### 2. ローカルのPDFファイル
- 指定方法: スキル起動時にファイルパスを渡す。
- PowerPoint（PPTX）やGoogleスライドが元の場合も、ユーザー側で標準機能を使いPDF形式でエクスポートしてから渡してもらう。PPTXファイルをそのまま渡された場合は、PDF形式で再エクスポートするよう案内する。
- 元がどう生成されたか分からない「フラットなPDF」の場合、ページ内容をピクセル単位で編集する手段は基本的に無い。以下のいずれかで対応する。
  - 元データ（Markdown/Marp、LaTeX、HTML、PowerPoint本体等）が別途あるならそちらを教えてもらい、そちらを編集→再度PDF化してもらう
  - 元データが無い場合は、フィードバック内容をテキストでまとめて提示し、ユーザーに元ツール側での手直しを依頼する（自動修正は不可）
- 画像化: `pdftoppm -png -r 150`でページごとにPNG化するのみ。

## レビューHTMLのUI仕様

まじん式（マークボタン→ドラッグで矩形指定）をベースに、tetumemo氏の実装で確認した以下の機能を追加する。実装は `<skill-dir>/templates/review-template.html`（vanilla HTML/CSS/JS、外部依存なし）。

- 上部: ページ番号タブ（P01, P02…）、←前/次→、x/nページカウンター
- 左側: スライド画像。長い画像はスクロール可能な枠内に表示。画像右上に「マーク」ボタン
  - 「マーク」ボタン押下後、画像上をドラッグして矩形を指定（誤操作防止のため、ボタンを押していない状態でのドラッグでは矩形を作らない）
  - 矩形には連番バッジ（①②③…）を自動採番
- 右側:
  - 矩形ごとの一覧。各矩形に自由記述のコメント欄＋個別「消す」（削除）ボタン
  - ページ全体の判定ボタン: OK / 要修正 / NG（意味は下記）
  - ページ全体向けの自由記述コメント欄
  - 参考画像添付欄（ユーザー自身の画面キャプチャ等をローカル添付、Base64で保持）
- フッター:
  - 「書いた（まとめて出す）」ボタン: 全ページ分のフィードバックをJSONにまとめ、モーダルで「JSONをコピー」（クリップボード、主経路）と「ファイルでダウンロード」（`feedback.json`、副経路）を提供
  - 「全部消す」ボタン: 全ページの矩形・コメント・判定をリセット
  - 進捗表示: 「判定 x/nページ／赤枠 y個」

### ページ判定（OK / 要修正 / NG）の意味

- **OK**: このページは確定。修正不要。
- **要修正**: 赤枠で指摘した箇所に対応すればよい。矩形の`comment`を個別に処理する。
- **NG**: 赤枠の指摘では収まらない全面作り直し（ページ構成・コンセプトから練り直し）。矩形は使わず`pageComment`に方向性が書かれる想定。
  - ただし`pageComment`に「削除」「不要」「消して」等、ページ自体の削除を意図する文言が含まれる場合は、作り直しではなく**そのページをスライドから削除する**処理として扱う。
  - 判定が曖昧な場合は自動判断せずユーザーに確認する。
  - `<skill-dir>/scripts/apply.js`はこの判定を機械的に行い（正規表現ベースの一次判定）、`action`フィールド（`no-change`/`apply-annotations`/`rebuild-page`/`delete-page`/`unspecified`）としてレポートする。最終判断はClaudeが`pageComment`本文を読んで確定させること（正規表現はあくまで一次スクリーニング）。

## データ形式（feedback.json）

```json
{
  "exportedAt": "2026-09-10T15:00:00+09:00",
  "pages": [
    {
      "page": 1,
      "judgement": "要修正",
      "pageComment": "全体的に文字が小さい",
      "annotations": [
        {
          "id": 1,
          "rect": { "xPct": 12.3, "yPct": 5.0, "wPct": 30.0, "hPct": 8.0 },
          "comment": "この図解を右に寄せて"
        }
      ],
      "referenceImage": null
    }
  ]
}
```

矩形座標は画像サイズに依存しないよう`%`指定（`xPct`/`yPct`/`wPct`/`hPct`）で統一する。

## セッション用ディレクトリ構成

呼び出し元のカレントディレクトリ（ユーザーの作業プロジェクト）を`<cwd>`とする。

```
<cwd>/.feedback-to-slide/work/<セッション名>/
  state.json        # init時に生成。sourceType/sourcePath/pages(ページ番号と画像相対パス)
  pages/             # ページ画像 (page-01.png ...)
  review.html        # レビュー用HTML（<skill-dir>/templates/review-template.htmlから生成）
  feedback.json       # ユーザーが書き出したフィードバック（Claudeが会話から受け取り書き込む）
  apply-report.json  # apply実行時に生成される、ページごとのaction判定結果
  output/             # export実行時の最終成果物 (pdf/pptx/html)
```

## Claude Codeでのフィードバック受け取りフロー

1. ユーザーがレビューHTML上で「書いた（まとめて出す）」を押す
   - 主経路: 「JSONをコピー」でクリップボードにコピーし、会話にそのままテキストとして貼り付ける
   - 副経路: 「ファイルでダウンロード」で`feedback.json`を保存し、ファイルパスを伝える
2. ユーザーが会話上で「フィードバックした」等と伝える（JSON本文が貼られていればそれを解釈、ファイルパスならClaudeが読み込む）
3. Claudeは受け取ったJSONを`.feedback-to-slide/work/<セッション名>/feedback.json`として保存し、`<skill-dir>/scripts/apply.js`を実行して`apply-report.json`（ページごとのaction）を得る
4. `action`ごとにClaudeが対応する:
   - `no-change`: 何もしない
   - `apply-annotations`: 対応する矩形の`comment`を読み、入力元がHTML+CSSならソースを直接編集
   - `rebuild-page`: `pageComment`の方向性に沿ってページを作り直す（HTML+CSS入力のみ自動対応可）
   - `delete-page`: 該当ページのHTMLファイルを削除し、ページ番号を振り直す
   - `unspecified`: 判定が空の場合はスキップし、その旨をユーザーに伝える
5. 入力元がフラットPDFで自動修正できない場合は、対応できない旨と代替手段（テキストでの修正指示リスト等）を明示する
6. 対応後、`<skill-dir>/scripts/init.js`相当の画像再生成処理（HTML+CSSソースの場合のみ）を行い、レビューHTMLを更新する

## 未決事項 / TODO

- PDF入力（フラットPDF）に対する「rebuild-page」「delete-page」の自動化は非対応（元データが無いため）。将来的にMarp/Markdown等の中間フォーマットを経由する運用を検討する余地あり
- Google Slides APIによる直接連携（読み取り・書き戻し）はスコープ外（現状はユーザーが手動でPDFエクスポートする運用）
- `<skill-dir>/scripts/export.js`のpptx出力は画像貼り付け方式（テキストや図形としての再編集はできない、見た目の書き出しのみ）
