"""Render maintained Markdown into static, script-free documentation pages."""

from __future__ import annotations

import hashlib
import html
import json
import posixpath
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

SOURCE_URL = "https://github.com/joongi007/joongi-skills/blob/main/"
GROUPS = {
    "installation": "설치와 업데이트",
    "operations": "사용과 문제 해결",
    "architecture": "구조와 지원 범위",
    "development": "개발과 검증",
    "adr": "설계 결정",
}


def destination(source: Path) -> str:
    return "read/" + source.with_suffix(".html").as_posix()


def relative(target: str, current: str) -> str:
    return quote(posixpath.relpath(target, posixpath.dirname(current)), safe="/.-_")


def slug(text: str) -> str:
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", text.lower()).strip())


def content(source: str) -> str:
    """Hide skill metadata and build contracts, preserving code examples verbatim."""
    source = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n", "", source, count=1, flags=re.S)
    lines = []
    fence = None
    comment = False
    for line in source.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker and not comment:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            lines.append(line)
        elif fence:
            lines.append(line)
        elif comment or line.lstrip().startswith("<!--"):
            comment = "-->" not in line
        else:
            lines.append(line)
    return "\n".join(lines)


def build_docs(root: Path, output: Path, public_file) -> int:
    sources = [root / "README.md"]
    sources += [p for folder in ("docs", "skills", "refs") for p in (root / folder).rglob("*.md")]
    sources = sorted(
        p.relative_to(root)
        for p in sources
        if p.is_file()
        and not p.is_symlink()
        and p.resolve().is_relative_to(root.resolve())
        and public_file(p.relative_to(root))
        and public_file(p.resolve().relative_to(root.resolve()))
    )
    if not sources:
        return 0
    try:
        from markdown_it import MarkdownIt
    except ImportError as error:
        raise RuntimeError(
            "Install build dependencies: pip install -r requirements-docs.txt"
        ) from error

    parser = MarkdownIt("js-default", {"html": False})
    diagrams = {}
    original_fence = parser.renderer.rules["fence"]

    def render_fence(tokens, index, options, environment):
        token = tokens[index]
        if token.info.strip() != "mermaid":
            return original_fence(tokens, index, options, environment)
        if len(token.content) > 16000:
            raise ValueError("Mermaid source exceeds 16,000 characters")
        identity = hashlib.sha256(token.content.encode()).hexdigest()
        diagrams[identity] = token.content
        image = relative("diagrams/" + identity + ".svg", environment["current"])
        return (
            '<figure class="mermaid-diagram">'
            f'<p data-mermaid-slot="{identity}" data-mermaid-src="{image}">'
            "도표 이미지 빌드 전입니다. 원문을 펼쳐 볼 수 있습니다.</p>"
            "<details><summary>Mermaid 원문 보기</summary><pre><code>"
            + html.escape(token.content)
            + "</code></pre></details></figure>"
        )

    parser.renderer.rules["fence"] = render_fence
    pages = {}
    for source in sources:
        tokens = parser.parse(content((root / source).read_text(encoding="utf-8")))
        headings = []
        counts = {}
        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                inline = tokens[i + 1]
                label = "".join(
                    t.content for t in inline.children or [] if t.type in {"text", "code_inline"}
                )
                base = slug(label)
                count = counts.get(base, 0)
                counts[base] = count + 1
                identifier = "section-" + base + (f"-{count}" if count else "")
                token.attrSet("id", identifier)
                headings.append((token.tag, label, identifier))
        pages[source] = {
            "tokens": tokens,
            "headings": headings,
            "title": headings[0][1] if headings else source.stem,
        }

    def link(target: str, source: Path) -> str:
        url = urlsplit(target)
        if url.scheme or url.netloc:
            return target
        if url.path.startswith("/"):
            return target
        normalized = (
            posixpath.normpath((source.parent / unquote(url.path)).as_posix())
            if url.path
            else source.as_posix()
        )
        path = Path(normalized)
        if path not in pages:
            for name in ("00-index.md", "README.md", "INDEX.md"):
                candidate = path / name
                if candidate in pages:
                    path = candidate
                    break
        if path in pages:
            fragment = "section-" + unquote(url.fragment) if url.fragment else ""
            return urlunsplit(
                ("", "", relative(destination(path), destination(source)), url.query, fragment)
            )
        # Keep source-only files (JSON, examples, licenses) reachable without copying them.
        if normalized.startswith("../") or normalized == "..":
            raise ValueError(f"Documentation link escapes source: {source}: {target}")
        return (
            SOURCE_URL
            + quote(normalized, safe="/.-_")
            + ("#" + url.fragment if url.fragment else "")
        )

    nav_sources = [s for s in sources if s.parts[0] == "docs"]
    nav_sources = ([Path("README.md")] if Path("README.md") in pages else []) + nav_sources
    for source, page in pages.items():
        current = destination(source)
        for token in page["tokens"]:
            for child in token.children or []:
                if child.type == "link_open":
                    child.attrSet("href", link(child.attrGet("href") or "", source))
                elif child.type == "image":
                    target = child.attrGet("src") or ""
                    if not urlsplit(target).scheme and not target.startswith("/"):
                        normalized = posixpath.normpath(
                            (source.parent / unquote(target)).as_posix()
                        )
                        child.attrSet(
                            "src",
                            SOURCE_URL.replace("github.com/", "raw.githubusercontent.com/").replace(
                                "/blob/", "/"
                            )
                            + quote(normalized, safe="/.-_"),
                        )
        navigation = []
        for key, label in [("overview", "시작하기"), *GROUPS.items(), ("skills", "공용 스킬")]:
            candidates = [
                s for s in nav_sources if (s.parts[1] if len(s.parts) > 2 else "overview") == key
            ]
            if key == "skills":
                candidates = [s for s in sources if s.parts[0] == "skills" and s.name == "SKILL.md"]
            if not candidates:
                continue
            active = source in candidates
            items = "".join(
                f'<li><a href="{html.escape(relative(destination(s), current), quote=True)}"'
                + (' aria-current="page"' if s == source else "")
                + f">{html.escape(pages[s]['title'])}</a></li>"
                for s in candidates
            )
            navigation.append(
                f"<details{' open' if active else ''}><summary>{label}</summary>"
                f"<ul>{items}</ul></details>"
            )
        toc = "".join(
            f'<li class="toc-{tag}"><a href="#{html.escape(identifier)}">'
            f"{html.escape(label)}</a></li>"
            for tag, label, identifier in page["headings"]
            if tag in {"h2", "h3"}
        )
        body = parser.renderer.render(page["tokens"], parser.options, {"current": current})
        body = body.replace(
            "<table>",
            '<div class="table-scroll" role="region" aria-label="문서 표" tabindex="0"><table>',
        ).replace("</table>", "</table></div>")
        title = html.escape(page["title"])
        home = relative("index.html", current)
        doc_home = (
            relative(destination(Path("docs/00-index.md")), current)
            if Path("docs/00-index.md") in pages
            else home
        )
        source_url = SOURCE_URL + quote(source.as_posix(), safe="/.-_")
        template = Path(__file__).with_name("templates") / "document.html"
        rendered = template.read_text(encoding="utf-8").format(
            title=title,
            tokens=relative("tokens.css", current),
            stylesheet=relative("docs.css", current),
            home=home,
            doc_home=doc_home,
            source_url=source_url,
            navigation="".join(navigation),
            source=html.escape(source.as_posix()),
            toc=toc,
            body=body,
        )
        target = output / current
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    if diagrams:
        (output / "mermaid-diagrams.json").write_text(
            json.dumps(diagrams, ensure_ascii=False), encoding="utf-8"
        )
    return len(pages)
