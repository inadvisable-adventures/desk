"""Stable TODO item id generation, shared by scripts/todo_item_ids.py and
the TODO widget (widgets/todo/). See development-process.md's "Item IDs"
section and how-to-convert-item-id-one-time.md for the full scheme.

Deliberately just make_item_id here, not an item-start regex too: the
one-time conversion script and the TODO widget need different patterns
(the script only ever matches plain numbers, converting *from* that
format; the widget's desk.todo_file needs to also recognize already
-converted hash ids, since it reads arbitrary projects' TODO.md files).
Each keeps its own regex scoped to its actual need."""
import hashlib
import secrets

ID_LENGTH = 7
SHORT_DESCRIPTION_THRESHOLD = 10


def make_item_id(description: str) -> str:
    """Stable id derived from an item's description at the moment the id
    is assigned. If the description is shorter than
    SHORT_DESCRIPTION_THRESHOLD characters, hash a random string instead
    (a short description alone wouldn't give a well-distributed hash).
    Once assigned, this is just an opaque label -- never recompute it from
    a later-edited description."""
    text = description if len(description) >= SHORT_DESCRIPTION_THRESHOLD else secrets.token_hex(8)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:ID_LENGTH]
