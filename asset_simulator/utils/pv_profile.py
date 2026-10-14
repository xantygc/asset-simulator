"""
Asset Simulator - PV Profile Module
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
Módulo para cargar y usar perfiles de producción solar fotovoltaica.

El perfil contiene potencia de salida esperada en función del tiempo,
típicamente generado a partir de datos de irradiancia solar y parámetros
del panel (ubicación, inclinación, orientación, kWp).

Formato CSV esperado:
- Primera línea: cabeceras de metadatos (#key=value)
- Segunda línea: cabeceras de columnas (timestamp,power_w)
- Líneas siguientes: datos (ISO timestamp, potencia en W)

Ejemplo:
    #source=pvlib
    #kwp=6.0
    #lat=39.47
    #lon=-6.37
    timestamp,power_w
    2026-06-21T07:00:00,0
    2026-06-21T08:00:00,1250
    2026-06-21T09:00:00,2800
    ...

Uso:
    profile = PVProfile.from_csv("solar_profile.csv")
    power_w = profile.power_w(datetime.now(timezone.utc))
"""
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class PVError(Exception):
    """Excepción para errores relacionados con perfiles PV."""
    pass


@dataclass
class PVDataPoint:
    """Punto de datos del perfil: mes, día, hora, minuto, segundo, potencia."""
    month: int
    day: int
    hour: int
    minute: int
    second: int
    power_w: float

    @classmethod
    def from_datetime(cls, dt: datetime, power_w: float):
        """Crear punto desde datetime."""
        return cls(
            month=dt.month,
            day=dt.day,
            hour=dt.hour,
            minute=dt.minute,
            second=dt.second,
            power_w=power_w
        )

    def to_seconds_in_year(self) -> float:
        """
        Convertir a segundos desde inicio del año (aproximado).

        Asume meses de 30 días para simplificar, lo que permite
        reutilizar perfiles entre años diferentes.
        """
        return (
            (self.month - 1) * 30 * 86400 +
            (self.day - 1) * 86400 +
            self.hour * 3600 +
            self.minute * 60 +
            self.second
        )


class PVProfile:
    """
    Perfil de producción solar fotovoltaica.

    Carga datos de un CSV y proporciona interpolación lineal
    para obtener potencia en cualquier instante.

    Los datos se reutilizan para cualquier año (solo importan
    mes, día y hora), permitiendo simulaciones multi-año con
    el mismo patrón solar.
    """

    def __init__(self, data_points: list[PVDataPoint], metadata: dict | None = None):
        """
        Inicializar perfil.

        Args:
            data_points: Lista de puntos de datos ordenados por tiempo
            metadata: Diccionario con metadatos del perfil
        """
        if not data_points:
            raise PVError("El perfil debe contener al menos un punto de datos")

        self.data_points = sorted(data_points, key=lambda p: p.to_seconds_in_year())
        self.meta = metadata or {}

        # Verificar que los puntos estén ordenados
        for i in range(len(self.data_points) - 1):
            if self.data_points[i].to_seconds_in_year() >= self.data_points[i + 1].to_seconds_in_year():
                raise PVError("Los puntos del perfil deben estar ordenados cronológicamente")

    @classmethod
    def from_csv(cls, filepath: str | Path):
        """
        Cargar perfil desde archivo CSV.

        Args:
            filepath: Ruta al archivo CSV

        Returns:
            Instancia de PVProfile

        Raises:
            PVError: Si el archivo no existe o tiene formato inválido
        """
        filepath = Path(filepath)
        if not filepath.exists():
            raise PVError(f"Archivo no encontrado: {filepath}")

        metadata = {}
        data_points = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # Leer metadatos (líneas que empiezan con #)
                lines = []
                for line in f:
                    line = line.strip()
                    if line.startswith('#'):
                        # Parsear metadatos: #key=value
                        if '=' in line:
                            key, value = line[1:].split('=', 1)
                            metadata[key.strip()] = value.strip()
                    else:
                        lines.append(line)

                # Parsear CSV desde las líneas restantes
                if not lines:
                    raise PVError("No se encontraron datos en el archivo")

                # Primera línea no-comentario debe ser la cabecera
                reader = csv.DictReader(lines)

                for row_num, row in enumerate(reader, start=2):
                    try:
                        # Parsear timestamp (formato ISO)
                        timestamp_str = row.get('timestamp', '').strip()
                        if not timestamp_str:
                            raise ValueError("Falta columna 'timestamp'")

                        # Soportar varios formatos de timestamp
                        for fmt in [
                            "%Y-%m-%dT%H:%M:%S",
                            "%Y-%m-%d %H:%M:%S",
                            "%Y-%m-%dT%H:%M:%S%z",
                            "%Y-%m-%d %H:%M:%S%z",
                        ]:
                            try:
                                dt = datetime.strptime(timestamp_str, fmt)
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                break
                            except ValueError:
                                continue
                        else:
                            raise ValueError(f"Formato de timestamp no reconocido: {timestamp_str}")

                        # Parsear potencia
                        power_str = row.get('power_w', '').strip()
                        if not power_str:
                            raise ValueError("Falta columna 'power_w'")

                        power_w = float(power_str)
                        if power_w < 0:
                            raise ValueError(f"Potencia negativa no permitida: {power_w}")

                        data_points.append(PVDataPoint.from_datetime(dt, power_w))

                    except (ValueError, KeyError) as e:
                        raise PVError(f"Error en línea {row_num}: {e}")

                if not data_points:
                    raise PVError("No se encontraron puntos de datos válidos")

        except (OSError, UnicodeDecodeError) as e:
            raise PVError(f"Error al leer archivo: {e}")

        return cls(data_points, metadata)

    def power_w(self, timestamp: datetime) -> float:
        """
        Obtener potencia interpolada para un timestamp dado.

        Usa interpolación lineal entre puntos adyacentes.
        Los datos se reutilizan para cualquier año (solo mes, día, hora).

        Args:
            timestamp: Momento para el cual obtener la potencia

        Returns:
            Potencia en W (float)
        """
        # Convertir timestamp a punto comparable (sin año)
        target_point = PVDataPoint.from_datetime(timestamp, 0.0)
        target_seconds = target_point.to_seconds_in_year()

        # Buscar puntos adyacentes para interpolar
        # Si está fuera del rango, devolver el valor del extremo más cercano

        if target_seconds <= self.data_points[0].to_seconds_in_year():
            return self.data_points[0].power_w

        if target_seconds >= self.data_points[-1].to_seconds_in_year():
            return self.data_points[-1].power_w

        # Buscar puntos entre los que interpolar
        for i in range(len(self.data_points) - 1):
            p1 = self.data_points[i]
            p2 = self.data_points[i + 1]

            t1 = p1.to_seconds_in_year()
            t2 = p2.to_seconds_in_year()

            if t1 <= target_seconds <= t2:
                # Interpolación lineal
                if t2 == t1:
                    return p1.power_w

                ratio = (target_seconds - t1) / (t2 - t1)
                return p1.power_w + ratio * (p2.power_w - p1.power_w)

        # No debería llegar aquí, pero por seguridad
        return 0.0

    def __repr__(self) -> str:
        kwp = self.meta.get('kwp', '?')
        source = self.meta.get('source', '?')
        n_points = len(self.data_points)
        return f"PVProfile(source={source}, kwp={kwp}, points={n_points})"


# Función auxiliar para generar perfiles de prueba
def generate_sample_profile(filepath: str | Path, kwp: float = 6.0, date_str: str = "2026-06-21") -> None:
    """
    Generar un perfil de ejemplo para testing.

    Crea un perfil sintético con una curva sinusoidal simple
    que simula un día soleado.

    Args:
        filepath: Ruta donde guardar el CSV
        kwp: Potencia pico en kW
        date_str: Fecha de ejemplo (formato YYYY-MM-DD)
    """
    import math

    filepath = Path(filepath)

    with open(filepath, 'w', encoding='utf-8') as f:
        # Escribir metadatos
        f.write(f"#source=synthetic\n")
        f.write(f"#kwp={kwp}\n")
        f.write(f"#date={date_str}\n")
        f.write("timestamp,power_w\n")

        # Generar datos para un día (de 6:00 a 20:00)
        for hour in range(6, 21):
            for minute in [0, 30]:
                timestamp = f"{date_str}T{hour:02d}:{minute:02d}:00"

                # Calcular potencia con curva sinusoidal
                # Máximo al mediodía (12:00)
                t = hour + minute / 60.0
                if 6 <= t <= 20:
                    # Sinusoide centrada en 13:00 (hora solar)
                    angle = (t - 6) / 14 * math.pi
                    power_w = kwp * 1000 * math.sin(angle) * 0.85  # 85% eficiencia
                else:
                    power_w = 0

                f.write(f"{timestamp},{power_w:.1f}\n")


if __name__ == "__main__":
    # Demo
    import tempfile
    from datetime import timedelta

    # Generar perfil de ejemplo
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tf:
        generate_sample_profile(tf.name, kwp=6.0)

        # Cargar y probar
        profile = PVProfile.from_csv(tf.name)
        print(f"Perfil cargado: {profile}")
        print(f"Metadatos: {profile.meta}")

        # Probar interpolación
        base_time = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
        for i in range(5):
            dt = base_time + timedelta(hours=i)
            power = profile.power_w(dt)
            print(f"{dt.strftime('%H:%M')}: {power:.1f} W")
