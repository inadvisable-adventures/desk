import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from desk.schema_types import (  # noqa: E402
    ArrayType,
    LiteralType,
    ObjectMember,
    ObjectType,
    PrimitiveType,
    SchemaSyntaxError,
    UnionType,
    coerce,
    parse_type_expression,
    type_expressions_equivalent,
    validate,
)

passed = 0
failed = 0


def check(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"PASS: {name}")
    else:
        failed += 1
        print(f"FAIL: {name}")


# ---------- parsing ----------


def test_parse_primitives():
    check("string parses", parse_type_expression("string") == PrimitiveType("string"))
    check("number parses", parse_type_expression("number") == PrimitiveType("number"))
    check("boolean parses", parse_type_expression("boolean") == PrimitiveType("boolean"))
    check("null parses", parse_type_expression("null") == PrimitiveType("null"))


def test_parse_literals():
    check("string literal parses", parse_type_expression('"foo"') == LiteralType("foo"))
    check("single-quoted string literal parses", parse_type_expression("'foo'") == LiteralType("foo"))
    check("integer literal parses", parse_type_expression("5") == LiteralType(5))
    check("float literal parses", parse_type_expression("5.5") == LiteralType(5.5))
    check("negative literal parses", parse_type_expression("-5") == LiteralType(-5))
    check("true literal parses", parse_type_expression("true") == LiteralType(True))
    check("false literal parses", parse_type_expression("false") == LiteralType(False))


def test_parse_arrays():
    check("array parses", parse_type_expression("string[]") == ArrayType(PrimitiveType("string")))
    check(
        "double array parses",
        parse_type_expression("number[][]") == ArrayType(ArrayType(PrimitiveType("number"))),
    )


def test_parse_unions():
    node = parse_type_expression('"a" | "b" | 5')
    check(
        "union parses in order",
        node == UnionType((LiteralType("a"), LiteralType("b"), LiteralType(5))),
    )
    check(
        "parenthesized union inside array parses",
        parse_type_expression("(string | number)[]")
        == ArrayType(UnionType((PrimitiveType("string"), PrimitiveType("number")))),
    )


def test_parse_objects():
    node = parse_type_expression("{ a: string; b?: number }")
    check(
        "object with optional member parses",
        node
        == ObjectType(
            (
                ObjectMember("a", False, PrimitiveType("string")),
                ObjectMember("b", True, PrimitiveType("number")),
            )
        ),
    )
    check(
        "comma-separated object parses the same as semicolon-separated",
        parse_type_expression("{ a: string, b: number }")
        == ObjectType(
            (
                ObjectMember("a", False, PrimitiveType("string")),
                ObjectMember("b", False, PrimitiveType("number")),
            )
        ),
    )


def test_parse_errors():
    for bad in ["", "{", "string[", "foo", "{ a string }", "5abc", "string |", "{ a: }"]:
        try:
            parse_type_expression(bad)
            check(f"{bad!r} raises SchemaSyntaxError", False)
        except SchemaSyntaxError:
            check(f"{bad!r} raises SchemaSyntaxError", True)


# ---------- validation ----------


def test_validate_primitives():
    check("string validates a str", validate(PrimitiveType("string"), "hi"))
    check("string rejects a number", not validate(PrimitiveType("string"), 5))
    check("number validates an int", validate(PrimitiveType("number"), 5))
    check("number validates a float", validate(PrimitiveType("number"), 5.5))
    check("number rejects a bool (Python bool is an int subclass)", not validate(PrimitiveType("number"), True))
    check("boolean validates a bool", validate(PrimitiveType("boolean"), True))
    check("null validates None", validate(PrimitiveType("null"), None))
    check("null rejects a non-None value", not validate(PrimitiveType("null"), 0))


def test_validate_literals_and_unions():
    node = parse_type_expression('"a" | "b" | 5')
    check("union validates first option", validate(node, "a"))
    check("union validates second option", validate(node, "b"))
    check("union validates third option", validate(node, 5))
    check("union rejects a non-member value", not validate(node, "c"))


def test_validate_arrays():
    node = parse_type_expression("string[]")
    check("array validates a list of strings", validate(node, ["a", "b"]))
    check("array rejects a list with a wrong-typed element", not validate(node, ["a", 1]))
    check("array rejects a non-list", not validate(node, "a"))


def test_validate_objects_are_permissive_about_extra_keys():
    node = parse_type_expression("{ a: string; b?: number }")
    check("object validates with only the required member", validate(node, {"a": "x"}))
    check("object validates with the optional member present", validate(node, {"a": "x", "b": 1}))
    check("object rejects a missing required member", not validate(node, {"b": 1}))
    check("object allows extra keys not in the schema", validate(node, {"a": "x", "extra": "ignored"}))
    check("object rejects a non-dict", not validate(node, "not a dict"))


# ---------- coercion (best-effort, never raises) ----------


def test_coerce_never_raises_and_falls_back():
    check("coercing an already-valid value returns it unchanged", coerce(PrimitiveType("string"), "hi") == "hi")
    check("coercing a hopeless string to number returns it unchanged", coerce(PrimitiveType("number"), "not a number") == "not a number")


def test_coerce_primitives():
    check("number coerces a numeric string", coerce(PrimitiveType("number"), "5") == 5.0)
    check("string coerces a number", coerce(PrimitiveType("string"), 5) == "5")
    check("boolean coerces the string 'true'", coerce(PrimitiveType("boolean"), "true") is True)
    check("boolean coerces the string 'false'", coerce(PrimitiveType("boolean"), "false") is False)
    check("boolean coerces a nonzero number to True", coerce(PrimitiveType("boolean"), 1) is True)


def test_coerce_arrays_and_objects():
    check(
        "array coerces each element",
        coerce(ArrayType(PrimitiveType("string")), [1, 2]) == ["1", "2"],
    )
    node = parse_type_expression("{ a: number }")
    check(
        "object coerces a declared member's value",
        coerce(node, {"a": "5"}) == {"a": 5.0},
    )
    check(
        "object coercion leaves keys not in the schema untouched",
        coerce(node, {"a": "5", "extra": "kept"}) == {"a": 5.0, "extra": "kept"},
    )


def test_coerce_unions_tries_each_option():
    node = parse_type_expression("number | boolean")
    check("union coercion picks the first option that validates after coercing", coerce(node, "5") == 5.0)


# ---------- structural equivalence ----------


def test_equivalence():
    check(
        "reordered object members are equivalent",
        type_expressions_equivalent("{ a: string; b: number }", "{ b: number, a: string }"),
    )
    check(
        "reordered union options are equivalent",
        type_expressions_equivalent("string | number", "number | string"),
    )
    check("a genuinely different type is not equivalent", not type_expressions_equivalent("string", "number"))
    check(
        "differing optionality is not equivalent",
        not type_expressions_equivalent("{ a: string }", "{ a?: string }"),
    )


test_parse_primitives()
test_parse_literals()
test_parse_arrays()
test_parse_unions()
test_parse_objects()
test_parse_errors()
test_validate_primitives()
test_validate_literals_and_unions()
test_validate_arrays()
test_validate_objects_are_permissive_about_extra_keys()
test_coerce_never_raises_and_falls_back()
test_coerce_primitives()
test_coerce_arrays_and_objects()
test_coerce_unions_tries_each_option()
test_equivalence()

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
