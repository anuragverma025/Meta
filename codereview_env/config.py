from pydantic import BaseModel


class PaginationConfig(BaseModel):
    MIN_PAGE: int = 1
    MAX_PAGE_SIZE: int = 100
    DEFAULT_PAGE_SIZE: int = 10
    ERROR_INVALID_PAGE: str = "Page number must be >= {min_page}"
    ERROR_INVALID_SIZE: str = "Page size must be between 1 and {max_size}"
    ERROR_NOT_A_LIST: str = "Items must be a list"
    ERROR_NOT_NUMERIC: str = "Page and PageSize must be numeric"


class RewardConfig(BaseModel):
    MIN_REWARD: float = 0.0
    MAX_REWARD: float = 1.0
    DECIMAL_PRECISION: int = 4
    BONUS_COEFFICIENT: float = 0.75


class SafetyConfig(BaseModel):
    pagination: PaginationConfig = PaginationConfig()
    reward: RewardConfig = RewardConfig()


# Centralized configuration singleton
CONFIG = SafetyConfig()
