#!/usr/bin/env python3
"""
X (Twitter) の記事・ポストを、見た目・画像・コード/プロンプト部を忠実に保った
Markdown として保存する。

使い方:
    python3 x_article_to_md.py <X_URL> [<X_URL> ...] [options]

options:
    --outdir DIR      保存先ルート (既定: $X_ARTICLE_DIR または ~/x-article)
    --no-images       画像をダウンロードせずリモートURLを参照する
    --from-json FILE  ネットワークを使わず既存の raw.json から再生成する
    --overwrite       既存の保存先ディレクトリを上書きする（登録済みURLでも再保存する）
    --quiet           進捗ログを出さない

出力:
    <outdir>/articles.csv                       保存済みURL台帳（ヘッダ: URL,記事フォルダ名）
    <outdir>/<YYYY-MM-DD>_<screen_name>_<title>/
        <title>.md    本文 Markdown（ファイル名もタイトル）
        raw.json      取得した生JSON（再生成用）
        images/       cover.<ext>, img-01.<ext> ...

articles.csv に登録済みのURLは取得せずスキップする（--overwrite で無視できる）。
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
JST = timezone(timedelta(hours=9))

# Draft.js のインラインスタイル -> Markdown
STYLE_MARK = {
    "Bold": ("**", "**"),
    "BOLD": ("**", "**"),
    "Italic": ("*", "*"),
    "ITALIC": ("*", "*"),
    "Underline": ("<u>", "</u>"),
    "UNDERLINE": ("<u>", "</u>"),
    "Strikethrough": ("~~", "~~"),
    "STRIKETHROUGH": ("~~", "~~"),
}

BLOCK_PREFIX = {
    "header-one": "## ",
    "header-two": "### ",
    "header-three": "#### ",
    "header-four": "##### ",
    "blockquote": "> ",
}


def log(msg, quiet=False):
    if not quiet:
        print(msg, file=sys.stderr)


# ---------------------------------------------------------------- fetch

def extract_id(url):
    m = re.search(r"(?:twitter\.com|x\.com)/[^/]+/status(?:es)?/(\d+)", url)
    if m:
        return m.group(1)
    m = re.search(r"/i/(?:article|status)/(\d+)", url)
    if m:
        return m.group(1)
    m = re.fullmatch(r"\s*(\d{10,25})\s*", url)
    if m:
        return m.group(1)
    raise ValueError("ポストIDを抽出できません: %s" % url)


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_tweet(url, quiet=False):
    """fxtwitter の公開APIから、記事本文まで含んだJSONを取得する。"""
    tid = extract_id(url)
    m = re.search(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)/status", url)
    screen = m.group(1) if m and m.group(1) != "i" else "i"
    candidates = [
        "https://api.fxtwitter.com/%s/status/%s" % (screen, tid),
        "https://api.fxtwitter.com/i/status/%s" % tid,
        "https://api.vxtwitter.com/i/status/%s" % tid,  # 形が違えばフォールバックとして弾く
    ]
    last = None
    for api in candidates:
        try:
            log("fetch: %s" % api, quiet)
            data = json.loads(http_get(api).decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            continue
        if isinstance(data, dict) and isinstance(data.get("tweet"), dict):
            return data
        last = ValueError("想定外のレスポンス形式: %s" % api)
    raise RuntimeError("取得に失敗しました (%s): %s" % (tid, last))


# ------------------------------------------------- UTF-16 offset helpers

def to_units(s):
    """Draft.js のオフセットは UTF-16 コードユニット単位なので、その単位に分解する。"""
    out = []
    for ch in s:
        b = ch.encode("utf-16-le")
        for i in range(0, len(b), 2):
            out.append(b[i:i + 2])
    return out


def units_to_str(units):
    return b"".join(units).decode("utf-16-le", "replace")


def render_inline(text, style_ranges, url_ranges):
    """インラインの太字・リンクを、UTF-16オフセットに忠実に適用する。"""
    units = to_units(text)
    n = len(units)
    if n == 0:
        return ""

    spans = []
    for r in style_ranges or []:
        style = r.get("style")
        if style not in STYLE_MARK:
            continue
        s = max(0, int(r.get("offset", 0)))
        e = min(n, s + int(r.get("length", 0)))
        if e > s:
            spans.append((s, e, ("style", style)))
    for u in url_ranges or []:
        s = max(0, int(u.get("fromIndex", 0)))
        e = min(n, int(u.get("toIndex", 0)))
        href = u.get("expanded_url") or u.get("url") or u.get("text")
        if e > s and href:
            spans.append((s, e, ("link", href)))

    if not spans:
        return units_to_str(units)

    active_at = [set() for _ in range(n + 1)]
    for s, e, key in spans:
        for i in range(s, e):
            active_at[i].add(key)

    def open_order(key):
        # リンクを外側、スタイルを内側にして入れ子を安定させる
        return (0 if key[0] == "link" else 1, str(key[1]))

    def open_mark(key):
        return "[" if key[0] == "link" else STYLE_MARK[key[1]][0]

    def close_mark(key):
        return "]" if key[0] == "link" else STYLE_MARK[key[1]][1]

    out = []
    buf = []
    stack = []

    def flush():
        if buf:
            out.append(units_to_str(buf))
            buf.clear()

    def close_top():
        key = stack.pop()
        flush()
        if key[0] == "link":
            out.append("](%s)" % key[1])
        else:
            out.append(close_mark(key))

    for i in range(n + 1):
        cur = active_at[i]
        while stack and stack[-1] not in cur:
            close_top()
        if any(k not in cur for k in stack):
            while stack:
                close_top()
        for key in sorted(cur - set(stack), key=open_order):
            flush()
            out.append(open_mark(key))
            stack.append(key)
        if i < n:
            buf.append(units[i])
    flush()
    return "".join(out)


# ------------------------------------------------------------- rendering

def fence_for(body):
    """本文に ``` が含まれていても壊れない長さのフェンスを返す。"""
    longest = 0
    for m in re.finditer(r"`+", body):
        longest = max(longest, len(m.group(0)))
    return "`" * max(3, longest + 1)


def as_code_block(body, lang=""):
    body = body.strip("\n")
    f = fence_for(body)
    return "%s%s\n%s\n%s" % (f, lang, body, f)


def normalize_markdown_entity(raw):
    """
    MARKDOWN エンティティ（記事内のコード/プロンプト枠）を、
    必ずコードブロックとして本文と混ざらない形にする。
    """
    text = (raw or "").strip("\n")
    if not text.strip():
        return ""
    stripped = text.strip()
    m = re.match(r"^(`{3,})([^\n`]*)\n(.*)\n\1\s*$", stripped, re.S)
    if m:
        # すでにフェンス済み: 中身をそのまま保持したうえでフェンスを張り直す
        return as_code_block(m.group(3), (m.group(2) or "").strip())
    if stripped.startswith("```"):
        # 閉じフェンスが欠けているケース
        inner = re.sub(r"^`{3,}[^\n]*\n?", "", stripped)
        inner = re.sub(r"\n?`{3,}\s*$", "", inner)
        return as_code_block(inner)
    return as_code_block(text)


def media_ext(url, typename=""):
    m = re.search(r"\.(jpg|jpeg|png|gif|webp|mp4|mov|m4v)(?:\?|$)", url or "", re.I)
    if m:
        return "." + m.group(1).lower()
    if "video" in (typename or "").lower():
        return ".mp4"
    return ".jpg"


def media_source(info):
    """media_info から実体URLを取り出す（画像・GIF・動画）。"""
    if not isinstance(info, dict):
        return None, None
    typename = info.get("__typename") or ""
    for key in ("original_img_url", "url", "media_url_https", "media_url"):
        if info.get(key):
            return info[key], typename
    variants = info.get("variants") or info.get("video_variants") or []
    best, bitrate = None, -1
    for v in variants:
        if not isinstance(v, dict):
            continue
        if v.get("content_type") and "mp4" not in v["content_type"]:
            continue
        br = int(v.get("bitrate") or 0)
        if v.get("url") and br >= bitrate:
            best, bitrate = v["url"], br
    if best:
        return best, typename
    if info.get("preview_image_url"):
        return info["preview_image_url"], typename
    return None, typename


class MediaSaver:
    """画像を images/ に落とし、Markdown から相対パスで参照できるようにする。"""

    def __init__(self, images_dir, download=True, quiet=False):
        self.images_dir = images_dir
        self.download = download
        self.quiet = quiet
        self.seq = 0
        self.by_url = {}
        self.manifest = []

    def save(self, url, typename="", name=None):
        if not url:
            return None
        if url in self.by_url:
            return self.by_url[url]
        if not self.download:
            self.by_url[url] = url
            self.manifest.append({"remote": url, "local": "(remote)"})
            return url
        if name is None:
            self.seq += 1
            name = "img-%02d" % self.seq
        fname = name + media_ext(url, typename)
        path = os.path.join(self.images_dir, fname)
        os.makedirs(self.images_dir, exist_ok=True)
        got = None
        for candidate in ([url + ("&" if "?" in url else "?") + "name=orig", url]
                          if "pbs.twimg.com" in url else [url]):
            try:
                got = http_get(candidate, timeout=60)
                break
            except Exception as e:  # noqa: BLE001
                log("  ! 画像取得失敗 %s (%s)" % (candidate, e), self.quiet)
        if got is None:
            self.by_url[url] = url
            self.manifest.append({"remote": url, "local": None})
            return url
        with open(path, "wb") as f:
            f.write(got)
        rel = "images/" + fname
        log("  + %s (%d KB)" % (rel, len(got) // 1024), self.quiet)
        self.by_url[url] = rel
        self.manifest.append({"remote": url, "local": rel})
        return rel


def img_md(src, alt="", caption=""):
    alt = re.sub(r"[\[\]\n]", " ", alt or "").strip()
    out = ["![%s](%s)" % (alt, src)]
    if caption:
        cap = caption.strip().replace("\n", " ")
        out.append("*%s*" % cap)
    return "\n\n".join(out)


def entity_map_dict(content):
    """entityMap が list でも dict でも引けるようにする。"""
    em = content.get("entityMap")
    out = {}
    if isinstance(em, list):
        for e in em:
            if isinstance(e, dict) and "key" in e:
                out[str(e["key"])] = e.get("value") or {}
    elif isinstance(em, dict):
        for k, v in em.items():
            out[str(k)] = v or {}
    return out


def parse_ranges(spec):
    """'12-18,24' -> [(12,18),(24,24)]"""
    out = []
    for chunk in (spec or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = re.fullmatch(r"(\d+)\s*-\s*(\d+)", chunk)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out.append((min(a, b), max(a, b)))
        else:
            i = int(chunk)
            out.append((i, i))
    return sorted(out)


def in_range(i, ranges):
    for a, b in ranges:
        if a <= i <= b:
            return (a, b)
    return None


def list_blocks(content):
    """--fence-blocks で指定するためのブロック一覧を出力する。"""
    em = entity_map_dict(content)
    rows = []
    for i, b in enumerate(content.get("blocks") or []):
        btype = b.get("type") or "unstyled"
        text = (b.get("text") or "").replace("\n", "⏎")
        if btype == "atomic":
            kinds = []
            for er in b.get("entityRanges") or []:
                ent = em.get(str(er.get("key"))) or {}
                kinds.append((ent.get("type") or "?").upper())
            text = "[" + ",".join(kinds) + "]"
        rows.append("%4d  %-20s %s" % (i, btype, text[:90]))
    return "\n".join(rows)


def render_blocks(content, media_index, saver, fence_ranges=None):
    em = entity_map_dict(content)
    parts = []
    prev_list = None
    ol_no = 0
    fence_ranges = fence_ranges or []
    fence_buf = []

    for bidx, block in enumerate(content.get("blocks") or []):
        rng = in_range(bidx, fence_ranges)
        if rng:
            # 明示指定されたブロック群は、本文と混ざらないよう
            # 生テキストのままコードブロックにまとめる
            prev_list = None
            if block.get("type") != "atomic":
                fence_buf.append(block.get("text") or "")
            if bidx == rng[1]:
                body = "\n".join(fence_buf).strip("\n")
                # X のコピーボタン由来の先頭 "Copy" は UI 装飾なので落とす
                body = re.sub(r"^Copy(?=\S)", "", body)
                fence_buf = []
                if body.strip():
                    parts.append(as_code_block(body))
            continue

        btype = block.get("type") or "unstyled"
        text = block.get("text") or ""
        depth = int(block.get("depth") or 0)
        data = block.get("data") or {}
        entity_ranges = block.get("entityRanges") or []

        if btype == "atomic":
            prev_list = None
            for er in entity_ranges:
                ent = em.get(str(er.get("key"))) or {}
                etype = (ent.get("type") or "").upper()
                edata = ent.get("data") or {}
                if etype == "MARKDOWN":
                    md = normalize_markdown_entity(edata.get("markdown"))
                    if md:
                        parts.append(md)
                elif etype == "DIVIDER":
                    parts.append("---")
                elif etype == "MEDIA":
                    caption = edata.get("caption") or ""
                    chunks = []
                    for item in edata.get("mediaItems") or []:
                        info = media_index.get(str(item.get("mediaId")))
                        url, typename = media_source(info)
                        src = saver.save(url, typename)
                        if src:
                            chunks.append(img_md(src, caption if len(
                                edata.get("mediaItems") or []) == 1 else "", ""))
                    if chunks:
                        parts.append("\n\n".join(chunks))
                    if caption:
                        parts.append("*%s*" % caption.strip().replace("\n", " "))
                elif etype == "TWEET":
                    tw = edata.get("tweetId") or edata.get("tweet_id")
                    if tw:
                        parts.append("> 引用ポスト: https://x.com/i/status/%s" % tw)
                elif etype == "LINK":
                    href = edata.get("url") or edata.get("expanded_url")
                    if href:
                        parts.append("<%s>" % href)
                else:
                    parts.append("<!-- 未対応エンティティ: %s %s -->" % (
                        etype, json.dumps(edata, ensure_ascii=False)[:200]))
            continue

        if btype == "code-block":
            prev_list = None
            if text.strip():
                parts.append(as_code_block(text))
            continue

        inline = render_inline(text, block.get("inlineStyleRanges"), data.get("urls"))
        if not inline.strip():
            prev_list = None
            continue

        if btype in ("unordered-list-item", "ordered-list-item"):
            if btype == "ordered-list-item":
                ol_no = ol_no + 1 if prev_list == btype else 1
                bullet = "%d. " % ol_no
            else:
                bullet = "- "
            indent = "  " * depth
            body = inline.replace("\n", "\n" + indent + "  ")
            line = indent + bullet + body
            if prev_list == btype and parts:
                parts[-1] = parts[-1] + "\n" + line
            else:
                parts.append(line)
            prev_list = btype
            continue

        prev_list = None
        if btype in BLOCK_PREFIX:
            prefix = BLOCK_PREFIX[btype]
            if btype == "blockquote":
                parts.append("\n".join(prefix + l for l in inline.split("\n")))
            else:
                parts.append(prefix + inline.replace("\n", " "))
            continue

        # 通常段落: 記事内の改行は Markdown の強制改行として保持する
        parts.append(inline.replace("\n", "  \n"))

    return "\n\n".join(p for p in parts if p is not None and p != "")


def build_media_index(article):
    idx = {}
    for m in article.get("media_entities") or []:
        if isinstance(m, dict) and m.get("media_id"):
            idx[str(m["media_id"])] = m.get("media_info") or {}
    cover = article.get("cover_media") or {}
    if cover.get("media_id"):
        idx.setdefault(str(cover["media_id"]), cover.get("media_info") or {})
    return idx


# ------------------------------------------------------- tweet (記事以外)

def render_plain_tweet(tweet, saver):
    parts = []
    raw = tweet.get("raw_text") or {}
    text = raw.get("text") or tweet.get("text") or ""
    urls = []
    for f in raw.get("facets") or []:
        if f.get("type") == "url" and f.get("replacement"):
            ind = f.get("indices") or [0, 0]
            urls.append({"fromIndex": ind[0], "toIndex": ind[1],
                         "url": f["replacement"], "text": f.get("display")})
    body = render_inline(text, [], urls)
    if body.strip():
        parts.append(body.replace("\n", "  \n"))

    media = tweet.get("media") or {}
    for item in media.get("all") or []:
        url = item.get("url") or item.get("thumbnail_url")
        src = saver.save(url, item.get("type") or "")
        if src:
            parts.append(img_md(src, item.get("altText") or ""))

    poll = tweet.get("poll")
    if poll:
        lines = ["**投票**"]
        for c in poll.get("choices") or []:
            lines.append("- %s — %s%%" % (c.get("label"), c.get("percentage")))
        parts.append("\n".join(lines))

    quote = tweet.get("quote")
    if quote:
        q = render_plain_tweet(quote, saver)
        head = "引用: %s (@%s) %s" % (
            (quote.get("author") or {}).get("name", ""),
            (quote.get("author") or {}).get("screen_name", ""),
            quote.get("url", ""))
        block = head + "\n\n" + q
        parts.append("\n".join("> " + l if l else ">" for l in block.split("\n")))

    return "\n\n".join(p for p in parts if p)


# ---------------------------------------------------------------- output

def slugify(title, maxlen=60):
    s = unicodedata.normalize("NFC", title or "").strip()
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r'[/\\:*?"<>|]', "", s)
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._ ")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("._ ")
    return s or "untitled"


def parse_created(tweet):
    ts = tweet.get("created_timestamp")
    if ts:
        return datetime.fromtimestamp(int(ts), JST)
    for fmt in ("%a %b %d %H:%M:%S %z %Y",):
        try:
            return datetime.strptime(tweet.get("created_at", ""), fmt).astimezone(JST)
        except Exception:  # noqa: BLE001
            pass
    return datetime.now(JST)


def yaml_str(v):
    return '"%s"' % str(v).replace("\\", "\\\\").replace('"', '\\"')


def save_one(data, outroot, download=True, overwrite=False, quiet=False,
             fence_ranges=None):
    tweet = data["tweet"]
    author = tweet.get("author") or {}
    article = tweet.get("article") or None
    created = parse_created(tweet)

    title = (article or {}).get("title") or None
    if not title:
        first = ((tweet.get("raw_text") or {}).get("text")
                 or tweet.get("text") or "post").split("\n")[0]
        title = first[:60]

    title_slug = slugify(title)
    dirname = "%s_%s_%s" % (created.strftime("%Y-%m-%d"),
                            author.get("screen_name") or "unknown",
                            title_slug)
    dest = os.path.join(outroot, dirname)
    if os.path.exists(dest) and not overwrite:
        i = 2
        while os.path.exists("%s_%d" % (dest, i)):
            i += 1
        dest = "%s_%d" % (dest, i)
    os.makedirs(dest, exist_ok=True)
    images_dir = os.path.join(dest, "images")
    saver = MediaSaver(images_dir, download=download, quiet=quiet)

    log("save: %s" % dest, quiet)

    head = [
        "---",
        "title: %s" % yaml_str(title),
        "author: %s" % yaml_str(author.get("name") or ""),
        "author_handle: %s" % yaml_str("@" + (author.get("screen_name") or "")),
        "author_url: %s" % yaml_str(author.get("url") or ""),
        "source_url: %s" % yaml_str(tweet.get("url") or ""),
        "type: %s" % ("x-article" if article else "x-post"),
        "posted_at: %s" % yaml_str(created.strftime("%Y-%m-%d %H:%M:%S %z")),
    ]
    if article:
        if article.get("id"):
            head.append("article_url: %s" % yaml_str(
                "https://x.com/i/article/%s" % article["id"]))
        if article.get("modified_at"):
            head.append("modified_at: %s" % yaml_str(article["modified_at"]))
    head += [
        "likes: %s" % (tweet.get("likes") or 0),
        "reposts: %s" % (tweet.get("retweets") or 0),
        "bookmarks: %s" % (tweet.get("bookmarks") or 0),
        "views: %s" % (tweet.get("views") or 0),
        "saved_at: %s" % yaml_str(datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S %z")),
        "---",
    ]

    body = ["\n".join(head), "# %s" % title]

    byline = "%s ([@%s](%s)) ・ %s ・ [元記事](%s)" % (
        author.get("name") or "",
        author.get("screen_name") or "",
        author.get("url") or "",
        created.strftime("%Y-%m-%d %H:%M JST"),
        tweet.get("url") or "")
    body.append(byline)

    if article:
        media_index = build_media_index(article)
        cover = article.get("cover_media") or {}
        cover_url, cover_type = media_source(cover.get("media_info") or {})
        if cover_url:
            src = saver.save(cover_url, cover_type, name="cover")
            if src:
                body.append(img_md(src, "cover"))
        preview = article.get("preview_text")
        if preview and preview.strip():
            body.append("> %s" % preview.strip().replace("\n", "\n> "))
        body.append("---")
        content = article.get("content") or {}
        rendered = render_blocks(content, media_index, saver, fence_ranges)
        if not rendered.strip():
            rendered = "<!-- 本文ブロックを取得できませんでした。raw.json を確認してください -->"
        body.append(rendered)
    else:
        body.append("---")
        body.append(render_plain_tweet(tweet, saver))

    md_path = os.path.join(dest, title_slug + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(b for b in body if b and b.strip()) + "\n")
    with open(os.path.join(dest, "raw.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    stats = {"blocks": 0, "code_entities": 0, "media": len(saver.manifest)}
    if article:
        content = article.get("content") or {}
        stats["blocks"] = len(content.get("blocks") or [])
        stats["code_entities"] = sum(
            1 for v in entity_map_dict(content).values()
            if (v.get("type") or "").upper() == "MARKDOWN")
    return dest, md_path, saver.manifest, stats


CSV_NAME = "articles.csv"
CSV_HEADER = ["URL", "記事フォルダ名"]


def url_key(url):
    """同じポストを指すURLを同一視するためのキー。

    x.com / twitter.com / 末尾スラッシュ / クエリ文字列の違いを吸収する。
    ステータスIDが取れればそれを、取れなければ正規化したURLを返す。
    """
    u = (url or "").strip()
    m = re.search(r"/status(?:es)?/(\d+)", u)
    if m:
        return "status:%s" % m.group(1)
    m = re.search(r"/i/article/([\w-]+)", u)
    if m:
        return "article:%s" % m.group(1)
    u = re.sub(r"[?#].*$", "", u)
    u = re.sub(r"/+$", "", u)
    return u.lower()


def csv_path(outroot):
    return os.path.join(outroot, CSV_NAME)


def load_csv_index(outroot):
    """articles.csv を読み、{url_key: 記事フォルダ名} を返す。"""
    path = csv_path(outroot)
    index = {}
    if not os.path.exists(path):
        return index
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            if not row or not row[0].strip():
                continue
            url = row[0].strip()
            if url.lower() == "url":  # ヘッダ行は読み飛ばす
                continue
            index[url_key(url)] = row[1].strip() if len(row) > 1 else ""
    return index


def append_csv(outroot, url, dirname):
    """URL と記事フォルダ名を articles.csv に1行追記する。

    ファイルが無い・空のときはヘッダ行を先に書く。
    """
    path = csv_path(outroot)
    need_header = (not os.path.exists(path)) or os.path.getsize(path) == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        if need_header:
            w.writerow(CSV_HEADER)
        w.writerow([url, dirname])


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--outdir", default=os.environ.get(
        "X_ARTICLE_DIR", os.path.expanduser("~/x-article")))
    ap.add_argument("--no-images", action="store_true")
    ap.add_argument("--from-json", default=None)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--list-blocks", action="store_true",
                    help="記事のブロック一覧を表示して終了（--fence-blocks の指定用）")
    ap.add_argument("--fence-blocks", default=None,
                    help="例 12-18,24 : 指定ブロックを生テキストのままコードブロック化")
    args = ap.parse_args(argv)

    outroot = os.path.expanduser(args.outdir)
    os.makedirs(outroot, exist_ok=True)
    index = load_csv_index(outroot)

    jobs = []  # (入力URL or None, data)
    if args.from_json:
        with open(args.from_json, encoding="utf-8") as f:
            raw = f.read()
        raw = re.sub(r"^\s*```(?:json)?\s*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
        jobs.append((None, json.loads(raw)))
    else:
        if not args.urls:
            ap.error("URL を1つ以上指定してください")
        for u in args.urls:
            if not args.list_blocks and not args.overwrite \
                    and url_key(u) in index:
                print("SKIP %s (登録済み: %s)" % (u, index[url_key(u)] or "-"))
                continue
            try:
                jobs.append((u, fetch_tweet(u, args.quiet)))
            except Exception as e:  # noqa: BLE001
                print("ERROR %s: %s" % (u, e), file=sys.stderr)

    if not jobs:
        return 0 if not args.from_json else 1

    if args.list_blocks:
        for _, data in jobs:
            art = (data.get("tweet") or {}).get("article") or {}
            print("# %s" % (art.get("title") or "(記事ではありません)"))
            print(list_blocks(art.get("content") or {}))
        return 0

    fence_ranges = parse_ranges(args.fence_blocks) if args.fence_blocks else []

    rc = 0
    for src_url, data in jobs:
        try:
            dest, md_path, manifest, stats = save_one(data, outroot,
                                             download=not args.no_images,
                                             overwrite=args.overwrite,
                                             quiet=args.quiet,
                                             fence_ranges=fence_ranges)
            missing = [m["remote"] for m in manifest if m["local"] is None]
            print("SAVED %s" % md_path)
            print("  blocks: %d / code_entities: %d" % (
                stats["blocks"], stats["code_entities"]))
            print("  images: %d 件 / 未取得 %d 件" % (len(manifest), len(missing)))
            for m in missing:
                print("  MISSING %s" % m)

            rec_url = src_url or (data.get("tweet") or {}).get("url") or ""
            dirname = os.path.basename(dest)
            key = url_key(rec_url)
            if not rec_url:
                print("  CSV: URLが不明のため articles.csv には追記しない")
            elif key in index:
                print("  CSV: 登録済み (%s)" % (index[key] or "-"))
            else:
                append_csv(outroot, rec_url, dirname)
                index[key] = dirname
                print("  CSV: %s に追記 (%s)" % (CSV_NAME, dirname))
        except Exception as e:  # noqa: BLE001
            print("ERROR save: %s" % e, file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
