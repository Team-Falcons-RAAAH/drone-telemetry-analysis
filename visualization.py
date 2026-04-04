"""
visualization.py
================
Конвертація GPS-координат WGS-84 → ENU (East-North-Up).

Приймає DataFrame від parser.gpsData() і повертає його з доданими
колонками E, N, U у метрах відносно точки зльоту.

Використання:
    from parser import parser
    from visualization import add_enu_columns

    df_gps = parser.gpsData('flight.bin')
    df_gps = add_enu_columns(df_gps)
    # df_gps тепер містить колонки E, N, U — передавай далі
"""

import math
import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_000


def add_enu_columns(df_gps: pd.DataFrame) -> pd.DataFrame:
    """
    Приймає df_gps від parser.gpsData() і додає колонки E, N, U.

    Вхід (від parser.gpsData):
        timestamp  float64  — Unix timestamp у секундах
        lat        float64  — широта у градусах (WGS-84)
        lon        float64  — довгота у градусах (WGS-84)
        alt        float64  — висота у метрах
        spd        float64  — горизонтальна швидкість у м/с

    Вихід — той самий DataFrame плюс три нові колонки:
        E   float64  — зміщення на схід від точки зльоту, метри
        N   float64  — зміщення на північ від точки зльоту, метри
        U   float64  — зміщення вгору від точки зльоту, метри

    Математична основа:
        Перша точка стає origin (0, 0, 0).
        N = Δlat_rad * R
        E = Δlon_rad * R * cos(lat0)   ← cos компенсує стиснення
                                           паралелей при відході від
                                           екватора
        U = alt - alt0
    """
    if df_gps.empty:
        df_gps = df_gps.copy()
        df_gps['E'] = pd.Series(dtype='float64')
        df_gps['N'] = pd.Series(dtype='float64')
        df_gps['U'] = pd.Series(dtype='float64')
        return df_gps

    df = df_gps.copy().reset_index(drop=True)

    lat0 = df['lat'].iloc[0]
    lon0 = df['lon'].iloc[0]
    alt0 = df['alt'].iloc[0]

    lat0_rad = math.radians(lat0)

    df['E'] = np.radians(df['lon'] - lon0) * EARTH_RADIUS_M * math.cos(lat0_rad)
    df['N'] = np.radians(df['lat'] - lat0) * EARTH_RADIUS_M
    df['U'] = df['alt'] - alt0

    return df