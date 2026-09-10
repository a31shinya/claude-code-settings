const path = require("path");

// スキル自身のインストール場所（scripts/lib から2階層上）。
// テンプレートやnode_modulesなど、スキルに同梱される資産の参照に使う。
const SKILL_ROOT = path.join(__dirname, "..", "..");

// セッションの作業ファイルは「呼び出し元のカレントディレクトリ」基準で置く。
// これにより、このスキルを ~/.claude/skills/feedback-to-slide/ に置いて
// どのプロジェクトから呼び出しても、作業ファイルは呼び出し元プロジェクト側の
// .feedback-to-slide/work/ に作られ、プロジェクトごとに分離される。
function sessionsRoot() {
  return path.join(process.cwd(), ".feedback-to-slide", "work");
}

function workDir(session) {
  return path.join(sessionsRoot(), session);
}

module.exports = { SKILL_ROOT, sessionsRoot, workDir };
