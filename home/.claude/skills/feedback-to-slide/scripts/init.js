#!/usr/bin/env node
/**
 * PDFファイル、またはClaude Code製HTML+CSSスライド(1ページ=1.htmlのディレクトリ)から
 * ページ画像とレビューHTMLを生成する。
 *
 * Usage: node scripts/init.js --input <file.pdf|htmlDir> --session <session名>
 */
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { workDir } = require("./lib/paths");
const { renderReviewHtml } = require("./lib/renderReviewHtml");

function usage() {
  console.error("Usage: node scripts/init.js --input <file.pdf|htmlDir> --session <session名>");
  process.exit(1);
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--input") args.input = argv[++i];
    else if (argv[i] === "--session") args.session = argv[++i];
  }
  return args;
}

function extractPageNum(filename) {
  const m = filename.match(/(\d+)\.png$/);
  return m ? parseInt(m[1], 10) : 0;
}

function pdfToImages(pdfPath, outDir) {
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  const prefix = path.join(outDir, "page");
  try {
    execFileSync("pdftoppm", ["-png", "-r", "150", pdfPath, prefix], { stdio: "inherit" });
  } catch (err) {
    console.error("pdftoppm の実行に失敗しました。poppler が未導入の場合は `brew install poppler` を実行してください。");
    throw err;
  }
  const files = fs
    .readdirSync(outDir)
    .filter((f) => /^page-?\d+\.png$/.test(f))
    .sort((a, b) => extractPageNum(a) - extractPageNum(b));
  if (files.length === 0) {
    throw new Error(`${outDir} にページ画像が生成されませんでした`);
  }
  // ページ番号でゼロ埋めリネーム (page-01.png 形式に統一)
  return files.map((f, i) => {
    const target = path.join(outDir, `page-${String(i + 1).padStart(2, "0")}.png`);
    const src = path.join(outDir, f);
    if (src !== target) fs.renameSync(src, target);
    return target;
  });
}

async function htmlDirToImages(htmlDir, outDir) {
  let puppeteer;
  try {
    puppeteer = require("puppeteer");
  } catch (err) {
    throw new Error("puppeteer が未インストールです。プロジェクトルートで `npm install` を実行してください。");
  }
  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });
  const files = fs
    .readdirSync(htmlDir)
    .filter((f) => f.endsWith(".html"))
    .sort();
  if (files.length === 0) {
    throw new Error(`${htmlDir} 内に .html ファイルが見つかりません（1ページ=1ファイル、連番のファイル名を想定）`);
  }

  const browser = await puppeteer.launch();
  try {
    const page = await browser.newPage();
    // ビューポート幅はスライドHTMLのコンテンツ幅に合わせる。高さは実コンテンツに応じて
    // fullPage スクリーンショットが自動調整するため仮の値でよい。
    await page.setViewport({ width: 1241, height: 1754, deviceScaleFactor: 2 });
    const outputs = [];
    for (let i = 0; i < files.length; i++) {
      const filePath = path.join(htmlDir, files[i]);
      await page.goto("file://" + path.resolve(filePath), { waitUntil: "networkidle0" });
      const outPath = path.join(outDir, `page-${String(i + 1).padStart(2, "0")}.png`);
      await page.screenshot({ path: outPath, fullPage: true });
      outputs.push(outPath);
    }
    return outputs;
  } finally {
    await browser.close();
  }
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.input || !args.session) usage();

  const inputPath = path.resolve(args.input);
  if (!fs.existsSync(inputPath)) {
    throw new Error(`入力が見つかりません: ${inputPath}`);
  }

  const dir = workDir(args.session);
  const pagesDir = path.join(dir, "pages");
  fs.mkdirSync(dir, { recursive: true });

  const stat = fs.statSync(inputPath);
  let sourceType;
  let imagePaths;

  if (stat.isDirectory()) {
    sourceType = "html";
    imagePaths = await htmlDirToImages(inputPath, pagesDir);
  } else if (inputPath.toLowerCase().endsWith(".pdf")) {
    sourceType = "pdf";
    imagePaths = pdfToImages(inputPath, pagesDir);
  } else {
    throw new Error("入力はPDFファイル、またはHTML+CSSスライドを含むディレクトリを指定してください（既存ファイルはPDF限定）");
  }

  const state = {
    session: args.session,
    sourceType,
    sourcePath: inputPath,
    pages: imagePaths.map((p, i) => ({
      page: i + 1,
      image: path.relative(dir, p)
    })),
    createdAt: new Date().toISOString()
  };
  fs.writeFileSync(path.join(dir, "state.json"), JSON.stringify(state, null, 2), "utf8");

  const reviewHtmlPath = path.join(dir, "review.html");
  renderReviewHtml({ state, outPath: reviewHtmlPath });

  console.log(`レビューHTMLを生成しました: ${reviewHtmlPath}`);
  console.log(`入力種別: ${sourceType} / ページ数: ${imagePaths.length}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
