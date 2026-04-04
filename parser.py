import pandas as pd
from pymavlink import mavutil

class parser:
    @staticmethod
    def gpsData(file_path):
        mlog = mavutil.mavlink_connection(file_path)
        gps_records = []

        while True:
            msg = mlog.recv_match(type='GPS', blocking=False)
            if msg is None:
                break

            # Фільтр: тільки 3D Fix (Status >= 3) і достатня кількість супутників
            if msg.Status < 3 or msg.NSats < 6:
                continue

            gps_records.append({
                'timestamp': msg._timestamp,
                'lat': msg.Lat,
                'lon': msg.Lng,
                'alt': msg.Alt,
                'spd': msg.Spd,
                'status': msg.Status,   # опціонально, для дебагу
                'nsats': msg.NSats,     # опціонально, для дебагу
            })
        df_gps = pd.DataFrame(gps_records)
        return df_gps
    @staticmethod
    def imuData(file_path):
        mlog = mavutil.mavlink_connection(file_path)
        imu_records = []

        while True:
            msg = mlog.recv_match(type='IMU', blocking=False)
            if msg is None:
                break
            imu_records.append({
                'timestamp': msg._timestamp,
                'AccX': msg.AccX, #прискорення по X (м/с²)
                'AccY': msg.AccY, #прискорення по Y (м/с²)  
                'AccZ': msg.AccZ, #прискорення по Z (м/с²)
            })
        df_imu = pd.DataFrame(imu_records)
        df_imu['dt'] = df_imu['timestamp'].diff().fillna(0)
        return df_imu