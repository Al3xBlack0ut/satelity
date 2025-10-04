"""
Propagatory/Walidatory - Logika biznesowa i obliczenia

System Śledzenia Orbit Satelitarnych - Warstwa Serwisów
Autor: Aleks Czarnecki

Zawiera:
- Propagatory orbitalne (Keplerowski)
- Walidatory danych (ISO8601, zakres)
- Algorytmy obliczeń pozycji satelitów
- Wzorce: Strategy Pattern, Service Layer
"""

import logging
import math
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

import dateutil.parser
from sqlalchemy.orm import Session

from satelity_modele import (
    WspolrzedneGeodezyjne,
    ParametryOrbitalne,
    ZdarzeniePrzestrz,
    ModelOrbityBD,
    ModelObiektuBD,
    KategoriaPrecyzji,
    SREDNICA_BAZOWA_ZIEMI,
    TOLERANCJA_ZBLIZENIA,
    EPSILON_NUMERYCZNY
)

log = logging.getLogger(__name__)


# ===========================================================================================
# WYJĄTKI DOMENOWE
# ===========================================================================================

class BladWalidacjiCzasu(ValueError):
    """Błąd walidacji formatu czasowego"""


class BladObliczenOrbitych(RuntimeError):
    """Błąd w obliczeniach orbitalnych"""


class BladZasobuNieznaleziony(RuntimeError):
    """Zasób nie został znaleziony w bazie danych"""


# ===========================================================================================
# KLASY ABSTRAKCYJNE - Wzorzec Strategy
# ===========================================================================================

class PropagatorOrbity(ABC):
    """Abstrakcyjna klasa bazowa dla propagatorów orbit"""
    
    @abstractmethod
    def oblicz_pozycje(
        self,
        param_orb: ParametryOrbitalne,
        moment: datetime,
        dlugosc_pocz: float,
        data_startowa: datetime
    ) -> WspolrzedneGeodezyjne:
        """Oblicza pozycję obiektu w danym momencie"""


class WalidatorCzasowy(ABC):
    """Abstrakcyjna klasa bazowa dla walidatorów czasowych"""
    
    @abstractmethod
    def waliduj_znacznik(self, znacznik_czasowy: str) -> datetime:
        """Waliduje i parsuje znacznik czasowy"""


# ===========================================================================================
# IMPLEMENTACJE PROPAGATORÓW
# ===========================================================================================

class PropagatorKeplerowski(PropagatorOrbity):
    """Propagator orbity używający uproszczonego modelu Keplerianskiego"""
    
    def __init__(self):
        self.nazwa = "Keplerian Circular Propagator"
        log.debug(f"Zainicjalizowano propagator: {self.nazwa}")
    
    def propaguj_pozycje(
        self,
        parametry: ParametryOrbitalne,
        czas_od_epoki: float,
        dlug_poczatkowa: float
    ) -> WspolrzedneGeodezyjne:
        """
        Propagacja pozycji metodą Keplerianowską
        
        Args:
            parametry: Parametry orbitalne obiektu
            czas_od_epoki: Czas od epoki początkowej [sekundy]
            dlug_poczatkowa: Długość geograficzna początkowa [stopnie]
        
        Returns:
            Współrzędne geodezyjne w danym momencie
        """
        # Konwersja kątów na radiany
        inklinacja_rad = math.radians(parametry.inklinacja_kat)
        raan_rad = math.radians(parametry.wezl_wstepujacy)
        dlug_pocz_rad = math.radians(dlug_poczatkowa)
        
        # Oblicz anomalię prawdziwą
        omega_kat = parametry.oblicz_predkosc_katowa()
        anomalia_prawdziwa = (omega_kat * czas_od_epoki + dlug_pocz_rad) % (2 * math.pi)
        
        # Oblicz współrzędne w płaszczyźnie orbitalnej
        szer_orb = math.asin(math.sin(inklinacja_rad) * math.sin(anomalia_prawdziwa))
        
        # Oblicz długość geograficzną
        dlug_wsp = math.atan2(
            math.cos(inklinacja_rad) * math.sin(anomalia_prawdziwa),
            math.cos(anomalia_prawdziwa)
        ) + raan_rad
        
        # Konwersja z powrotem na stopnie i normalizacja
        szer_geo = math.degrees(szer_orb)
        dlug_geo = self._normalizuj_dlugosc(math.degrees(dlug_wsp))
        
        # Wysokość to promień orbity minus promień Ziemi
        wysokosc = parametry.polOs_wielka - SREDNICA_BAZOWA_ZIEMI
        
        return WspolrzedneGeodezyjne(
            szer_geogr=szer_geo,
            dlug_geogr=dlug_geo,
            wysokosc_npm=wysokosc
        )
    
    @staticmethod
    def _normalizuj_dlugosc(dlugosc_deg: float) -> float:
        """Normalizuje długość geograficzną do przedziału [-180, 180]"""
        normalized = ((dlugosc_deg + 180) % 360) - 180
        return normalized
    
    # Implementacja metody abstrakcyjnej
    def oblicz_pozycje(
        self,
        param_orb: ParametryOrbitalne,
        moment: datetime,
        dlugosc_pocz: float,
        data_startowa: datetime
    ) -> WspolrzedneGeodezyjne:
        """Oblicza pozycję obiektu w danym momencie"""
        
        if not isinstance(moment, datetime) or not isinstance(data_startowa, datetime):
            raise BladObliczenOrbitych("Niepoprawny format daty")
        
        # Zapewnienie timezone-aware datetime
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        if data_startowa.tzinfo is None:
            data_startowa = data_startowa.replace(tzinfo=timezone.utc)
        
        # Czas który upłynął od startu [sekundy]
        delta_t = (moment - data_startowa).total_seconds()
        
        if delta_t < 0:
            raise BladObliczenOrbitych(
                "Moment obliczeniowy nie może być wcześniejszy niż data startowa"
            )
        
        # Prędkość kątowa
        omega = param_orb.oblicz_predkosc_katowa()
        if abs(omega) < EPSILON_NUMERYCZNY:
            raise BladObliczenOrbitych("Prędkość kątowa zbyt niska")
        
        # Użyj propaguj_pozycje
        return self.propaguj_pozycje(param_orb, delta_t, dlugosc_pocz)


# ===========================================================================================
# WALIDATORY
# ===========================================================================================

class WalidatorISO8601(WalidatorCzasowy):
    """Walidator formatu ISO 8601"""
    
    def waliduj_znacznik(self, znacznik_czasowy: str) -> datetime:
        """Parsuje i waliduje znacznik czasu w formacie ISO 8601"""
        try:
            dt = dateutil.parser.isoparse(znacznik_czasowy)
            
            # Zapewnienie timezone-aware datetime
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            return dt
            
        except (ValueError, TypeError) as e:
            raise BladWalidacjiCzasu(
                f"Nieprawidłowy format czasowy: {znacznik_czasowy}. "
                f"Oczekiwano ISO 8601 (np. '2024-01-15T10:30:00Z'). Błąd: {e}"
            ) from e


# ===========================================================================================
# SERWISY BIZNESOWE
# ===========================================================================================

class SerwisObliczenOrbitalalnych:
    """Serwis do obliczeń pozycji obiektów orbitalnych"""
    
    def __init__(self, propagator: PropagatorOrbity, walidator: WalidatorCzasowy):
        """Inicjalizacja serwisu z wybraną strategią propagacji"""
        self.propagator = propagator
        self.walidator = walidator
    
    def oblicz_pozycje_obiektu(
        self,
        sesja_bd: Session,
        id_obiektu: int,
        znacznik_czasu: str
    ) -> WspolrzedneGeodezyjne:
        """Oblicza pozycję obiektu w danym czasie"""
        
        # Walidacja czasu
        moment = self.walidator.waliduj_znacznik(znacznik_czasu)
        
        # Pobranie obiektu i jego orbity
        obiekt = sesja_bd.query(ModelObiektuBD).filter_by(id_rekordu=id_obiektu).first()
        if not obiekt:
            raise BladZasobuNieznaleziony(f"Obiekt o ID {id_obiektu} nie istnieje")
        
        orbita = sesja_bd.query(ModelOrbityBD).filter_by(id_rekordu=obiekt.id_orbity_powiazanej).first()
        if not orbita:
            raise BladZasobuNieznaleziony(f"Orbita obiektu {id_obiektu} nie istnieje")
        
        # Konwersja do parametrów orbitalnych
        params = ParametryOrbitalne(
            polOs_wielka=orbita.wysokosc_km + SREDNICA_BAZOWA_ZIEMI,
            inklinacja_kat=orbita.kat_inklinacji,
            wezl_wstepujacy=orbita.wezel_wst
        )
        
        # Obliczenie pozycji
        return self.propagator.oblicz_pozycje(
            param_orb=params,
            moment=moment,
            dlugosc_pocz=obiekt.pozycja_startowa_lon,
            data_startowa=obiekt.data_wprowadzenia
        )


class SerwisAnalizyZdarzen:
    """Serwis do wykrywania zdarzeń w przestrzeni kosmicznej"""
    
    def __init__(
        self,
        serwis_obliczen: SerwisObliczenOrbitalalnych,
        prog_zblizenia: float = TOLERANCJA_ZBLIZENIA
    ):
        """Inicjalizacja serwisu analizy"""
        self.serwis_obliczen = serwis_obliczen
        self.prog_zblizenia = prog_zblizenia
    
    def wykryj_kolizje(
        self,
        sesja_bd: Session,
        znacznik_czasu: str,
        filtr_orbit: Optional[int] = None
    ) -> List[ZdarzeniePrzestrz]:
        """Wykrywa potencjalne kolizje między obiektami"""
        
        # Pobierz wszystkie aktywne obiekty
        query = sesja_bd.query(ModelObiektuBD).filter_by(stan_operacyjny="active")
        
        if filtr_orbit:
            query = query.filter_by(id_orbity_powiazanej=filtr_orbit)
        
        obiekty = query.all()
        
        if len(obiekty) < 2:
            return []
        
        # Oblicz pozycje wszystkich obiektów
        pozycje = {}
        for obj in obiekty:
            try:
                poz = self.serwis_obliczen.oblicz_pozycje_obiektu(
                    sesja_bd=sesja_bd,
                    id_obiektu=obj.id_rekordu,
                    znacznik_czasu=znacznik_czasu
                )
                pozycje[obj.id_rekordu] = poz
            except Exception as e:
                log.warning(f"Błąd obliczania pozycji dla obiektu {obj.id_rekordu}: {e}")
                continue
        
        # Wykryj zbliżenia
        zdarzenia = []
        ids = list(pozycje.keys())
        
        for i, id_a in enumerate(ids):
            for j in range(i + 1, len(ids)):
                id_b = ids[j]
                poz_a, poz_b = pozycje[id_a], pozycje[id_b]
                
                dystans = poz_a.dystans_do(poz_b)
                
                if dystans <= self.prog_zblizenia:
                    # Użyj środka między pozycjami jako lokalizacji zdarzenia
                    sr_lat = (poz_a.szer_geogr + poz_b.szer_geogr) / 2
                    sr_lon = (poz_a.dlug_geogr + poz_b.dlug_geogr) / 2
                    sr_alt = (poz_a.wysokosc_npm + poz_b.wysokosc_npm) / 2
                    
                    moment = self.serwis_obliczen.walidator.waliduj_znacznik(znacznik_czasu)
                    
                    zdarzenie = ZdarzeniePrzestrz(
                        obiekt_id_a=id_a,
                        obiekt_id_b=id_b,
                        moment_czasu=moment,
                        lokalizacja=WspolrzedneGeodezyjne(sr_lat, sr_lon, sr_alt),
                        dystans_min=dystans
                    )
                    zdarzenia.append(zdarzenie)
        
        return zdarzenia


# ===========================================================================================
# FUNKCJE POMOCNICZE
# ===========================================================================================

def oblicz_roznice_czasu(
    czas_start: datetime,
    czas_koniec: datetime,
    kategoria: KategoriaPrecyzji = KategoriaPrecyzji.SEKUNDY
) -> float:
    """Oblicza różnicę czasu w określonej jednostce"""
    
    if czas_start.tzinfo is None:
        czas_start = czas_start.replace(tzinfo=timezone.utc)
    if czas_koniec.tzinfo is None:
        czas_koniec = czas_koniec.replace(tzinfo=timezone.utc)
    
    delta = czas_koniec - czas_start
    sekundy = delta.total_seconds()
    
    konwersje = {
        KategoriaPrecyzji.MILISEKUNDY: lambda s: s * 1000,
        KategoriaPrecyzji.SEKUNDY: lambda s: s,
        KategoriaPrecyzji.MINUTY: lambda s: s / 60,
        KategoriaPrecyzji.GODZINY: lambda s: s / 3600,
        KategoriaPrecyzji.DNI: lambda s: s / 86400
    }
    
    return konwersje[kategoria](sekundy)


def waliduj_parametry_orbitalne(wysokosc: float, inklinacja: float, raan: float) -> bool:
    """Waliduje parametry orbitalne"""
    from satelity_modele import MINIMALNA_WYSOKOSC_ORBITY, MAKSYMALNA_WYSOKOSC_ORBITY
    
    if not (MINIMALNA_WYSOKOSC_ORBITY <= wysokosc <= MAKSYMALNA_WYSOKOSC_ORBITY):
        return False
    
    if not (0 <= inklinacja <= 180):
        return False
    
    if not (0 <= raan < 360):
        return False
    
    return True
