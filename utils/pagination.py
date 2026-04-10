# EXISTING CODE - DO NOT MODIFY (Treat as Read-Only Library)


def get_paged_items(items: list, page: int, page_size: int) -> list:
    """
    Existing buggy/unsafe pagination logic.
    - Fails on page 0 (returns negative slice)
    - No type checking
    - No bounds checking
    """
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end]
