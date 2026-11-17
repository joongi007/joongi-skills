"""Bounded, non-executing checks for a procedural 3D review manifest."""

import json
import math

from joongi_hub.errors import RpcError

STAGES = (
    "blockout",
    "structure",
    "form",
    "material",
    "surface",
    "lighting",
    "interaction",
    "optimization",
)

TOOL = {
    "name": "hub_3d_review",
    "description": "Validate a procedural Three.js reconstruction review manifest. "
    "Read building-procedural-3d first. Checks ordered passes, component/detail coverage, "
    "review evidence and measured budgets; does not render, execute code, verify files "
    "or judge visual similarity. A passed manifest is not visual certification.",
    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    "execution": {"taskSupport": "forbidden"},
    "inputSchema": {
        "type": "object",
        "properties": {
            "target_stage": {"type": "string", "enum": list(STAGES)},
            "report": {
                "type": "object",
                "description": "Manifest format in skill references/workflow.md.",
            },
        },
        "required": ["target_stage", "report"],
        "additionalProperties": False,
    },
}


def validate(target_stage, report):
    if target_stage not in STAGES or not isinstance(report, dict):
        raise RpcError(-32602, "target_stage와 report 객체를 확인하세요.")
    try:
        if len(json.dumps(report, allow_nan=False).encode()) > 128000:
            raise ValueError
    except (ValueError, TypeError, RecursionError):
        raise RpcError(-32602, "report는 128 KB 이하의 유한 JSON 값이어야 합니다.") from None
    errors = []

    def fail(message):
        if len(errors) < 50:
            errors.append(message)

    def text(value):
        return isinstance(value, str) and 0 < len(value.strip()) <= 2048

    def evidence(value):
        return isinstance(value, list) and 1 <= len(value) <= 8 and all(map(text, value))

    def score(value):
        return type(value) in {int, float} and 0 <= value <= 1

    if set(report) - {
        "references",
        "components",
        "details",
        "passes",
        "budget",
        "measurements",
        "limitations",
    }:
        fail("report에 알 수 없는 필드가 있습니다.")
    if not evidence(report.get("references")):
        fail("references: 참조 이미지 식별자 1~8개가 필요합니다.")
    components = report.get("components")
    if not isinstance(components, list) or not 1 <= len(components) <= 256:
        components = []
        fail("components: 구성요소 1~256개가 필요합니다.")
    ids = set()
    for item in components:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "purpose"}
            or not all(map(text, item.values()))
        ):
            fail("components: 각 항목에는 id와 purpose가 필요합니다.")
        elif item["id"] in ids:
            fail("components: id가 중복됩니다.")
        else:
            ids.add(item["id"])
    details = report.get("details")
    if not isinstance(details, list) or not 1 <= len(details) <= 1024:
        details = []
        fail("details: 형태를 식별하는 특징 1~1024개를 기록하세요.")
    detail_ids = set()
    for item in details:
        if not isinstance(item, dict) or set(item) != {
            "id",
            "component_id",
            "evidence",
            "confidence",
        }:
            fail("details: id/component_id/evidence/confidence가 필요합니다.")
            continue
        if not text(item["id"]) or item["id"] in detail_ids:
            fail("details: id가 비어 있거나 중복됩니다.")
        elif isinstance(item["component_id"], str) and item["component_id"] in ids:
            detail_ids.add(item["id"])
        else:
            fail("details: component_id가 실제 구성요소에 연결되지 않았습니다.")
        if not evidence(item["evidence"]) or not score(item["confidence"]):
            fail("details: 증거와 0~1의 confidence가 필요합니다.")
    passes = report.get("passes")
    required = list(STAGES[: STAGES.index(target_stage) + 1])
    if not isinstance(passes, list) or len(passes) != len(required):
        passes = []
        fail("passes: target_stage까지 모든 단계를 순서대로 제출하세요.")
    for expected, item in zip(required, passes, strict=False):
        if not isinstance(item, dict) or set(item) != {"stage", "evidence", "accepted", "notes"}:
            fail("passes: stage/evidence/accepted/notes가 필요합니다.")
            continue
        if item["stage"] != expected or item["accepted"] is not True:
            fail(expected + ": 단계 순서를 지키고 실제 검토에 통과해야 합니다.")
        if not evidence(item["evidence"]) or not text(item["notes"]):
            fail(expected + ": 렌더·측정 증거와 검토 기록이 필요합니다.")
    if not isinstance(report.get("limitations"), list) or not all(
        map(text, report.get("limitations", []))
    ):
        fail(
            "limitations: 보이지 않는 면·근사·미검증 기능을 배열로 기록하세요. "
            "없으면 빈 배열입니다."
        )
    if target_stage == "optimization":
        for key in ("draw_calls", "triangles", "frame_ms"):
            budget, measured = report.get("budget"), report.get("measurements")
            limit = budget.get(key) if isinstance(budget, dict) else None
            value = measured.get(key) if isinstance(measured, dict) else None
            if (
                type(limit) not in {int, float}
                or type(value) not in {int, float}
                or (isinstance(limit, float) and not math.isfinite(limit))
                or (isinstance(value, float) and not math.isfinite(value))
                or not 0 <= value <= limit
                or limit <= 0
            ):
                fail(key + ": 양수 예산과 그 이하의 실제 측정값이 필요합니다.")
    return {
        "status": "blocked" if errors else "passed",
        "target_stage": target_stage,
        "errors": errors,
        "verification": "manifest_only",
        "instructions": "실제 파일·렌더·시각적 유사도는 별도로 검토하세요. "
        "증거를 만들지 못했다면 통과했다고 주장하지 마세요.",
    }
