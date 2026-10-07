"""Load Block from P1's schema, or the local stub until that file exists."""


def load_schema():
    try:
        from pipeline import schema as source
    except ImportError:
        from extractors import schema_stub as source
    return source
