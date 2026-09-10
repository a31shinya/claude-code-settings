const fs = require("fs");
const path = require("path");

const TEMPLATE_PATH = path.join(__dirname, "..", "..", "templates", "review-template.html");

/**
 * state.pages の画像を review-template.html に差し込み、work/<session>/review.html を書き出す。
 * @param {object} params
 * @param {{pages: {page:number, image:string}[]}} params.state
 * @param {string} params.outPath 出力先 (review.html への絶対パス)
 */
function renderReviewHtml({ state, outPath }) {
  const template = fs.readFileSync(TEMPLATE_PATH, "utf8");
  const pagesData = state.pages.map((p) => ({
    title: `P${String(p.page).padStart(2, "0")}`,
    image: p.image
  }));
  const injected = template.replace(
    /\/\*__PAGES_DATA_JSON__\*\/\[\]\/\*__END_PAGES_DATA_JSON__\*\//,
    JSON.stringify(pagesData)
  );
  if (injected === template) {
    throw new Error("review-template.html 内のプレースホルダーが見つかりませんでした（テンプレートが変更された可能性があります）");
  }
  fs.writeFileSync(outPath, injected, "utf8");
}

module.exports = { renderReviewHtml };
