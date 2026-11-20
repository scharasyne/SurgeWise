"""Construct the feature matrix used during training and web inference."""

import numpy as np
import pandas as pd

WEEKS = 52
HORIZON = 6


def feature_blocks(origin, history, recent, last_year, annual, weights, past, shares,
                   *, weeks_ahead=HORIZON, first_week_offset=0):
    """Build the requested horizon blocks in the training feature order."""
    features = annual.copy()
    for lag in (0, 1, 2, 3, 4, 6, 8):
        features[f"local_lag{lag}"] = recent[lag]
    for window in (2, 4, 8, 12):
        features[f"local_mean{window}"] = recent[:window].mean(axis=0)
    features["local_growth"] = (features["local_mean2"] + 0.1) / (features["local_mean8"] + 0.1)
    features["neighbor_recent"] = weights @ features["local_mean4"]
    features["neighbor_growth"] = weights @ features["local_growth"]
    features["local_lag52"] = last_year
    for lag in (0, 1, 2, 4, 8, 12, 26, 52):
        features[f"city_lag{lag}"] = history[origin - lag] if origin >= lag else np.nan
    for window in (2, 4, 8, 12):
        features[f"city_mean{window}"] = history[origin - window + 1:origin + 1].mean()
    features["city_growth"] = (features["city_mean2"] + 1) / (features["city_mean8"] + 1)

    blocks = []
    for horizon in range(1, weeks_ahead + 1):
        target = origin + horizon
        week = (first_week_offset + target) % WEEKS
        angle = 2 * np.pi * week / WEEKS
        block = dict(
            features, horizon=horizon, sin_week=np.sin(angle), cos_week=np.cos(angle),
            gp_seasonal_last=past[-1, week], gp_seasonal_mean=past[:, week].mean(axis=0),
            gp_seasonal_share=shares[week], city_lastyear=history[target - WEEKS],
        )
        blocks.append(pd.DataFrame(block, index=range(len(last_year))))
    return pd.concat(blocks, ignore_index=True).astype("float32"), recent[0], shares
