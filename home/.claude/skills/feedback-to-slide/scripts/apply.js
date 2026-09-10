#!/usr/bin/env node
/**
 * feedback.json を読み込み、ページごとの対応方針 (action) を機械的に一次判定してレポートする。
 * 実際のソース編集（HTML/CSSの書き換え、ページ削除など）はClaude Code本体がこのレポートを見て行う。
 *
 * Usage: node scripts/apply.js --session <session名> [--feedback <path>]
 */
const fs = require("fs");
const path = require("path");
const { workDir } = require("./lib/paths");

const DELETE_INTENT_RE = /削除|不要|消して|除外|カットして/;

function usage() {
  console.error("Usage: node scripts/apply.js --session <session名> [--feedback <feedback.jsonのパス>]");
  process.exit(1);
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--session") args.session = argv[++i];
    else if (argv[i] === "--feedback") args.feedback = argv[++i];
  }
  return args;
}

function decideAction(pageFeedback) {
  const comment = pageFeedback.pageComment || "";
  switch (pageFeedback.judgement) {
    case "OK":
      return "no-change";
    case "要修正":
      return "apply-annotations";
    case "NG":
      return DELETE_INTENT_RE.test(comment) ? "delete-page" : "rebuild-page";
    default:
      return "unspecified";
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.session) usage();

  const dir = workDir(args.session);
  const statePath = path.join(dir, "state.json");
  if (!fs.existsSync(statePath)) {
    throw new Error(`state.json が見つかりません: ${statePath}。先に init を実行してください。`);
  }
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));

  const feedbackPath = args.feedback ? path.resolve(args.feedback) : path.join(dir, "feedback.json");
  if (!fs.existsSync(feedbackPath)) {
    throw new Error(`feedback.json が見つかりません: ${feedbackPath}`);
  }
  const feedback = JSON.parse(fs.readFileSync(feedbackPath, "utf8"));

  const pages = (feedback.pages || []).map((p) => ({
    page: p.page,
    judgement: p.judgement || null,
    action: decideAction(p),
    annotationCount: (p.annotations || []).length,
    annotations: p.annotations || [],
    pageComment: p.pageComment || null
  }));

  const report = {
    session: args.session,
    sourceType: state.sourceType,
    sourcePath: state.sourcePath,
    generatedAt: new Date().toISOString(),
    pages
  };

  const reportPath = path.join(dir, "apply-report.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2), "utf8");

  console.log(`一次判定レポートを書き出しました: ${reportPath}`);
  console.log(
    `内訳: no-change=${pages.filter((p) => p.action === "no-change").length}` +
      ` / apply-annotations=${pages.filter((p) => p.action === "apply-annotations").length}` +
      ` / rebuild-page=${pages.filter((p) => p.action === "rebuild-page").length}` +
      ` / delete-page=${pages.filter((p) => p.action === "delete-page").length}` +
      ` / unspecified=${pages.filter((p) => p.action === "unspecified").length}`
  );
  if (state.sourceType === "pdf") {
    console.log("入力元はPDFのため自動修正はできません。apply-report.json の内容をテキストでユーザーに提示してください。");
  }
}

main();
