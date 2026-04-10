from typing import Any, List, Optional
from codereview_env.config import CONFIG
from utils.pagination import get_paged_items


class PaginationValidator:
    """
    Validation layer for pagination inputs.
    Strictly handles edge cases and enforced constraints.
    """

    @staticmethod
    def validate_inputs(items: List[Any], page: Any, page_size: Any) -> tuple[int, int]:
        """
        Validates types and ranges for pagination.

        Formula:
        min_page = CONFIG.pagination.MIN_PAGE
        max_size = CONFIG.pagination.MAX_PAGE_SIZE
        """
        # Rule 3.1: Wrong types
        if not isinstance(items, list):
            raise TypeError(CONFIG.pagination.ERROR_NOT_A_LIST)

        try:
            p = int(page)
            ps = int(page_size)
        except (ValueError, TypeError):
            raise TypeError(CONFIG.pagination.ERROR_NOT_NUMERIC)

        # Rule 3.1: Null/Zero/Negative
        conf = CONFIG.pagination
        if p < conf.MIN_PAGE:
            msg = conf.ERROR_INVALID_PAGE.format(min_page=conf.MIN_PAGE)
            raise ValueError(msg)

        if ps < conf.MIN_PAGE or ps > conf.MAX_PAGE_SIZE:
            msg = conf.ERROR_INVALID_SIZE.format(max_size=conf.MAX_PAGE_SIZE)
            raise ValueError(msg)

        return p, ps


class SafePaginationFacade:
    """
    Facade pattern providing a safe entry point to the pagination system.
    Complies with Rule 1: Zero modifications to existing code.
    """

    def __init__(self, items: List[Any]):
        self._items = items
        self._length = len(items)

    def get_page(self, page: int, page_size: Optional[int] = None) -> List[Any]:
        """
        Safely retrieves a page of items.
        Calls the underlying black-box system after thorough validation.
        """
        ps = page_size if page_size is not None else CONFIG.pagination.DEFAULT_PAGE_SIZE

        # Validation Layer
        clean_page, clean_ps = PaginationValidator.validate_inputs(
            self._items, page, ps
        )

        # Rule 3.1: Handle empty list or out-of-bounds gracefully before calling existing
        if not self._items:
            return []

        # Existing System Call
        return get_paged_items(self._items, clean_page, clean_ps)


class SafeRewardCalculator:
    """
    Wrapper for reward calculations to ensure mathematical accuracy.
    """

    @staticmethod
    def calculate_final_reward(score: float, bonus: float) -> float:
        """
        Mathematically correct reward summation with final-step rounding.

        Boundary Math:
        score [0.0, 1.0], bonus [0.0, 0.25]
        Return range: [0.0, 1.0]
        """
        conf = CONFIG.reward

        # Intermediate calculations (full precision)
        # Using raw floats for calculation per Rule 3.5
        total = (score * conf.BONUS_COEFFICIENT) + bonus

        # Clipping to safety boundaries
        safe_total = max(conf.MIN_REWARD, min(conf.MAX_REWARD, total))

        # Rule 3.5: Round floating-point numbers ONLY at the final output step
        return round(safe_total, conf.DECIMAL_PRECISION)
