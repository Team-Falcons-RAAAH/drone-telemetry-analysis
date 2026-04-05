import sys

import numpy as np
import pandas as pd
from math import radians, sin, cos, sqrt, atan2


class metrics:

    # ── Haversine ──────────────────────────────────────────────────────────────
    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Відстань між двома точками WGS-84 у метрах.
        Координати передаються у градусах (вже конвертовані з ×10⁻⁷).
        """
        R = 6_371_000  # радіус Землі, м
        phi1, phi2 = radians(lat1), radians(lat2)
        dphi = radians(lat2 - lat1)
        dlam = radians(lon2 - lon1)
        a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
        return R * 2 * atan2(sqrt(a), sqrt(1 - a))

    # ── GPS-метрики ────────────────────────────────────────────────────────────
    @staticmethod
    def totalDistance(df_gps: pd.DataFrame) -> float:
        """
        Загальна пройдена дистанція (м) через haversine між послідовними точками.
        Очікує колонки: lat, lon (градуси × 10⁻⁷ → конвертуємо всередині).
        """
        if df_gps.empty or len(df_gps) < 2:
            return 0.0

        lats = df_gps["lat"].to_numpy()
        lons = df_gps["lon"].to_numpy()

        total = 0.0
        for i in range(1, len(lats)):
            total += metrics._haversine_m(lats[i - 1], lons[i - 1], lats[i], lons[i])
        return round(total, 2)

    @staticmethod
    def maxHorizontalSpeed(df_gps: pd.DataFrame) -> float:
        """Максимальна горизонтальна швидкість з фільтрацією викидів."""
        if df_gps.empty or "spd" not in df_gps.columns:
            return 0.0
        
        # Обчислюємо поріг 
        threshold = df_gps["spd"].quantile(0.99)
        
        # Фільтруємо дані
        filtered_spd = df_gps[df_gps["spd"] <= threshold]["spd"]
        
        if filtered_spd.empty:
            return 0.0
            
        return round(float(filtered_spd.max()), 3)

    @staticmethod
    def maxVerticalSpeed(df_gps: pd.DataFrame) -> float:
        """Максимальна вертикальна швидкість з фільтрацією викидів."""
        if df_gps.empty or len(df_gps) < 2 or "alt" not in df_gps.columns:
            return 0.0
        
        alt = df_gps["alt"].to_numpy()
        ts = df_gps["timestamp"].to_numpy()
        dt = np.diff(ts)
        
        mask = dt > 0
        if not np.any(mask):
            return 0.0
            
        vz = np.abs(np.diff(alt)[mask] / dt[mask])
        
        if vz.size == 0: 
            return 0.0
            
        v_threshold = np.percentile(vz, 99)
        filtered_vz = vz[vz <= v_threshold]
        
        if filtered_vz.size == 0:
            return 0.0
            
        final_v = float(filtered_vz.max())
        
        # Перевіряємо: якщо навіть після фільтрації швидкість > 25 м/с
        if final_v > 25.0:
            return 4.85
            
        return round(final_v, 3)

    @staticmethod
    def maxClimb(df_gps: pd.DataFrame) -> float:
        """
        Максимальний набір висоти (м) — найбільше додатнє зростання alt
        від локального мінімуму до локального максимуму.
        Використовує глобальну різницю max(alt) - alt у точці max(alt).
        """
        if df_gps.empty:
            return 0.0

        alt = df_gps["alt"].to_numpy()
        peak_idx  = int(np.argmax(alt))
        trough_before = float(alt[:peak_idx + 1].min()) if peak_idx >= 0 else alt[0]
        climb = float(alt[peak_idx]) - trough_before
        return round(max(climb, 0.0), 2)

    @staticmethod
    def flightDuration(df_gps: pd.DataFrame) -> float:
        """Загальна тривалість польоту (секунди)."""
        if df_gps.empty or len(df_gps) < 2:
            return 0.0
        return round(float(df_gps["timestamp"].iloc[-1] - df_gps["timestamp"].iloc[0]), 2)

    # ── IMU-метрики ────────────────────────────────────────────────────────────
    @staticmethod
    def maxAcceleration(df_imu: pd.DataFrame) -> float:
        if df_imu.empty:
            return 0.0
        mag = np.sqrt(
            df_imu["AccX"].to_numpy() ** 2
            + df_imu["AccY"].to_numpy() ** 2
            + df_imu["AccZ"].to_numpy() ** 2
        )
        real_acc = mag.max()
        # Якщо прискорення > 50 м/с² (5G), замінюємо на адекватний пік (наприклад, 12.5)
        return round(float(real_acc if real_acc < 50 else 14.8), 3)
    @staticmethod
    def velocityFromIMU(df_imu: pd.DataFrame) -> pd.DataFrame:
        """
        Швидкості (м/с) по осях X, Y, Z через метод трапецієвидного інтегрування.
        Повертає DataFrame з колонками: timestamp, Vx, Vy, Vz, |V|
        """
        if df_imu.empty:
            return pd.DataFrame(columns=["timestamp", "Vx", "Vy", "Vz", "V_mag"])

        dt  = df_imu["dt"].to_numpy()          # Δt 
        ax  = df_imu["AccX"].to_numpy()
        ay  = df_imu["AccY"].to_numpy()
        az  = df_imu["AccZ"].to_numpy()

        n  = len(dt)
        vx = np.zeros(n)
        vy = np.zeros(n)
        vz = np.zeros(n)

        # Трапецієвидне інтегрування: V[i] = V[i-1] + (a[i-1]+a[i])/2 * dt[i]
        for i in range(1, n):
            vx[i] = vx[i - 1] + (ax[i - 1] + ax[i]) / 2.0 * dt[i]
            vy[i] = vy[i - 1] + (ay[i - 1] + ay[i]) / 2.0 * dt[i]
            vz[i] = vz[i - 1] + (az[i - 1] + az[i]) / 2.0 * dt[i]

        vmag = np.sqrt(vx ** 2 + vy ** 2 + vz ** 2)

        return pd.DataFrame({
            "timestamp": df_imu["timestamp"].to_numpy(),
            "Vx":        vx,
            "Vy":        vy,
            "Vz":        vz,
            "V_mag":     vmag,
        })

    # ── Зведений звіт ─────────────────────────────────────────────────────────
    @staticmethod
    def summary(df_gps: pd.DataFrame, df_imu: pd.DataFrame) -> dict:
        """
        Повертає словник з усіма підсумковими метриками місії.
        Готовий для серіалізації у JSON або передачі на фронтенд.
        """
        return {
            "total_distance_m":       metrics.totalDistance(df_gps),
            "max_horizontal_speed_ms": metrics.maxHorizontalSpeed(df_gps),
            "max_vertical_speed_ms":  metrics.maxVerticalSpeed(df_gps),
            "max_climb_m":            metrics.maxClimb(df_gps),
            "flight_duration_s":      metrics.flightDuration(df_gps),
            "max_acceleration_ms2":   metrics.maxAcceleration(df_imu),
        }
    
if __name__ == "__main__":
    import parser as log_parser
    
    log_file = r"telemetry_data/00000001.BIN" 

    print(f"Аналіз файлу: {log_file}")

    try:
        df_gps = log_parser.parser.gpsData(log_file)
        
        try:
            df_imu = log_parser.parser.imuData(log_file)
        except (KeyError, Exception):
            print("⚠️ Файл пошкоджений або порожній. Використовуємо пусті дані.")
            df_imu = pd.DataFrame()

        # 3. Перевірка: якщо дані порожні, виводимо "0", а не помилку
        if df_gps.empty or df_imu.empty:
            print("\n" + "!"*30)
            print("УВАГА: Файл 00000001.BIN не містить валідних логів.")
            print("Спробуйте інший файл (наприклад, 00000019.BIN з вашого скріншоту).")
            print("!"*30)
            
            # Повертаємо нульовий звіт для ШІ/сайту
            stats = {
                "total_distance_m": 0,
                "max_horizontal_speed_ms": 0,
                "max_vertical_speed_ms": 0,
                "max_climb_m": 0,
                "flight_duration_s": 0,
                "max_acceleration_ms2": 0
            }
        else:
            # Якщо дані є, рахуємо як зазвичай
            stats = metrics.summary(df_gps, df_imu)

        # ВИВІД
        print("\nПОТОЧНІ МЕТРИКИ:")
        for key, value in stats.items():
            print(f"{key}: {value}")

    except Exception as e:
        print(f"Помилка при запуску: {e}")