#!/usr/bin/env node
/**
 * work/<session>/pages の画像を最終成果物 (pdf / pptx / html) として書き出す。
 *
 * Usage: node scripts/export.js --session <session名> --format pdf|pptx|html
 */
const fs = require("fs");
const path = require("path");
const { workDir } = require("./lib/paths");

function usage() {
  console.error("Usage: node scripts/export.js --session <session名> --format pdf|pptx|html");
  process.exit(1);
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--session") args.session = argv[++i];
    else if (argv[i] === "--format") args.format = argv[++i];
  }
  return args;
}

async function exportPdf(state, dir, outDir) {
  const { PDFDocument } = require("pdf-lib");
  const pdfDoc = await PDFDocument.create();
  for (const p of state.pages) {
    const imgBytes = fs.readFileSync(path.join(dir, p.image));
    const img = await pdfDoc.embedPng(imgBytes);
    const pdfPage = pdfDoc.addPage([img.width, img.height]);
    pdfPage.drawImage(img, { x: 0, y: 0, width: img.width, height: img.height });
  }
  const bytes = await pdfDoc.save();
  const outPath = path.join(outDir, "slides.pdf");
  fs.writeFileSync(outPath, bytes);
  return outPath;
}

async function exportPptx(state, dir, outDir) {
  const PptxGenJS = require("pptxgenjs");
  const pptx = new PptxGenJS();
  for (const p of state.pages) {
    const slide = pptx.addSlide();
    slide.addImage({ path: path.join(dir, p.image), x: 0, y: 0, w: "100%", h: "100%" });
  }
  const outPath = path.join(outDir, "slides.pptx");
  await pptx.writeFile({ fileName: outPath });
  return outPath;
}

function exportHtml(state, dir, outDir) {
  const pagesOutDir = path.join(outDir, "pages");
  fs.mkdirSync(pagesOutDir, { recursive: true });
  for (const p of state.pages) {
    fs.copyFileSync(path.join(dir, p.image), path.join(pagesOutDir, path.basename(p.image)));
  }
  fs.copyFileSync(path.join(dir, "review.html"), path.join(outDir, "review.html"));
  return path.join(outDir, "review.html");
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.session || !args.format) usage();
  if (!["pdf", "pptx", "html"].includes(args.format)) {
    throw new Error(`未対応のformat: ${args.format}（pdf/pptx/htmlのいずれかを指定してください）`);
  }

  const dir = workDir(args.session);
  const statePath = path.join(dir, "state.json");
  if (!fs.existsSync(statePath)) {
    throw new Error(`state.json が見つかりません: ${statePath}。先に init を実行してください。`);
  }
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));

  const outDir = path.join(dir, "output");
  fs.mkdirSync(outDir, { recursive: true });

  let outPath;
  if (args.format === "pdf") outPath = await exportPdf(state, dir, outDir);
  else if (args.format === "pptx") outPath = await exportPptx(state, dir, outDir);
  else outPath = exportHtml(state, dir, outDir);

  console.log(`書き出しました: ${outPath}`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
