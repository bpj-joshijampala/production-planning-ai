from uuid import uuid4


def new_uuid() -> str:
    return str(uuid4())
