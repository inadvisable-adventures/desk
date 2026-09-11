"""A pragmatic, intentionally-constrained subset of TypeScript type
expression syntax (TODO af7898b) -- primitives, literals, arrays, unions,
and simple object shapes, stored as a raw string (matching app_dsl
/schema.py's own StateSlot.type convention) and parsed here into a real
AST so Desk can validate/coerce a JSON value against it at runtime. No
intersections, generics, tuples, or unknown/any/never in this pass --
left to grow later if a real need shows up.

Grammar:
    type      := union
    union     := atom ("|" atom)*
    atom      := primitive | literal | array | object | "(" type ")"
    primitive := "string" | "number" | "boolean" | "null"
    literal   := STRING | NUMBER | "true" | "false"
    array     := atom ("[]")+
    object    := "{" (member SEPARATOR?)* "}"
    member    := IDENT "?"? ":" type
"""

import re
from dataclasses import dataclass

TOKEN_RE = re.compile(
    r"""
      \s*(?:
        (?P<string>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
      | (?P<number>-?\d+(?:\.\d+)?)
      | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
      | (?P<punct>\[\]|[|(){}:;,?])
      )
    """,
    re.VERBOSE,
)

PRIMITIVE_NAMES = ("string", "number", "boolean", "null")


class SchemaSyntaxError(ValueError):
    pass


@dataclass(frozen=True)
class PrimitiveType:
    name: str  # one of PRIMITIVE_NAMES


@dataclass(frozen=True)
class LiteralType:
    value: object  # str | float | bool


@dataclass(frozen=True)
class ArrayType:
    element: "TypeNode"


@dataclass(frozen=True)
class UnionType:
    options: tuple["TypeNode", ...]


@dataclass(frozen=True)
class ObjectMember:
    name: str
    optional: bool
    type: "TypeNode"


@dataclass(frozen=True)
class ObjectType:
    members: tuple[ObjectMember, ...]


TypeNode = PrimitiveType | LiteralType | ArrayType | UnionType | ObjectType


def _tokenize(text: str) -> list[str]:
    tokens = []
    pos = 0
    while pos < len(text):
        match = TOKEN_RE.match(text, pos)
        if match is None or match.end() == pos:
            remainder = text[pos:].strip()
            if not remainder:
                break
            raise SchemaSyntaxError(f"Unexpected character in type expression: {remainder[0]!r}")
        pos = match.end()
        token = match.group("string") or match.group("number") or match.group("ident") or match.group("punct")
        if token is not None:
            tokens.append(token)
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> str | None:
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _advance(self) -> str:
        token = self._peek()
        if token is None:
            raise SchemaSyntaxError("Unexpected end of type expression")
        self._pos += 1
        return token

    def _expect(self, token: str) -> None:
        actual = self._advance()
        if actual != token:
            raise SchemaSyntaxError(f"Expected {token!r}, got {actual!r}")

    def parse_type(self) -> TypeNode:
        node = self.parse_union()
        if self._peek() is not None:
            raise SchemaSyntaxError(f"Unexpected trailing token: {self._peek()!r}")
        return node

    def parse_union(self) -> TypeNode:
        options = [self.parse_array()]
        while self._peek() == "|":
            self._advance()
            options.append(self.parse_array())
        return options[0] if len(options) == 1 else UnionType(tuple(options))

    def parse_array(self) -> TypeNode:
        node = self.parse_atom()
        while self._peek() == "[]":
            self._advance()
            node = ArrayType(node)
        return node

    def parse_atom(self) -> TypeNode:
        token = self._peek()
        if token is None:
            raise SchemaSyntaxError("Unexpected end of type expression")
        if token == "(":
            self._advance()
            node = self.parse_union()
            self._expect(")")
            return node
        if token == "{":
            return self.parse_object()
        if token[0] in "\"'":
            self._advance()
            return LiteralType(token[1:-1])
        if token == "true":
            self._advance()
            return LiteralType(True)
        if token == "false":
            self._advance()
            return LiteralType(False)
        if re.fullmatch(r"-?\d+(\.\d+)?", token):
            self._advance()
            return LiteralType(float(token) if "." in token else int(token))
        if token in PRIMITIVE_NAMES:
            self._advance()
            return PrimitiveType(token)
        raise SchemaSyntaxError(f"Unexpected token: {token!r}")

    def parse_object(self) -> TypeNode:
        self._expect("{")
        members = []
        while self._peek() != "}":
            name = self._advance()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise SchemaSyntaxError(f"Expected a member name, got {name!r}")
            optional = False
            if self._peek() == "?":
                self._advance()
                optional = True
            self._expect(":")
            member_type = self.parse_union()
            members.append(ObjectMember(name=name, optional=optional, type=member_type))
            if self._peek() in (";", ","):
                self._advance()
            elif self._peek() != "}":
                raise SchemaSyntaxError(f"Expected ';', ',', or '}}', got {self._peek()!r}")
        self._expect("}")
        return ObjectType(tuple(members))


def parse_type_expression(text: str) -> TypeNode:
    tokens = _tokenize(text)
    if not tokens:
        raise SchemaSyntaxError("Empty type expression")
    return _Parser(tokens).parse_type()


def validate(node: TypeNode, value: object) -> bool:
    if isinstance(node, PrimitiveType):
        if node.name == "string":
            return isinstance(value, str)
        if node.name == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if node.name == "boolean":
            return isinstance(value, bool)
        if node.name == "null":
            return value is None
        return False
    if isinstance(node, LiteralType):
        if isinstance(node.value, bool) or isinstance(value, bool):
            return value is node.value
        return type(node.value) is type(value) and value == node.value
    if isinstance(node, ArrayType):
        return isinstance(value, list) and all(validate(node.element, item) for item in value)
    if isinstance(node, UnionType):
        return any(validate(option, value) for option in node.options)
    if isinstance(node, ObjectType):
        if not isinstance(value, dict):
            return False
        for member in node.members:
            if member.name not in value:
                if not member.optional:
                    return False
                continue
            if not validate(member.type, value[member.name]):
                return False
        return True
    raise TypeError(f"Unknown type node: {node!r}")  # pragma: no cover


def coerce(node: TypeNode, value: object) -> object:
    """Best-effort -- never raises. Returns `value` unchanged whenever no
    sensible coercion applies, rather than failing the whole call: this
    is only ever used for the non-validated, call-site typeHint path
    (see plans/state-store-schema-core.md), which has no "reject" outcome
    at all, only "coerced" or "left as-is"."""
    if validate(node, value):
        return value
    if isinstance(node, PrimitiveType):
        try:
            if node.name == "string":
                return value if isinstance(value, str) else json_scalar_to_str(value)
            if node.name == "number":
                return float(value) if isinstance(value, str) else value
            if node.name == "boolean":
                return _coerce_boolean(value)
        except (TypeError, ValueError):
            return value
        return value
    if isinstance(node, ArrayType):
        if isinstance(value, list):
            return [coerce(node.element, item) for item in value]
        return value
    if isinstance(node, UnionType):
        for option in node.options:
            coerced = coerce(option, value)
            if validate(option, coerced):
                return coerced
        return value
    if isinstance(node, ObjectType):
        if not isinstance(value, dict):
            return value
        result = dict(value)
        for member in node.members:
            if member.name in result:
                result[member.name] = coerce(member.type, result[member.name])
        return result
    return value


def json_scalar_to_str(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _coerce_boolean(value: object) -> object:
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return value


def _normalize(node: TypeNode):
    """A hashable, order-independent representation for structural
    equivalence -- object members sorted by name, union options sorted
    by their own normalized repr, so member/option order in the source
    text never affects equivalence."""
    if isinstance(node, PrimitiveType):
        return ("primitive", node.name)
    if isinstance(node, LiteralType):
        return ("literal", type(node.value).__name__, node.value)
    if isinstance(node, ArrayType):
        return ("array", _normalize(node.element))
    if isinstance(node, UnionType):
        return ("union", tuple(sorted(_normalize(o) for o in node.options)))
    if isinstance(node, ObjectType):
        return (
            "object",
            tuple(sorted((m.name, m.optional, _normalize(m.type)) for m in node.members)),
        )
    raise TypeError(f"Unknown type node: {node!r}")  # pragma: no cover


def type_expressions_equivalent(a: str, b: str) -> bool:
    return _normalize(parse_type_expression(a)) == _normalize(parse_type_expression(b))
