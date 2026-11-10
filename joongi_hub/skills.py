"""Progressive disclosure of local skill sources, with path confinement."""

import base64
import hashlib
import math
import mimetypes
import re
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from joongi_hub._vendor import yaml
from joongi_hub.errors import RpcError

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_FILE_BYTES = 1024 * 1024
IGNORED = {".git", "__pycache__", ".DS_Store"}


class MetadataLoader(yaml.SafeLoader):
    """Bound YAML aliases, nesting and nodes before constructing untrusted data."""

    def __init__(self, stream):
        super().__init__(stream)
        self.node_count = 0
        self.node_depth = 0

    def compose_node(self, parent, index):
        self.node_count += 1
        self.node_depth += 1
        if self.node_count > 10000 or self.node_depth > 40:
            raise yaml.YAMLError("Skill metadata exceeds structural limits")
        try:
            return super().compose_node(parent, index)
        finally:
            self.node_depth -= 1

    def construct_mapping(self, node, deep=False):
        if any(key.tag == "tag:yaml.org,2002:merge" for key, _ in node.value):
            raise yaml.YAMLError("YAML merge keys are not supported in skill metadata")
        return super().construct_mapping(node, deep=deep)


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise RpcError(-32602, "SKILL.md requires YAML frontmatter")
    try:
        end = lines.index("---", 1)
        loader = MetadataLoader("\n".join(lines[1:end]))
        try:
            fields = loader.get_single_data()
        finally:
            loader.dispose()
    except (ValueError, yaml.YAMLError, RecursionError) as exc:
        raise RpcError(-32602, "Invalid or overly complex YAML frontmatter") from exc
    visits = [0]

    def check(value, ancestors=()):
        visits[0] += 1
        if visits[0] > 10000 or len(ancestors) > 40:
            raise RpcError(-32602, "Metadata aliases expand beyond the supported limit")
        if isinstance(value, (dict, list)):
            if id(value) in ancestors:
                raise RpcError(-32602, "Recursive YAML aliases are not supported")
            lineage = (*ancestors, id(value))
            if isinstance(value, dict):
                if not all(isinstance(key, str) for key in value):
                    raise RpcError(-32602, "Metadata object keys must be strings")
                for item in value.values():
                    check(item, lineage)
            else:
                for item in value:
                    check(item, lineage)
        elif isinstance(value, float) and not math.isfinite(value):
            raise RpcError(-32602, "Non-finite metadata numbers are not valid JSON")
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise RpcError(-32602, "Metadata must contain JSON-compatible YAML values")

    check(fields)
    if not isinstance(fields, dict):
        raise RpcError(-32602, "Skill frontmatter must be an object")
    if not isinstance(fields.get("name"), str) or not NAME_PATTERN.fullmatch(fields["name"]):
        raise RpcError(-32602, "Invalid skill metadata name")
    if len(fields["name"]) > 64:
        raise RpcError(-32602, "Skill names must be at most 64 characters")
    description = fields.get("description")
    if not isinstance(description, str) or not description or len(description) > 1024:
        raise RpcError(-32602, "Skill description must be text (up to 1024 characters)")
    return fields


class Skills:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()

    def list(self):
        if not self.directory.exists():
            return []
        result = []
        for folder in sorted(self.directory.iterdir()):
            entry = folder / "SKILL.md"
            if not NAME_PATTERN.fullmatch(folder.name) or not entry.is_file():
                continue
            if folder.is_symlink() or entry.is_symlink():
                continue
            try:
                fields = frontmatter(self.read(folder.name)["content"])
            except RpcError:
                continue
            description = fields["description"]
            files = [
                path.relative_to(folder).as_posix()
                for path in sorted(folder.rglob("*"))
                if path.is_file()
                and not path.is_symlink()
                and not any(part in IGNORED for part in path.relative_to(folder).parts)
                and path.resolve().is_relative_to(folder.resolve())
            ]
            result.append(
                {
                    "name": folder.name,
                    "description": description,
                    "files": files,
                    "uri": self.uri(folder.name),
                }
            )
        return result

    @staticmethod
    def uri(name, path="SKILL.md"):
        return "skill://" + name + "/" + quote(path, safe="/")

    def read_bytes(self, name, path="SKILL.md"):
        if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
            raise RpcError(-32602, "Invalid skill name")
        if not isinstance(path, str) or not path or "\\" in path:
            raise RpcError(-32602, "Invalid skill path")
        folder = self.directory / name
        target = folder / path
        resolved = target.resolve()
        if (
            folder.is_symlink()
            or not resolved.is_relative_to(folder.resolve())
            or not folder.resolve().is_relative_to(self.directory)
            or not resolved.is_file()
            or any(part in IGNORED for part in target.parts)
        ):
            raise RpcError(-32602, "Skill file not found")
        if any(
            part.is_symlink()
            for part in [target, *target.parents]
            if part != self.directory and part.is_relative_to(self.directory)
        ):
            raise RpcError(-32602, "Symlink skill files are not served")
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise RpcError(-32602, "Skill file exceeds 1 MiB")
        return resolved.read_bytes()

    def read(self, name, path="SKILL.md"):
        raw = self.read_bytes(name, path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        result = {"name": name, "path": path, "mimeType": mime}
        try:
            result["content"] = raw.decode("utf-8")
        except UnicodeDecodeError:
            result["blob"] = base64.b64encode(raw).decode("ascii")
        return result

    def read_uri(self, uri):
        parsed = urlparse(uri)
        if parsed.scheme != "skill" or parsed.query or parsed.fragment:
            raise RpcError(-32602, "Invalid skill URI")
        return self.read(parsed.netloc, unquote(parsed.path.lstrip("/")))

    def read_directory(self, uri):
        parsed = urlparse(uri)
        name = parsed.netloc
        relative = unquote(parsed.path.lstrip("/"))
        if (
            parsed.scheme != "skill"
            or not NAME_PATTERN.fullmatch(name)
            or parsed.query
            or parsed.fragment
            or "\\" in relative
            or ".." in relative.split("/")
            or any(part in IGNORED for part in relative.split("/"))
        ):
            raise RpcError(-32602, "Invalid skill directory URI")
        folder = self.directory / name
        target = folder / relative
        if (
            not target.is_dir()
            or folder.is_symlink()
            or not target.resolve().is_relative_to(folder.resolve())
            or not folder.resolve().is_relative_to(self.directory)
            or any(
                part.is_symlink()
                for part in [target, *target.parents]
                if part.is_relative_to(self.directory)
            )
        ):
            raise RpcError(-32602, "Skill directory not found")
        result = []
        for child in sorted(target.iterdir()):
            if child.is_symlink() or child.name in IGNORED:
                continue
            result.append(
                {
                    "name": child.name,
                    "uri": self.uri(name, child.relative_to(folder).as_posix()),
                    "mimeType": "inode/directory"
                    if child.is_dir()
                    else mimetypes.guess_type(child.name)[0] or "application/octet-stream",
                }
            )
        return result

    def entry(self, name):
        """Native skill entry with safe YAML and byte-exact supporting-file manifests."""
        skill = next((item for item in self.list() if item["name"] == name), None)
        if skill is None:
            raise RpcError(-32602, "Unknown skill")
        text = self.read(name)["content"]
        fields = frontmatter(text)
        metadata = fields.get("metadata")
        if metadata is not None and (
            not isinstance(metadata, dict)
            or not all(isinstance(value, str) for value in metadata.values())
        ):
            raise RpcError(-32602, "Agent Skills metadata must map names to strings")
        if fields.get("name") != name or not fields.get("description"):
            raise RpcError(-32602, "Invalid skill metadata")
        resources = []
        folder = self.directory / name
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                raise RpcError(-32602, "Skill manifests cannot include symlinks")
            relative = path.relative_to(folder).as_posix()
            if any(part in IGNORED for part in path.relative_to(folder).parts):
                continue
            content = self.read_bytes(name, relative)
            resources.append(
                {
                    "uri": self.uri(name, relative),
                    "size": len(content),
                    "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
                }
            )
            if len(resources) > 512 or sum(item["size"] for item in resources) > 16 * 1024 * 1024:
                raise RpcError(-32602, "A skill may contain at most 512 files and 16 MiB")
        return {"uri": self.uri(name), "frontmatter": fields, "resources": resources}

    def entries(self):
        entries = []
        for skill in self.list():
            try:
                entries.append(self.entry(skill["name"]))
            except RpcError:
                continue
        return entries
