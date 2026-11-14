"""Labels must survive missing (NaN) inputs, which the models impute."""

import math

import numpy as np
import pytest

from app.ml.explain import describe
from app.ml.labels import fmt_hour, fmt_num, fmt_value


@pytest.mark.parametrize(
    "base", ["completion_rate", "sleep_hours", "min_deep_work", "first_hour", "plan_ratio", "mood"]
)
def test_fmt_value_nan_is_no_data(base):
    assert fmt_value(base, float("nan")) == "no data"
    assert fmt_value(base, np.float64("nan")) == "no data"
    assert fmt_value(base, None) == "no data"


def test_fmt_helpers_nan():
    assert fmt_num(math.nan) == "?"
    assert fmt_hour(math.nan) == "?"
    assert fmt_value("completion_rate", 0.5) == "50%"


def test_describe_nan_feature():
    assert describe("completion_rate_r7", float("nan"), [], {}).endswith("no data")
