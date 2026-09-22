"""Closed content-plan record validation, without an optional dependency.

The checked-in schema is the cross-language contract fixture. Registry and
runtime-profile checks are performed by content_plan.validate after this pass.
"""
import json
import pkgutil
import re

SCHEMA = json.loads(pkgutil.get_data(__package__, "data/content-plan-v1.schema.json"))


def validate_shape(plan):
    def require(condition, path, message):
        if not condition:
            raise ValueError(f"{path}: {message}")

    def exact_equal(a, b):
        return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def check(value, shape, path):
        if "$ref" in shape:
            return check(value, SCHEMA["$defs"][shape["$ref"].split("/")[-1]], path)
        for keyword in ("oneOf", "anyOf"):
            if keyword in shape:
                count = 0
                for candidate in shape[keyword]:
                    try:
                        check(value, candidate, path)
                    except ValueError:
                        continue
                    count += 1
                require(count == 1 if keyword == "oneOf" else count > 0, path, "unsupported record shape")
                return
        if "const" in shape:
            require(exact_equal(value, shape["const"]), path, "unexpected constant")
        if "enum" in shape:
            require(any(exact_equal(value, x) for x in shape["enum"]), path, "unknown enum value")
        kind = shape.get("type")
        types = dict(object=dict, array=list, integer=int, string=str, boolean=bool, null=type(None))
        if kind:
            require(type(value) is types[kind], path, "expected " + kind)
        if kind == "object":
            require(set(shape.get("required", ())) <= set(value), path, "missing required fields")
            if shape.get("additionalProperties") is False:
                require(set(value) <= set(shape["properties"]), path, "unknown fields")
            for key, field in value.items():
                check(field, shape["properties"][key], path + "." + key)
        elif kind == "array":
            require(shape.get("minItems", 0) <= len(value) <= shape.get("maxItems", 4096), path, "array bounds")
            if shape.get("uniqueItems"):
                require(len({json.dumps(x, sort_keys=True) for x in value}) == len(value), path, "duplicate values")
            for i, field in enumerate(value):
                check(field, shape["items"], f"{path}[{i}]")
        elif kind == "string":
            require(shape.get("minLength", 0) <= len(value) <= shape.get("maxLength", 128), path, "string bounds")
            if "pattern" in shape:
                require(re.fullmatch(shape["pattern"], value) is not None, path, "invalid string")
        elif kind == "integer":
            require(shape.get("minimum", -(2**53-1)) <= value <= shape.get("maximum", 2**53-1), path, "integer bounds")

    stack = [(plan, 0)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        require(depth <= 32 and nodes <= 500000, "content_plan", "nesting/node budget")
        require(type(value) is not float, "content_plan", "float token")
        if isinstance(value, str):
            require(len(value.encode("utf-8")) <= 128, "content_plan", "UTF-8 string budget")
        elif isinstance(value, dict):
            stack.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            stack.extend((v, depth + 1) for v in value)
    require(len(json.dumps(plan, ensure_ascii=False, separators=(",", ":")).encode()) <= 16*1024*1024,
            "content_plan", "byte budget")
    check(plan, SCHEMA, "content_plan")
