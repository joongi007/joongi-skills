"""Read-only, namespaced skill roots with consistent catalog selection."""

import copy
from pathlib import Path
from urllib.parse import urlparse

from joongi_hub.errors import RpcError
from joongi_hub.skills import Skills


class CatalogSkills:
    def __init__(self, base, preferences):
        self.base = base
        self.preferences = preferences
        self.directory = base.directory

    def _items(self):
        result = {}
        for item in self.base.list():
            source_id = item.get(
                "source", "project" if item.get("scope") == "project" else "builtin"
            )
            result[item["name"]] = (self.base, item["name"], source_id, item)
        for source in self.preferences.sources():
            skills = Skills(Path(source["path"]))
            for item in skills.list():
                identity = source["id"] + "__" + item["name"]
                result[identity] = (
                    skills,
                    item["name"],
                    source["id"],
                    {
                        **item,
                        "name": identity,
                        "source": source["id"],
                        "source_name": source["name"],
                        "uri": Skills.uri(identity, item["name"] + "/SKILL.md"),
                    },
                )
        return result

    def inventory(self):
        result = []
        for name, (_, _, source, item) in sorted(self._items().items()):
            categories = self.preferences.categories("skill", name, source=source)
            result.append(
                {
                    **item,
                    "source": source,
                    "categories": categories,
                    "search_enabled": self.preferences.allows(
                        "skill", name, source=source, categories=categories
                    ),
                }
            )
        return result

    def list(self):
        return [item for item in self.inventory() if item["search_enabled"]]

    def _source(self, name):
        item = self._items().get(name)
        if item is None:
            raise RpcError(-32602, "Unknown skill in this catalog")
        source, original, source_id, _ = item
        categories = self.preferences.categories("skill", name, source=source_id)
        if not self.preferences.allows("skill", name, source=source_id, categories=categories):
            raise RpcError(-32602, "Skill is disabled in this catalog")
        return source, original

    @staticmethod
    def _rewrite(value, original, identity):
        result = copy.deepcopy(value)
        if original == identity:
            return result
        if isinstance(result, dict):
            for key, item in list(result.items()):
                if (
                    key == "uri"
                    and isinstance(item, str)
                    and item.startswith(Skills.uri(original, ""))
                ):
                    result[key] = (
                        Skills.uri(identity, original + "/") + item[len(Skills.uri(original, "")) :]
                    )
                elif key in {"resources", "resource", "files"}:
                    result[key] = CatalogSkills._rewrite(item, original, identity)
        elif isinstance(result, list):
            result = [CatalogSkills._rewrite(item, original, identity) for item in result]
        return result

    def read_bytes(self, name, path="SKILL.md"):
        source, original = self._source(name)
        value = self._rewrite(source.read_bytes(original, path), original, name)
        value["name"] = name
        return value

    def read(self, name, path="SKILL.md"):
        source, original = self._source(name)
        value = self._rewrite(source.read(original, path), original, name)
        value["name"] = name
        return value

    def _uri_source(self, uri):
        parsed = urlparse(uri)
        source, original = self._source(parsed.netloc)
        if parsed.netloc == original:
            return source, original, uri, parsed.netloc
        prefix = Skills.uri(parsed.netloc, original + "/")
        if not uri.startswith(prefix):
            raise RpcError(-32602, "Invalid namespaced skill URI")
        return source, original, Skills.uri(original, "") + uri[len(prefix) :], parsed.netloc

    def read_uri(self, uri):
        source, original, original_uri, identity = self._uri_source(uri)
        value = self._rewrite(source.read_uri(original_uri), original, identity)
        value["name"] = identity
        return value

    def read_directory(self, uri):
        source, original, original_uri, identity = self._uri_source(uri)
        return self._rewrite(source.read_directory(original_uri), original, identity)

    def entry(self, name):
        source, original = self._source(name)
        return self._rewrite(source.entry(original), original, name)

    def entries(self):
        return [self.entry(item["name"]) for item in self.list()]
