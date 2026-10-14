#!/usr/bin/env python3
"""
Asset Simulator - Load Profile Generator
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
Generador de perfiles de consumo eléctrico por tipo de industria.

Genera curvas de carga típicas para diferentes tipos de instalaciones:
- Industrial: Operación continua o por turnos
- Comercial: Horario comercial con picos mediodía
- Residencial: Picos mañana y tarde/noche
- Data Center: Carga base alta constante
- Retail: Picos en horario comercial

Uso:
    generator = LoadGenerator(profile_type='industrial', peak_kw=100)
    profile = generator.generate_profile(date="2026-06-21", interval_minutes=30)
    profile.to_csv("perfil_consumo.csv")
"""
from datetime import datetime, timedelta
from pathlib import Path
import random
from zoneinfo import ZoneInfo

import pandas as pd
import numpy as np


class LoadGenerator:
    """Generador de perfiles de consumo eléctrico."""

    # Perfiles típicos (proporción de potencia pico por hora del día)
    PROFILES = {
        "industrial": {
            "description": "Fábrica con operación continua 24h",
            "hourly_factors": [
                0.75, 0.72, 0.70, 0.68, 0.70, 0.75,  # 00-05: Turno noche reducido
                0.85, 0.92, 0.95, 0.98, 1.00, 0.98,  # 06-11: Turno mañana pico
                0.95, 0.92, 0.95, 0.98, 1.00, 0.98,  # 12-17: Turno tarde pico
                0.92, 0.88, 0.85, 0.82, 0.78, 0.75,  # 18-23: Turno noche
            ],
            "variability": 0.08,  # Variabilidad aleatoria 8%
            "base_load_ratio": 0.60,  # Carga base 60%
        },
        "industrial_shifts": {
            "description": "Fábrica con 2 turnos (mañana y tarde)",
            "hourly_factors": [
                0.15, 0.12, 0.10, 0.10, 0.12, 0.15,  # 00-05: Apagada
                0.30, 0.60, 0.85, 0.95, 1.00, 0.98,  # 06-11: Turno mañana
                0.95, 0.92, 0.95, 1.00, 0.98, 0.90,  # 12-17: Turno tarde
                0.70, 0.50, 0.30, 0.20, 0.18, 0.15,  # 18-23: Apagando
            ],
            "variability": 0.10,
            "base_load_ratio": 0.10,
        },
        "commercial": {
            "description": "Oficinas o centro comercial",
            "hourly_factors": [
                0.15, 0.12, 0.10, 0.10, 0.12, 0.15,  # 00-05: Cerrado
                0.25, 0.40, 0.70, 0.90, 0.95, 1.00,  # 06-11: Apertura y pico
                0.98, 0.95, 0.92, 0.90, 0.88, 0.85,  # 12-17: Tarde
                0.75, 0.60, 0.40, 0.25, 0.20, 0.15,  # 18-23: Cierre
            ],
            "variability": 0.12,
            "base_load_ratio": 0.10,
        },
        "residential": {
            "description": "Vivienda o edificio residencial",
            "hourly_factors": [
                0.25, 0.22, 0.20, 0.20, 0.22, 0.30,  # 00-05: Noche
                0.45, 0.70, 0.85, 0.65, 0.50, 0.45,  # 06-11: Pico mañana
                0.42, 0.40, 0.42, 0.45, 0.55, 0.70,  # 12-17: Tarde
                0.85, 0.95, 1.00, 0.90, 0.65, 0.40,  # 18-23: Pico noche
            ],
            "variability": 0.15,
            "base_load_ratio": 0.20,
        },
        "datacenter": {
            "description": "Centro de datos (carga constante)",
            "hourly_factors": [0.97] * 24,  # Carga casi constante
            "variability": 0.03,
            "base_load_ratio": 0.95,
        },
        "retail": {
            "description": "Tienda retail horario comercial",
            "hourly_factors": [
                0.10, 0.10, 0.10, 0.10, 0.10, 0.12,  # 00-05: Cerrado
                0.15, 0.20, 0.35, 0.60, 0.85, 0.95,  # 06-11: Apertura
                1.00, 0.98, 0.95, 0.92, 0.90, 0.88,  # 12-17: Pico
                0.85, 0.70, 0.45, 0.20, 0.12, 0.10,  # 18-23: Cierre
            ],
            "variability": 0.10,
            "base_load_ratio": 0.10,
        },
    }

    def __init__(
        self,
        profile_type: str = "industrial",
        peak_kw: float = 100.0,
        base_kw: float = None,
        weekend_factor: float = 0.6,
        random_seed: int = None,
    ):
        """
        Inicializar generador de consumo.

        Args:
            profile_type: Tipo de perfil ('industrial', 'industrial_shifts',
                         'commercial', 'residential', 'datacenter', 'retail')
            peak_kw: Potencia pico en kW
            base_kw: Potencia base en kW (None = usar ratio del perfil)
            weekend_factor: Factor de reducción fin de semana (0.6 = 60%)
            random_seed: Semilla para reproducibilidad
        """
        if profile_type not in self.PROFILES:
            raise ValueError(f"Tipo de perfil desconocido: {profile_type}. "
                           f"Válidos: {list(self.PROFILES.keys())}")

        self.profile_type = profile_type
        self.profile_config = self.PROFILES[profile_type]
        self.peak_kw = peak_kw
        self.weekend_factor = weekend_factor

        if base_kw is None:
            self.base_kw = peak_kw * self.profile_config["base_load_ratio"]
        else:
            self.base_kw = base_kw

        if random_seed is not None:
            random.seed(random_seed)
            np.random.seed(random_seed)

    def generate_profile(
        self,
        date: str,
        interval_minutes: int = 15,
    ) -> pd.DataFrame:
        """
        Generar perfil de consumo para un día completo.

        Args:
            date: Fecha en formato 'YYYY-MM-DD'
            interval_minutes: Intervalo entre puntos en minutos

        Returns:
            DataFrame con columnas: timestamp, power_w
        """
        # Parsear fecha
        try:
            date_obj = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Formato de fecha inválido: {date}. Use 'YYYY-MM-DD'")

        # Crear rango de tiempo
        tz = ZoneInfo("UTC")
        start = datetime(date_obj.year, date_obj.month, date_obj.day, 0, 0, tzinfo=tz)
        end = start + timedelta(days=1) - timedelta(minutes=interval_minutes)
        times = pd.date_range(start, end, freq=f"{interval_minutes}min")

        # Obtener factores horarios
        hourly_factors = np.array(self.profile_config["hourly_factors"])
        variability = self.profile_config["variability"]

        # Aplicar reducción de fin de semana
        is_weekend = date_obj.weekday() >= 5  # Sábado=5, Domingo=6
        if is_weekend and self.profile_type not in ["datacenter", "residential"]:
            hourly_factors = hourly_factors * self.weekend_factor

        # Interpolar factores para cada timestamp
        powers = []
        for ts in times:
            hour = ts.hour + ts.minute / 60.0

            # Interpolar entre horas
            hour_idx = int(hour)
            hour_frac = hour - hour_idx
            next_hour_idx = (hour_idx + 1) % 24

            factor = (hourly_factors[hour_idx] * (1 - hour_frac) +
                     hourly_factors[next_hour_idx] * hour_frac)

            # Añadir variabilidad aleatoria
            noise = np.random.normal(0, variability)
            factor = max(0.05, factor + noise)  # Mínimo 5%

            # Calcular potencia
            power_kw = self.base_kw + (self.peak_kw - self.base_kw) * factor
            powers.append(power_kw * 1000)  # Convertir a W

        # Crear DataFrame
        profile = pd.DataFrame({
            "timestamp": times,
            "power_w": powers,
        })

        return profile

    def save_profile(self, profile: pd.DataFrame, filepath: str | Path) -> None:
        """
        Guardar perfil en formato CSV.

        Args:
            profile: DataFrame con el perfil generado
            filepath: Ruta donde guardar el archivo
        """
        filepath = Path(filepath)

        with open(filepath, "w", encoding="utf-8") as f:
            # Escribir metadatos como comentarios
            f.write(f"#source=load_generator\n")
            f.write(f"#profile_type={self.profile_type}\n")
            f.write(f"#description={self.profile_config['description']}\n")
            f.write(f"#peak_kw={self.peak_kw}\n")
            f.write(f"#base_kw={self.base_kw}\n")

            # Escribir datos
            f.write("timestamp,power_w\n")
            for _, row in profile.iterrows():
                ts = row["timestamp"].strftime("%Y-%m-%dT%H:%M:%S")
                power = row["power_w"]
                f.write(f"{ts},{power:.2f}\n")

    def get_stats(self, profile: pd.DataFrame) -> dict:
        """
        Obtener estadísticas del perfil generado.

        Args:
            profile: DataFrame con el perfil generado

        Returns:
            Diccionario con estadísticas
        """
        if len(profile) < 2:
            return {}

        interval_hours = (profile["timestamp"].iloc[1] -
                         profile["timestamp"].iloc[0]).total_seconds() / 3600
        energy_kwh = profile["power_w"].sum() * interval_hours / 1000

        return {
            "profile_type": self.profile_type,
            "description": self.profile_config["description"],
            "peak_power_w": float(profile["power_w"].max()),
            "min_power_w": float(profile["power_w"].min()),
            "avg_power_w": float(profile["power_w"].mean()),
            "daily_energy_kwh": energy_kwh,
            "load_factor": energy_kwh / (self.peak_kw * 24),  # Factor de carga
            "peak_hour": profile.loc[profile["power_w"].idxmax(), "timestamp"].strftime("%H:%M"),
            "min_hour": profile.loc[profile["power_w"].idxmin(), "timestamp"].strftime("%H:%M"),
        }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generar perfil de consumo eléctrico")
    parser.add_argument("--type", choices=list(LoadGenerator.PROFILES.keys()),
                       default="industrial", help="Tipo de perfil")
    parser.add_argument("--date", required=True, help="Fecha YYYY-MM-DD")
    parser.add_argument("--peak-kw", type=float, required=True, help="Potencia pico (kW)")
    parser.add_argument("--output", required=True, help="Archivo CSV de salida")
    parser.add_argument("--interval", type=int, default=15, help="Intervalo en minutos (def: 15)")
    parser.add_argument("--seed", type=int, default=None, help="Semilla aleatoria")

    args = parser.parse_args()

    print(f"Generando perfil de consumo para {args.date}...")
    print(f"Tipo: {args.type}")
    print(f"Potencia pico: {args.peak_kw} kW")

    generator = LoadGenerator(args.type, args.peak_kw, random_seed=args.seed)
    profile = generator.generate_profile(args.date, args.interval)
    generator.save_profile(profile, args.output)

    stats = generator.get_stats(profile)
    print(f"\n✓ Perfil generado: {args.output}")
    print(f"  Descripción: {stats['description']}")
    print(f"  Potencia pico: {stats['peak_power_w']/1000:.2f} kW a las {stats['peak_hour']}")
    print(f"  Potencia mínima: {stats['min_power_w']/1000:.2f} kW a las {stats['min_hour']}")
    print(f"  Potencia media: {stats['avg_power_w']/1000:.2f} kW")
    print(f"  Energía diaria: {stats['daily_energy_kwh']:.2f} kWh")
    print(f"  Factor de carga: {stats['load_factor']:.2%}")
