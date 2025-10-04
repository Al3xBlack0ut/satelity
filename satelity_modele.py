"""
SQLAlchemy/Pydantic - Modele danych i schematy

System Śledzenia Orbit Satelitarnych - Warstwa Danych
Autor: Aleks Czarnecki

Zawiera:
- Modele bazodanowe (SQLAlchemy)
- Schematy walidacji (Pydantic)
- Dataclasses dla obliczeń orbitalnych
- Stałe fizyczne i konfiguracja
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Tuple, List

from pydantic import BaseModel, Field, validator
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool

# ===========================================================================================
# KONFIGURACJA I STAŁE
# ===========================================================================================

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# Stałe planetarne i orbitalne
PARAMETR_GRAWIT_ZIEMI = 398600.4418  # km³/s² - parametr grawit. standardowy
SREDNICA_BAZOWA_ZIEMI = 6371.0  # km
TOLERANCJA_ZBLIZENIA = 0.01  # km - prog wykrywania zdarzeń
EPSILON_NUMERYCZNY = 1e-9  # dla porównań zmiennoprzecinkowych

# Limity operacyjne systemu
MAX_OBIEKTOW_NA_STRONE = 100
DOMYSLNA_WIELKOSC_STRONY = 10
MINIMALNA_WYSOKOSC_ORBITY = 160.0  # km nad poziomem morza
MAKSYMALNA_WYSOKOSC_ORBITY = 40000.0  # km


# ===========================================================================================
# TYPY WYLICZENIOWE
# ===========================================================================================

class TypObiektu(str, Enum):
    """Klasyfikacja obiektów orbitalnych"""
    AKTYWNY = "active"
    NIEAKTYWNY = "inactive"
    DEZORBITALNY = "deorbited"


class KategoriaPrecyzji(str, Enum):
    """Kategorie dokładności czasowej obliczeń"""
    MILISEKUNDY = "ms"
    SEKUNDY = "s"
    MINUTY = "m"
    GODZINY = "h"
    DNI = "d"


# ===========================================================================================
# DATACLASSES - Struktury danych domenowych
# ===========================================================================================

@dataclass
class WspolrzedneGeodezyjne:
    """Współrzędne geodezyjne obiektu w przestrzeni"""
    szer_geogr: float  # szerokość geograficzna [-90, 90]
    dlug_geogr: float  # długość geograficzna [-180, 180]
    wysokosc_npm: float  # wysokość nad poziomem morza [km]
    
    def do_kartezjanskich(self) -> Tuple[float, float, float]:
        """Konwersja do współrzędnych kartezjańskich ECEF"""
        promien_calkowity = SREDNICA_BAZOWA_ZIEMI + self.wysokosc_npm
        
        lat_rad = math.radians(self.szer_geogr)
        lon_rad = math.radians(self.dlug_geogr)
        
        x_ecef = promien_calkowity * math.cos(lat_rad) * math.cos(lon_rad)
        y_ecef = promien_calkowity * math.cos(lat_rad) * math.sin(lon_rad)
        z_ecef = promien_calkowity * math.sin(lat_rad)
        
        return x_ecef, y_ecef, z_ecef
    
    def dystans_do(self, inne: 'WspolrzedneGeodezyjne') -> float:
        """Oblicza dystans 3D do innych współrzędnych"""
        x1, y1, z1 = self.do_kartezjanskich()
        x2, y2, z2 = inne.do_kartezjanskich()
        
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)


@dataclass
class ParametryOrbitalne:
    """Parametry Keplerian opisujące orbitę"""
    polOs_wielka: float  # semi-major axis [km]
    inklinacja_kat: float  # inclination [stopnie]
    wezl_wstepujacy: float  # RAAN - Right Ascension of Ascending Node [stopnie]
    
    def oblicz_okres_orbitalny(self) -> float:
        """Oblicza okres orbitalny T = 2Pi*pierw2(a3/μ)"""
        return 2 * math.pi * math.sqrt(
            self.polOs_wielka**3 / PARAMETR_GRAWIT_ZIEMI
        )
    
    def oblicz_predkosc_katowa(self) -> float:
        """Oblicza prędkość kątową omega = 2Pi/T"""
        T = self.oblicz_okres_orbitalny()
        return 2 * math.pi / T if T > EPSILON_NUMERYCZNY else 0.0


@dataclass
class ZdarzeniePrzestrz:
    """Zdarzenie w przestrzeni - np. zbliżenie obiektów"""
    obiekt_id_a: int
    obiekt_id_b: int
    moment_czasu: datetime
    lokalizacja: WspolrzedneGeodezyjne
    dystans_min: float = 0.0
    
    def jako_slownik(self) -> Dict[str, Any]:
        """Eksport do słownika"""
        return {
            "satelita1": self.obiekt_id_a,
            "satelita2": self.obiekt_id_b,
            "czas": self.moment_czasu.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pozycja": {
                "szerokosc": self.lokalizacja.szer_geogr,
                "dlugosc": self.lokalizacja.dlug_geogr,
                "wysokosc": self.lokalizacja.wysokosc_npm
            }
        }


# ===========================================================================================
# MODELE BAZY DANYCH - SQLAlchemy
# ===========================================================================================

# Silnik bazy danych
silnik_bd = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

FabrykaSesji = sessionmaker(autocommit=False, autoflush=False, bind=silnik_bd)
BazowyModel = declarative_base()


class ModelOrbityBD(BazowyModel):
    """Model bazy danych dla orbit"""
    __tablename__ = "orb_katalog"
    
    id_rekordu = Column(Integer, primary_key=True, index=True)
    identyfikator_orbity = Column(String(100), unique=True, nullable=False, index=True)
    wysokosc_km = Column(Float, nullable=False)
    kat_inklinacji = Column(Float, nullable=False)
    wezel_wst = Column(Float, nullable=False)
    
    # Relacje
    obiekty_powiazane = relationship("ModelObiektuBD", back_populates="orbita_ref")


class ModelObiektuBD(BazowyModel):
    """Model bazy danych dla obiektów orbitalnych"""
    __tablename__ = "obj_katalog"
    
    id_rekordu = Column(Integer, primary_key=True, index=True)
    nazwa_obiektu = Column(String(100), unique=True, nullable=False, index=True)
    operator_systemu = Column(String(50), nullable=False)
    data_wprowadzenia = Column(DateTime, nullable=False)
    stan_operacyjny = Column(String(20), nullable=False, default="active")
    pozycja_startowa_lon = Column(Float, nullable=False)
    id_orbity_powiazanej = Column(Integer, ForeignKey("orb_katalog.id_rekordu"), nullable=False)
    timestamp_utworzenia = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Relacje
    orbita_ref = relationship("ModelOrbityBD", back_populates="obiekty_powiazane")


# Utworzenie tabel
BazowyModel.metadata.create_all(bind=silnik_bd)


def uzyskaj_sesje_bd():
    """Dependency injection dla sesji bazy danych"""
    sesja = FabrykaSesji()
    try:
        yield sesja
    finally:
        sesja.close()


# ===========================================================================================
# SCHEMATY PYDANTIC - Walidacja danych API
# ===========================================================================================

class SchematOrbitWejscie(BaseModel):
    """Schemat wejściowy dla tworzenia orbity"""
    identyfikator_orbity: str = Field(..., min_length=1, max_length=100, alias="nazwa")
    wysokosc_km: float = Field(..., gt=MINIMALNA_WYSOKOSC_ORBITY, le=MAKSYMALNA_WYSOKOSC_ORBITY, alias="wysokosc")
    kat_inklinacji: float = Field(..., ge=0, le=180, alias="inklinacja")
    wezel_wst: float = Field(..., ge=0, lt=360, alias="wezel")
    
    class Config:
        populate_by_name = True


class SchematOrbitWyjscie(BaseModel):
    """Schemat wyjściowy dla orbity"""
    id: int
    nazwa: str
    wysokosc: float
    inklinacja: float
    wezel: float
    
    class Config:
        """Konfiguracja schematu Pydantic"""
        from_attributes = True
        populate_by_name = True
    
    @classmethod
    def z_modelu(cls, model: ModelOrbityBD):
        """Konwersja z modelu BD"""
        return cls(
            id=model.id_rekordu,
            nazwa=model.identyfikator_orbity,
            wysokosc=model.wysokosc_km,
            inklinacja=model.kat_inklinacji,
            wezel=model.wezel_wst
        )


class SchematObiektuWejscie(BaseModel):
    """Schemat wejściowy dla obiektu orbitalnego"""
    nazwa_obiektu: str = Field(..., min_length=1, max_length=100, alias="nazwa")
    operator_systemu: str = Field(..., min_length=1, max_length=50, alias="operator")
    data_wprowadzenia: datetime = Field(alias="data_startu")
    stan_operacyjny: TypObiektu = Field(default=TypObiektu.AKTYWNY, alias="status")
    pozycja_startowa_lon: float = Field(..., ge=-180, le=180, alias="dlugosc_poczatkowa")
    id_orbity_powiazanej: int = Field(alias="id_orbity")
    
    class Config:
        populate_by_name = True
    
    @validator('data_wprowadzenia', pre=True)
    @classmethod
    def waliduj_date_wprowadzenia(cls, wartosc):
        """Waliduje datę wprowadzenia"""
        import dateutil.parser as dp
        
        if isinstance(wartosc, str):
            dt = dp.isoparse(wartosc)
        elif isinstance(wartosc, datetime):
            dt = wartosc
        else:
            raise ValueError(f"Nieprawidłowy typ daty: {type(wartosc)}")
        
        # Zapewnij UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        
        if dt >= datetime.now(timezone.utc):
            raise ValueError('Data wprowadzenia musi być w przeszłości')
        
        return dt


class SchematObiektuWyjscie(BaseModel):
    """Schemat wyjściowy dla obiektu"""
    id: int
    nazwa: str
    operator: str
    data_startu: str
    status: str
    dlugosc_poczatkowa: float
    id_orbity: int
    
    class Config:
        """Konfiguracja schematu Pydantic"""
        from_attributes = True
    
    @classmethod
    def z_modelu(cls, model: ModelObiektuBD):
        """Konwersja z modelu BD"""
        return cls(
            id=model.id_rekordu,
            nazwa=model.nazwa_obiektu,
            operator=model.operator_systemu,
            data_startu=model.data_wprowadzenia.strftime("%Y-%m-%dT%H:%M:%SZ"),
            status=model.stan_operacyjny,
            dlugosc_poczatkowa=model.pozycja_startowa_lon,
            id_orbity=model.id_orbity_powiazanej
        )


class SchematPozycjiWyjscie(BaseModel):
    """Schemat pozycji obiektu"""
    szerokosc: float
    dlugosc: float
    wysokosc: float


class SchematListyOrbit(BaseModel):
    """Lista orbit z metadanymi paginacji"""
    orbity: List[SchematOrbitWyjscie]
    razem: int
    pomin: int
    limit: int


class SchematListyObiektow(BaseModel):
    """Lista obiektów z metadanymi paginacji"""
    satelity: List[SchematObiektuWyjscie]
    razem: int
    pomin: int
    limit: int


class SchematZdarzeniaKolizji(BaseModel):
    """Schemat zdarzenia zbliżenia satelitów (spotkanie orbit)"""
    satelita1: int = Field(description="ID pierwszego obiektu w zbliżeniu")
    satelita2: int = Field(description="ID drugiego obiektu w zbliżeniu")
    czas: str = Field(description="Moment zbliżenia (ISO-8601)")
    pozycja: SchematPozycjiWyjscie = Field(description="Współrzędne miejsca zbliżenia")


class SchematListyKolizji(BaseModel):
    """Lista wykrytych zbliżeń między satelitami"""
    zblizenia: List[SchematZdarzeniaKolizji] = Field(description="Wykryte zbliżenia orbit")
