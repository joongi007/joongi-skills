"""Proxy output contract: original structured result or explicit consent waiting."""

import copy
import hashlib
import json

APPROVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"const": "approval_required"},
        "execution": {"const": "not_started"},
        "approval_id": {"type": "string", "minLength": 40, "maxLength": 40},
    },
    "required": ["status", "execution", "approval_id"],
}


def proxy_output(tool, config, original_name=None):
    schema = tool.get("outputSchema")
    allowed = config.get("policy", {}).get("allowed_tools", [])
    if not isinstance(schema, dict) or (original_name or tool["name"]) in allowed or "*" in allowed:
        return tool
    if (
        config.get("auth", {}).get("type", "none") == "none"
        and not config.get("env")
        and not config.get("headers")
        and "policy" not in config
    ):
        return tool
    digest = hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).hexdigest()
    base = "https://joongi-hub.invalid/output/" + digest
    original = copy.deepcopy(schema)
    # A resource ID keeps local $refs rooted at the original schema after nesting.
    # These are JSON Schema identifiers, not endpoints fetched by the Hub.
    original.setdefault("$id", base + "/upstream")
    wrapped = {"$id": base, "type": "object", "anyOf": [original, APPROVAL_SCHEMA]}
    if "$schema" in schema:
        wrapped["$schema"] = schema["$schema"]
    return {**tool, "outputSchema": wrapped}
