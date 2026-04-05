"""
visualization.py
================
Два модулі в одному файлі:

1. add_enu_columns(df_gps)  — конвертація WGS-84 → ENU координати
2. get_plot_data(df_gps)    — повертає сирі масиви для Plotly.js у браузері

Використання в app.py:
    from visualization import add_enu_columns, get_plot_data

    df_gps    = parser.gpsData(path)
    df_gps    = add_enu_columns(df_gps)
    plot_data = get_plot_data(df_gps)      # передається в шаблон як JSON
"""

import json
import math

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_000


# ── 1. WGS-84 → ENU ──────────────────────────────────────────────────────────

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
    """
    if df_gps.empty:
        df = df_gps.copy()
        df['E'] = pd.Series(dtype='float64')
        df['N'] = pd.Series(dtype='float64')
        df['U'] = pd.Series(dtype='float64')
        return df

    df = df_gps.copy().reset_index(drop=True)

    lat0     = df['lat'].iloc[0]
    lon0     = df['lon'].iloc[0]
    alt0     = df['alt'].iloc[0]
    lat0_rad = math.radians(lat0)

    df['E'] = np.radians(df['lon'] - lon0) * EARTH_RADIUS_M * math.cos(lat0_rad)
    df['N'] = np.radians(df['lat'] - lat0) * EARTH_RADIUS_M
    df['U'] = df['alt'] - alt0

    return df


# ── 2. Дані для Plotly.js ─────────────────────────────────────────────────────

def get_plot_data(df_gps: pd.DataFrame) -> str:
    """
    Повертає JSON-рядок з масивами координат і швидкостей.
    Граф будується повністю в браузері через Plotly.js —
    жодних залежностей від plotly Python пакету.

    Повертає:
        str — JSON з полями E, N, U, spd, takeoff, landing
              або 'null' якщо DataFrame порожній

    Використання в app.py:
        plot_data = get_plot_data(df_gps)
        render_template('dashboard.html', plot_data=plot_data, ...)

    Використання в dashboard.html:
        const d = {{ plot_data | safe }};
        // d.E, d.N, d.U, d.spd — масиви float
        // d.takeoff, d.landing  — { E, N, U }
    """
    if df_gps.empty or 'E' not in df_gps.columns:
        return 'null'

    data = {
        'E':   df_gps['E'].round(2).tolist(),
        'N':   df_gps['N'].round(2).tolist(),
        'U':   df_gps['U'].round(2).tolist(),
        'spd': df_gps['spd'].round(3).tolist() if 'spd' in df_gps.columns else [],
        'takeoff': {
            'E': round(float(df_gps['E'].iloc[0]),  2),
            'N': round(float(df_gps['N'].iloc[0]),  2),
            'U': round(float(df_gps['U'].iloc[0]),  2),
        },
        'landing': {
            'E': round(float(df_gps['E'].iloc[-1]), 2),
            'N': round(float(df_gps['N'].iloc[-1]), 2),
            'U': round(float(df_gps['U'].iloc[-1]), 2),
        },
    }
    return json.dumps(data)
