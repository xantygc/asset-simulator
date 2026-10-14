#!/usr/bin/env python3
"""
Asset Simulator - Solar Profile Generator
Copyright (C) 2026 Santiago González

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
"""
Generador de perfiles de producción solar usando pvlib-python.

Calcula la producción esperada de un sistema fotovoltaico basándose en:
- Ubicación geográfica (lat/lon)
- Fecha y hora
- Configuración del sistema (kWp, inclinación, orientación)
- Modelo de irradiancia clearsky (cielo despejado)

Uso:
    generator = SolarGenerator(latitude=39.47, longitude=-6.37, kwp=6.0)
    profile = generator.generate_profile(date="2026-06-21", interval_minutes=30)
    profile.to_csv("perfil_solar.csv")
"""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pvlib
from pvlib import location, pvsystem, modelchain


class SolarGenerator:
    """Generador de perfiles de producción fotovoltaica usando pvlib."""

    def __init__(
        self,
        latitude: float,
        longitude: float,
        kwp: float,
        tilt: float = None,
        azimuth: float = 180.0,
        altitude: float = 100.0,
        timezone: str = "UTC",
        losses: float = 0.14,
    ):
        """
        Inicializar generador solar.

        Args:
            latitude: Latitud en grados (-90 a 90)
            longitude: Longitud en grados (-180 a 180)
            kwp: Potencia pico instalada en kWp
            tilt: Inclinación de paneles en grados (None = latitud óptima)
            azimuth: Orientación en grados (180=sur, 90=este, 270=oeste)
            altitude: Altitud sobre nivel del mar en metros
            timezone: Zona horaria (ej: 'Europe/Madrid', 'UTC')
            losses: Pérdidas del sistema (0.14 = 14%)
        """
        self.latitude = latitude
        self.longitude = longitude
        self.kwp = kwp
        self.tilt = tilt if tilt is not None else abs(latitude)  # Óptimo ≈ latitud
        self.azimuth = azimuth
        self.altitude = altitude
        self.timezone = timezone
        self.losses = losses

        # Crear ubicación pvlib
        self.location = location.Location(
            latitude=self.latitude,
            longitude=self.longitude,
            tz=self.timezone,
            altitude=self.altitude,
            name=f"Solar_{latitude:.2f}_{longitude:.2f}",
        )

        # Parámetros simplificados del sistema
        self.pdc0 = self.kwp * 1000  # Potencia DC nominal en W
        self.gamma_pdc = -0.004  # Coef. temperatura potencia (%/°C)
        self.eta_inv = 0.96  # Eficiencia del inversor

    def generate_profile(
        self,
        date: str,
        interval_minutes: int = 15,
        clearsky_model: str = "ineichen",
    ) -> pd.DataFrame:
        """
        Generar perfil de producción para un día completo.

        Args:
            date: Fecha en formato 'YYYY-MM-DD'
            interval_minutes: Intervalo entre puntos en minutos
            clearsky_model: Modelo de cielo despejado ('ineichen', 'haurwitz', 'simplified_solis')

        Returns:
            DataFrame con columnas: timestamp, power_w, ghi, dni, dhi
        """
        # Parsear fecha
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Formato de fecha inválido: {date}. Use 'YYYY-MM-DD'")

        # Crear rango de tiempo para el día completo
        tz = ZoneInfo(self.timezone)
        start = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, tzinfo=tz)
        end = start + timedelta(days=1) - timedelta(minutes=interval_minutes)
        times = pd.date_range(start, end, freq=f"{interval_minutes}min")

        # Calcular posición solar
        solar_position = self.location.get_solarposition(times)

        # Calcular irradiancia clearsky
        clearsky = self.location.get_clearsky(times, model=clearsky_model)

        # Calcular AOI (ángulo de incidencia)
        aoi = pvlib.irradiance.aoi(
            self.tilt,
            self.azimuth,
            solar_position["apparent_zenith"],
            solar_position["azimuth"],
        )

        # Calcular irradiancia en el plano inclinado (POA)
        poa_irradiance = pvlib.irradiance.get_total_irradiance(
            self.tilt,
            self.azimuth,
            solar_position["apparent_zenith"],
            solar_position["azimuth"],
            clearsky["dni"],
            clearsky["ghi"],
            clearsky["dhi"],
            model="isotropic",
        )

        # Calcular temperatura de celda (modelo simplificado Faiman)
        temp_cell = pvlib.temperature.faiman(
            poa_irradiance["poa_global"],
            25,  # Temperatura ambiente estimada en °C
            wind_speed=1.0,  # Velocidad del viento en m/s
        )

        # Calcular potencia DC del módulo
        pdc = pvlib.pvsystem.pvwatts_dc(
            poa_irradiance["poa_global"],
            temp_cell,
            self.pdc0,
            self.gamma_pdc,
        )

        # Calcular potencia AC del inversor
        pac = pvlib.inverter.pvwatts(
            pdc,
            self.pdc0 / self.eta_inv,
            self.eta_inv,
        )

        # Aplicar pérdidas del sistema
        pac_with_losses = pac * (1 - self.losses)

        # Limitar valores negativos a 0 (noche)
        pac_with_losses = pac_with_losses.clip(lower=0)

        # Crear DataFrame con resultados
        profile = pd.DataFrame(
            {
                "timestamp": times,
                "power_w": pac_with_losses.values,
                "ghi": clearsky["ghi"].values,
                "dni": clearsky["dni"].values,
                "dhi": clearsky["dhi"].values,
                "poa": poa_irradiance["poa_global"].values,
                "temp_cell": temp_cell.values,
            }
        )

        return profile

    def save_profile(self, profile: pd.DataFrame, filepath: str | Path) -> None:
        """
        Guardar perfil en formato CSV compatible con PVProfile.

        Args:
            profile: DataFrame con el perfil generado
            filepath: Ruta donde guardar el archivo
        """
        filepath = Path(filepath)

        with open(filepath, "w", encoding="utf-8") as f:
            # Escribir metadatos como comentarios
            f.write(f"#source=pvlib\n")
            f.write(f"#kwp={self.kwp}\n")
            f.write(f"#lat={self.latitude}\n")
            f.write(f"#lon={self.longitude}\n")
            f.write(f"#tilt={self.tilt}\n")
            f.write(f"#azimuth={self.azimuth}\n")
            f.write(f"#altitude={self.altitude}\n")
            f.write(f"#timezone={self.timezone}\n")
            f.write(f"#losses={self.losses}\n")

            # Escribir datos (solo timestamp y power_w para compatibilidad con PVProfile)
            f.write("timestamp,power_w\n")
            for _, row in profile.iterrows():
                ts = row["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
                power = row["power_w"]
                f.write(f"{ts},{power:.2f}\n")

    def get_daily_energy(self, profile: pd.DataFrame) -> float:
        """
        Calcular energía total generada en el día (kWh).

        Args:
            profile: DataFrame con el perfil generado

        Returns:
            Energía en kWh
        """
        # Calcular intervalo en horas
        if len(profile) < 2:
            return 0.0

        interval_hours = (profile["timestamp"].iloc[1] - profile["timestamp"].iloc[0]).total_seconds() / 3600

        # Integrar potencia
        energy_kwh = profile["power_w"].sum() * interval_hours / 1000

        return energy_kwh

    def get_stats(self, profile: pd.DataFrame) -> dict:
        """
        Obtener estadísticas del perfil generado.

        Args:
            profile: DataFrame con el perfil generado

        Returns:
            Diccionario con estadísticas
        """
        return {
            "peak_power_w": float(profile["power_w"].max()),
            "daily_energy_kwh": self.get_daily_energy(profile),
            "capacity_factor": self.get_daily_energy(profile) / (self.kwp * 24),
            "sunrise": profile[profile["power_w"] > 10]["timestamp"].min().strftime("%H:%M"),
            "sunset": profile[profile["power_w"] > 10]["timestamp"].max().strftime("%H:%M"),
            "peak_hour": profile.loc[profile["power_w"].idxmax(), "timestamp"].strftime("%H:%M"),
        }


def generate_profile_quick(
    latitude: float,
    longitude: float,
    date: str,
    kwp: float,
    tilt: float = None,
    azimuth: float = 180.0,
    output_file: str = None,
) -> pd.DataFrame:
    """
    Función rápida para generar un perfil solar.

    Args:
        latitude: Latitud en grados
        longitude: Longitud en grados
        date: Fecha 'YYYY-MM-DD'
        kwp: Potencia pico en kWp
        tilt: Inclinación (None = óptima)
        azimuth: Orientación (180 = sur)
        output_file: Opcional, archivo CSV de salida

    Returns:
        DataFrame con el perfil
    """
    generator = SolarGenerator(latitude, longitude, kwp, tilt, azimuth)
    profile = generator.generate_profile(date)

    if output_file:
        generator.save_profile(profile, output_file)

    return profile


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generar perfil solar con pvlib")
    parser.add_argument("--lat", type=float, required=True, help="Latitud")
    parser.add_argument("--lon", type=float, required=True, help="Longitud")
    parser.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    parser.add_argument("--kwp", type=float, required=True, help="Potencia pico (kWp)")
    parser.add_argument("--tilt", type=float, default=None, help="Inclinación (def: latitud)")
    parser.add_argument("--azimuth", type=float, default=180, help="Orientación (def: 180=sur)")
    parser.add_argument("--output", required=True, help="Archivo CSV de salida")
    parser.add_argument("--interval", type=int, default=15, help="Intervalo en minutos (def: 15)")

    args = parser.parse_args()

    print(f"Generando perfil solar para {args.date}...")
    print(f"Ubicación: {args.lat}°N, {args.lon}°E")
    print(f"Sistema: {args.kwp} kWp, inclinación {args.tilt}°, azimut {args.azimuth}°")

    generator = SolarGenerator(args.lat, args.lon, args.kwp, args.tilt, args.azimuth)
    profile = generator.generate_profile(args.date, args.interval)
    generator.save_profile(profile, args.output)

    stats = generator.get_stats(profile)
    print(f"\n✓ Perfil generado: {args.output}")
    print(f"  Potencia pico: {stats['peak_power_w']:.0f} W")
    print(f"  Energía diaria: {stats['daily_energy_kwh']:.2f} kWh")
    print(f"  Factor de capacidad: {stats['capacity_factor']:.2%}")
    print(f"  Amanecer: {stats['sunrise']}, Atardecer: {stats['sunset']}")
    print(f"  Hora pico: {stats['peak_hour']}")
