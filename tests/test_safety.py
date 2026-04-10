import pytest
from unittest.mock import patch
from codereview_env.safety import SafePaginationFacade, SafeRewardCalculator
from codereview_env.config import CONFIG

# ── Tests for Pagination Wrapper ──────────────────────────────────────────────


def test_pagination_happy_path():
    """Verify correct inputs reach the existing system."""
    items = [1, 2, 3, 4, 5]
    facade = SafePaginationFacade(items)

    with patch("codereview_env.safety.get_paged_items") as mock_legacy:
        mock_legacy.return_value = [1, 2]
        result = facade.get_page(page=1, page_size=2)

        assert result == [1, 2]
        mock_legacy.assert_called_once_with(items, 1, 2)


def test_pagination_boundary_limits():
    """Test max page size from config."""
    items = list(range(200))
    facade = SafePaginationFacade(items)

    # Exceed max size
    with pytest.raises(ValueError) as exc:
        facade.get_page(
            page=CONFIG.pagination.MIN_PAGE,
            page_size=CONFIG.pagination.MAX_PAGE_SIZE * 2,
        )
    expected_msg = CONFIG.pagination.ERROR_INVALID_SIZE.format(
        max_size=CONFIG.pagination.MAX_PAGE_SIZE
    )
    assert expected_msg in str(exc.value)


def test_pagination_edge_cases():
    """Test 0, -1, and None (empty list)."""
    # Empty list
    facade = SafePaginationFacade([])
    result = facade.get_page(page=1)
    assert result == []

    # Page before min_page
    facade = SafePaginationFacade([1, 2, 3])
    with pytest.raises(ValueError) as exc:
        facade.get_page(page=CONFIG.pagination.MIN_PAGE - 1)
    expected_msg = CONFIG.pagination.ERROR_INVALID_PAGE.format(
        min_page=CONFIG.pagination.MIN_PAGE
    )
    assert expected_msg in str(exc.value)


def test_pagination_wrong_types():
    """Test string input for numeric fields."""
    facade = SafePaginationFacade([1, 2])
    with pytest.raises(TypeError):
        facade.get_page(page="first_page")


# ── Tests for Reward Calculator ───────────────────────────────────────────────


def test_reward_precision():
    """Prove that rounding only happens at the final step."""
    # (0.55555 * 0.75) + 0.12345 = 0.4166625 + 0.12345 = 0.5401125
    # Rounded to 4 digits: 0.5401
    score = 0.55555
    bonus = 0.12345

    result = SafeRewardCalculator.calculate_final_reward(score, bonus)
    assert result == 0.5401


def test_reward_clipping():
    """Verify max reward boundary."""
    # Should clip to MAX_REWARD per CONFIG
    result = SafeRewardCalculator.calculate_final_reward(
        CONFIG.reward.MAX_REWARD, CONFIG.reward.MAX_REWARD
    )
    assert result == CONFIG.reward.MAX_REWARD
