from math import ceil


def clopper_pearson_interval(successes: int, trials: int, alpha: float = 0.05):
    """
    Exact (Clopper-Pearson) confidence interval for a binomial proportion.
    Returns lower/upper bounds as percentages rounded to one decimal.
    """
    if trials <= 0 or successes < 0 or successes > trials:
        return 0.0, 0.0

    if successes == 0:
        lower = 0.0
        upper = 1 - (alpha / 2) ** (1 / trials)
        return round(lower * 100, 1), round(upper * 100, 1)

    if successes == trials:
        lower = (alpha / 2) ** (1 / trials)
        upper = 1.0
        return round(lower * 100, 1), round(upper * 100, 1)

    def binom_cdf(k, n, p):
        if k < 0:
            return 0.0
        if k >= n:
            return 1.0
        if p <= 0:
            return 1.0
        if p >= 1:
            return 0.0

        prob = (1 - p) ** n
        cdf = prob
        for i in range(1, k + 1):
            prob *= (p / (1 - p)) * (n - i + 1) / i
            cdf += prob
        return float(min(max(cdf, 0.0), 1.0))

    def solve_lower():
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            tail = 1 - binom_cdf(successes - 1, trials, mid)
            if tail > alpha / 2:
                hi = mid
            else:
                lo = mid
        return hi

    def solve_upper():
        lo, hi = 0.0, 1.0
        target = 1 - alpha / 2
        for _ in range(60):
            mid = (lo + hi) / 2
            cdf = binom_cdf(successes, trials, mid)
            if cdf > target:
                lo = mid
            else:
                hi = mid
        return lo

    lower = solve_lower()
    upper = solve_upper()
    return round(lower * 100, 1), round(upper * 100, 1)
