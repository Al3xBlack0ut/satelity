"""
FastAPI - Endpointy i warstwa prezentacji

System Śledzenia Orbit Satelitarnych - Warstwa API
Autor: Aleks Czarnecki

Endpointy:
- /orbity/ - zarządzanie orbitami
- /satelity/ - zarządzanie obiektami orbitalnymi
- /satelity/{id}/pozycja - obliczanie pozycji
- /zblizenia - detekcja miejsc zbliżeń satelitów
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response, Path
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from satelity_modele import (
    ModelOrbityBD,
    ModelObiektuBD,
    SchematOrbitWejscie,
    SchematOrbitWyjscie,
    SchematObiektuWejscie,
    SchematObiektuWyjscie,
    SchematPozycjiWyjscie,
    SchematListyOrbit,
    SchematListyObiektow,
    SchematListyKolizji,
    SchematZdarzeniaKolizji,
    ZdarzeniePrzestrz,
    WspolrzedneGeodezyjne,
    ParametryOrbitalne,
    TypObiektu,
    uzyskaj_sesje_bd,
    SREDNICA_BAZOWA_ZIEMI,
    DOMYSLNA_WIELKOSC_STRONY,
    MAX_OBIEKTOW_NA_STRONE,
    TOLERANCJA_ZBLIZENIA,
)
from satelity_serwisy import (
    PropagatorKeplerowski,
    WalidatorISO8601,
    BladWalidacjiCzasu,
)

log = logging.getLogger(__name__)


# ===========================================================================================
# SERWISY 
# ===========================================================================================

class SerwisObliczenOrbitalalnych:
    """Serwis do obliczeń pozycji orbitalnych"""
    
    def __init__(self, propagator):
        self.propagator = propagator
        self.walidator = WalidatorISO8601()
        log.info(f"Zainicjalizowano serwis obliczeń z propagatorem: {propagator.__class__.__name__}")
    
    def oblicz_pozycje_w_czasie(
        self,
        model_obiektu: ModelObiektuBD,
        znacznik_czasu: datetime
    ) -> Optional[WspolrzedneGeodezyjne]:
        """
        Oblicza pozycję obiektu w określonym czasie
        
        Args:
            model_obiektu: Model obiektu z bazy danych
            znacznik_czasu: Moment czasu dla obliczeń
            
        Returns:
            Współrzędne lub None jeśli obiekt nie był jeszcze wprowadzony
        """
        # Sprawdź czy obiekt był już wprowadzony
        data_wprowadzenia = model_obiektu.data_wprowadzenia
        if data_wprowadzenia.tzinfo is None:
            data_wprowadzenia = data_wprowadzenia.replace(tzinfo=timezone.utc)
        
        if znacznik_czasu < data_wprowadzenia:
            return None  # Obiekt jeszcze nie istniał
        
        # Przygotuj parametry orbitalne
        orbita = model_obiektu.orbita_ref
        params = ParametryOrbitalne(
            polOs_wielka=SREDNICA_BAZOWA_ZIEMI + orbita.wysokosc_km,
            inklinacja_kat=orbita.kat_inklinacji,
            wezl_wstepujacy=orbita.wezel_wst
        )
        
        # Oblicz czas od wprowadzenia
        delta_czasu = (znacznik_czasu - data_wprowadzenia).total_seconds()
        
        # Propaguj pozycję
        wspolrzedne = self.propagator.propaguj_pozycje(
            params,
            delta_czasu,
            model_obiektu.pozycja_startowa_lon
        )
        
        return wspolrzedne


class SerwisAnalizyZdarzen:
    """Serwis do analizy zdarzeń orbitalnych (kolizje, zbliżenia)"""
    
    def __init__(self, serwis_obliczen: SerwisObliczenOrbitalalnych):
        self.serwis_obliczen = serwis_obliczen
        self.prog_wykrywania = TOLERANCJA_ZBLIZENIA
        log.info(f"Zainicjalizowano serwis zdarzeń z progiem: {self.prog_wykrywania} km")
    
    def parsuj_precyzje(self, tekst_precyzji: str) -> timedelta:
        """Parsuje string precyzji na timedelta"""
        pattern = r'^(\d+)(ms|s|m|h|d)$'
        match = re.match(pattern, tekst_precyzji)
        
        if not match:
            raise ValueError(f"Nieprawidłowy format precyzji: {tekst_precyzji}")
        
        wartosc = int(match.group(1))
        jednostka = match.group(2)
        
        if wartosc < 1:
            raise ValueError("Wartość precyzji musi być >= 1")
        
        mapowanie = {
            'ms': lambda v: timedelta(milliseconds=v),
            's': lambda v: timedelta(seconds=v),
            'm': lambda v: timedelta(minutes=v),
            'h': lambda v: timedelta(hours=v),
            'd': lambda v: timedelta(days=v)
        }
        
        return mapowanie[jednostka](wartosc)
    
    def zaokraglij_do_siatki(self, dt: datetime, delta: timedelta) -> datetime:
        """Zaokrągla datetime do najbliższej siatki czasowej"""
        timestamp = dt.timestamp()
        delta_sekund = delta.total_seconds()
        
        zaokraglony = round(timestamp / delta_sekund) * delta_sekund
        
        return datetime.fromtimestamp(zaokraglony, tz=timezone.utc)
    
    def wykryj_zdarzenia_w_przedziale(
        self,
        obiekty,
        czas_start: datetime,
        czas_koniec: datetime,
        delta_czasu: timedelta
    ):
        """
        Wykrywa zdarzenia w przedziale czasowym
        
        Args:
            obiekty: Lista obiektów do analizy
            czas_start: Początek przedziału
            czas_koniec: Koniec przedziału
            delta_czasu: Krok czasowy analizy
            
        Returns:
            Lista wykrytych zdarzeń
        """
        zdarzenia = []
        
        # Zaokrąglij granice do siatki
        czas_start = self.zaokraglij_do_siatki(czas_start, delta_czasu)
        czas_koniec = self.zaokraglij_do_siatki(czas_koniec, delta_czasu)
        
        log.info(f"Rozpoczynam analizę zdarzeń od {czas_start} do {czas_koniec}")
        
        # Iteruj po siatce czasowej
        czas_obecny = czas_start
        licznik_krokow = 0
        
        while czas_obecny <= czas_koniec:
            # Oblicz pozycje wszystkich aktywnych obiektów
            pozycje_map: Dict[int, WspolrzedneGeodezyjne] = {}
            
            for obiekt in obiekty:
                if obiekt.stan_operacyjny != TypObiektu.AKTYWNY.value:
                    continue
                
                pozycja = self.serwis_obliczen.oblicz_pozycje_w_czasie(
                    obiekt,
                    czas_obecny
                )
                
                if pozycja is not None:
                    pozycje_map[obiekt.id_rekordu] = pozycja
            
            # Analiza par obiektów
            ids_aktywne = sorted(pozycje_map.keys())
            
            for i, id_a in enumerate(ids_aktywne):
                for id_b in ids_aktywne[i+1:]:
                    poz_a = pozycje_map[id_a]
                    poz_b = pozycje_map[id_b]
                    
                    dystans = poz_a.dystans_do(poz_b)
                    
                    if dystans < self.prog_wykrywania:
                        zdarzenie = ZdarzeniePrzestrz(
                            obiekt_id_a=min(id_a, id_b),
                            obiekt_id_b=max(id_a, id_b),
                            moment_czasu=czas_obecny,
                            lokalizacja=poz_a,
                            dystans_min=dystans
                        )
                        zdarzenia.append(zdarzenie)
                        
                        log.warning(
                            f"Wykryto zbliżenie: {id_a} <-> {id_b} "
                            f"dystans={dystans:.6f}km w {czas_obecny}"
                        )
            
            czas_obecny += delta_czasu
            licznik_krokow += 1
        
        log.info(f"Zakończono analizę. Przeanalizowano {licznik_krokow} kroków, wykryto {len(zdarzenia)} zdarzeń")
        
        return zdarzenia


# ===========================================================================================
# WALIDATORY I POMOCNIKI
# ===========================================================================================

def waliduj_identyfikator_dodatni(id_str: str) -> int:
    """Waliduje i konwertuje ID na dodatnią liczbę całkowitą"""
    try:
        id_int = int(id_str)
        if id_int <= 0:
            raise HTTPException(status_code=400, detail="Nieprawidłowy format identyfikatora")
        return id_int
    except ValueError:
        raise HTTPException(status_code=400, detail="Nieprawidłowy format identyfikatora")


def waliduj_parametry_stronicowania(pominiete: int, limit: int):
    """Waliduje parametry paginacji"""
    if pominiete < 0 or limit < 1 or limit > MAX_OBIEKTOW_NA_STRONE:
        raise HTTPException(status_code=400, detail="Nieprawidłowe parametry stronicowania")


# ===========================================================================================
# APLIKACJA FASTAPI - Warstwa prezentacji
# ===========================================================================================

system_api = FastAPI(
    title="System Śledzenia Orbit Satelitarnych",
    version="2.0.0",
    description="System zarządzania i śledzenia obiektów orbitalnych"
)

# Middleware CORS
system_api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicjalizacja serwisów
propagator_glowny = PropagatorKeplerowski()
serwis_obliczen_globalny = SerwisObliczenOrbitalalnych(propagator_glowny)
serwis_zdarzen_globalny = SerwisAnalizyZdarzen(serwis_obliczen_globalny)


# ===========================================================================================
# OBSŁUGA WYJĄTKÓW
# ===========================================================================================

@system_api.exception_handler(RequestValidationError)
async def obsluz_blad_walidacji(zapytanie: Request, wyjatek: RequestValidationError):
    """Obsługa błędów walidacji"""
    try:
        errors = wyjatek.errors()
        
        for err in errors:
            loc = err.get('loc', [])
            if len(loc) >= 2 and loc[0] == 'path' and loc[1] == 'id':
                return JSONResponse(status_code=400, content={"detail": "Nieprawidłowy format identyfikatora"})
        
        if "/position" in str(zapytanie.url.path):
            for err in errors:
                loc = err.get('loc', [])
                if len(loc) >= 2 and loc[0] == 'query' and loc[1] == 'timestamp':
                    return JSONResponse(status_code=400, content={"detail": "Nieprawidłowy identyfikator lub znacznik czasu"})
        
        if zapytanie.url.path == "/zblizenia":
            return JSONResponse(status_code=400, content={"detail": "Nieprawidłowy format lub zakres dat"})
        
        return JSONResponse(status_code=400, content={"detail": "Nieprawidłowe dane wejściowe"})
    
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Nieprawidłowe dane wejściowe"})


# ===========================================================================================
# ENDPOINTY - Główne
# ===========================================================================================

@system_api.get("/")
async def endpoint_glowny():
    """Endpoint główny z informacjami o systemie"""
    return {
        "message": "System Śledzenia Orbit - API v2.0",
        "docs": "/docs",
        "status": "operational"
    }


@system_api.get("/status")
async def sprawdzenie_stanu():
    """Sprawdzenie stanu systemu"""
    return {"status": "działa", "timestamp": datetime.now(timezone.utc).isoformat()}


# ===========================================================================================
# ENDPOINTY - Orbity (CRUD)
# ===========================================================================================

@system_api.post("/orbity/", status_code=201, response_model=SchematOrbitWyjscie)
async def utworz_orbite(
    dane_wej: SchematOrbitWejscie,
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Tworzy nową orbitę w katalogu"""
    # Sprawdź unikalność
    istniejaca = sesja.query(ModelOrbityBD).filter(
        ModelOrbityBD.identyfikator_orbity == dane_wej.identyfikator_orbity
    ).first()
    
    if istniejaca:
        raise HTTPException(status_code=409, detail="Nazwa orbity już istnieje")
    
    # Utwórz rekord
    nowa_orbita = ModelOrbityBD(
        identyfikator_orbity=dane_wej.identyfikator_orbity,
        wysokosc_km=dane_wej.wysokosc_km,
        kat_inklinacji=dane_wej.kat_inklinacji,
        wezel_wst=dane_wej.wezel_wst
    )
    
    sesja.add(nowa_orbita)
    sesja.commit()
    sesja.refresh(nowa_orbita)
    
    log.info(f"Utworzono orbitę: {dane_wej.identyfikator_orbity}")
    
    return SchematOrbitWyjscie.z_modelu(nowa_orbita)


@system_api.get("/orbity/{id}", response_model=SchematOrbitWyjscie)
async def pobierz_orbite(
    id_zasobu: str = Path(alias="id"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Pobiera orbitę po ID"""
    id_val = waliduj_identyfikator_dodatni(id_zasobu)
    
    orbita = sesja.query(ModelOrbityBD).filter(
        ModelOrbityBD.id_rekordu == id_val
    ).first()
    
    if not orbita:
        raise HTTPException(status_code=404, detail="Orbit not found")
    
    return SchematOrbitWyjscie.z_modelu(orbita)


@system_api.get("/orbity/", response_model=SchematListyOrbit)
async def listuj_orbity(
    skip: int = Query(0, ge=0),
    limit: int = Query(DOMYSLNA_WIELKOSC_STRONY, ge=1, le=MAX_OBIEKTOW_NA_STRONE),
    name: Optional[str] = None,
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Listuje orbity z filtrowaniem i paginacją"""
    waliduj_parametry_stronicowania(skip, limit)
    
    zapytanie = sesja.query(ModelOrbityBD)
    
    if name:
        zapytanie = zapytanie.filter(
            ModelOrbityBD.identyfikator_orbity.ilike(f"%{name}%")
        )
    
    total = zapytanie.count()
    orbity = zapytanie.offset(skip).limit(limit).all()
    
    return SchematListyOrbit(
        orbity=[SchematOrbitWyjscie.z_modelu(o) for o in orbity],
        razem=total,
        pomin=skip,
        limit=limit
    )


@system_api.put("/orbity/{id}", response_model=SchematOrbitWyjscie)
async def aktualizuj_orbite(
    dane_wej: SchematOrbitWejscie,
    id_zasobu: str = Path(alias="id"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Aktualizuje parametry orbity"""
    id_val = waliduj_identyfikator_dodatni(id_zasobu)
    
    orbita = sesja.query(ModelOrbityBD).filter(
        ModelOrbityBD.id_rekordu == id_val
    ).first()
    
    if not orbita:
        raise HTTPException(status_code=404, detail="Orbit not found")
    
    # Sprawdź konflikt nazwy
    konflikt = sesja.query(ModelOrbityBD).filter(
        ModelOrbityBD.identyfikator_orbity == dane_wej.identyfikator_orbity,
        ModelOrbityBD.id_rekordu != id_val
    ).first()
    
    if konflikt:
        raise HTTPException(status_code=409, detail="Nazwa orbity już istnieje")
    
    # Aktualizuj
    orbita.identyfikator_orbity = dane_wej.identyfikator_orbity
    orbita.wysokosc_km = dane_wej.wysokosc_km
    orbita.kat_inklinacji = dane_wej.kat_inklinacji
    orbita.wezel_wst = dane_wej.wezel_wst
    
    sesja.commit()
    sesja.refresh(orbita)
    
    log.info(f"Zaktualizowano orbitę ID={id_val}")
    
    return SchematOrbitWyjscie.z_modelu(orbita)


@system_api.delete("/orbity/{id}", status_code=204)
async def usun_orbite(
    id_zasobu: str = Path(alias="id"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Usuwa orbitę z katalogu"""
    id_val = waliduj_identyfikator_dodatni(id_zasobu)
    
    orbita = sesja.query(ModelOrbityBD).filter(
        ModelOrbityBD.id_rekordu == id_val
    ).first()
    
    if not orbita:
        raise HTTPException(status_code=404, detail="Orbit not found")
    
    # Sprawdź powiązania
    liczba_powiazanych = sesja.query(ModelObiektuBD).filter(
        ModelObiektuBD.id_orbity_powiazanej == id_val
    ).count()
    
    if liczba_powiazanych > 0:
        raise HTTPException(status_code=409, detail="Orbita jest używana przez obiekty")
    
    sesja.delete(orbita)
    sesja.commit()
    
    log.info(f"Usunięto orbitę ID={id_val}")
    
    return Response(status_code=204)


# ===========================================================================================
# ENDPOINTY - Satelity (CRUD)
# ===========================================================================================

@system_api.post("/satelity/", status_code=201, response_model=SchematObiektuWyjscie)
async def utworz_obiekt(
    dane_wej: SchematObiektuWejscie,
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Dodaje nowy obiekt orbitalny do katalogu"""
    try:
        # Sprawdź unikalność nazwy
        istniejacy = sesja.query(ModelObiektuBD).filter(
            ModelObiektuBD.nazwa_obiektu == dane_wej.nazwa_obiektu
        ).first()
        
        if istniejacy:
            raise HTTPException(status_code=409, detail="Nazwa obiektu już istnieje")
        
        # Sprawdź istnienie orbity
        orbita = sesja.query(ModelOrbityBD).filter(
            ModelOrbityBD.id_rekordu == dane_wej.id_orbity_powiazanej
        ).first()
        
        if not orbita:
            raise HTTPException(status_code=400, detail="Nieprawidłowy identyfikator orbity")
        
        # Utwórz obiekt
        nowy_obiekt = ModelObiektuBD(
            nazwa_obiektu=dane_wej.nazwa_obiektu,
            operator_systemu=dane_wej.operator_systemu,
            data_wprowadzenia=dane_wej.data_wprowadzenia,
            stan_operacyjny=dane_wej.stan_operacyjny.value,
            pozycja_startowa_lon=dane_wej.pozycja_startowa_lon,
            id_orbity_powiazanej=dane_wej.id_orbity_powiazanej
        )
        
        sesja.add(nowy_obiekt)
        sesja.commit()
        sesja.refresh(nowy_obiekt)
        
        log.info(f"Utworzono obiekt: {dane_wej.nazwa_obiektu}")
        
        return SchematObiektuWyjscie.z_modelu(nowy_obiekt)
    
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format or invalid data")


@system_api.get("/satelity/{id}", response_model=SchematObiektuWyjscie)
async def pobierz_obiekt(
    id_zasobu: str = Path(alias="id"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Pobiera obiekt po ID"""
    id_val = waliduj_identyfikator_dodatni(id_zasobu)
    
    obiekt = sesja.query(ModelObiektuBD).filter(
        ModelObiektuBD.id_rekordu == id_val
    ).first()
    
    if not obiekt:
        raise HTTPException(status_code=404, detail="Satellite not found")
    
    return SchematObiektuWyjscie.z_modelu(obiekt)


@system_api.get("/satelity/", response_model=SchematListyObiektow)
async def listuj_obiekty(
    skip: int = Query(0, ge=0),
    limit: int = Query(DOMYSLNA_WIELKOSC_STRONY, ge=1, le=MAX_OBIEKTOW_NA_STRONE),
    operator: Optional[str] = None,
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Listuje obiekty orbitalne z filtrowaniem"""
    waliduj_parametry_stronicowania(skip, limit)
    
    zapytanie = sesja.query(ModelObiektuBD)
    
    if operator:
        zapytanie = zapytanie.filter(
            ModelObiektuBD.operator_systemu.ilike(f"%{operator}%")
        )
    
    total = zapytanie.count()
    obiekty = zapytanie.offset(skip).limit(limit).all()
    
    return SchematListyObiektow(
        satelity=[SchematObiektuWyjscie.z_modelu(o) for o in obiekty],
        razem=total,
        pomin=skip,
        limit=limit
    )


@system_api.put("/satelity/{id}", response_model=SchematObiektuWyjscie)
async def aktualizuj_obiekt(
    dane_wej: SchematObiektuWejscie,
    id_zasobu: str = Path(alias="id"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Aktualizuje parametry obiektu orbitalnego"""
    id_val = waliduj_identyfikator_dodatni(id_zasobu)
    
    obiekt = sesja.query(ModelObiektuBD).filter(
        ModelObiektuBD.id_rekordu == id_val
    ).first()
    
    if not obiekt:
        raise HTTPException(status_code=404, detail="Satellite not found")
    
    # Sprawdź konflikt nazwy
    konflikt = sesja.query(ModelObiektuBD).filter(
        ModelObiektuBD.nazwa_obiektu == dane_wej.nazwa_obiektu,
        ModelObiektuBD.id_rekordu != id_val
    ).first()
    
    if konflikt:
        raise HTTPException(status_code=409, detail="Nazwa obiektu już istnieje")
    
    # Sprawdź orbitę
    orbita = sesja.query(ModelOrbityBD).filter(
        ModelOrbityBD.id_rekordu == dane_wej.id_orbity_powiazanej
    ).first()
    
    if not orbita:
        raise HTTPException(status_code=400, detail="Invalid ID format or invalid data")
    
    # Aktualizuj
    obiekt.nazwa_obiektu = dane_wej.nazwa_obiektu
    obiekt.operator_systemu = dane_wej.operator_systemu
    obiekt.data_wprowadzenia = dane_wej.data_wprowadzenia
    obiekt.stan_operacyjny = dane_wej.stan_operacyjny.value
    obiekt.pozycja_startowa_lon = dane_wej.pozycja_startowa_lon
    obiekt.id_orbity_powiazanej = dane_wej.id_orbity_powiazanej
    
    sesja.commit()
    sesja.refresh(obiekt)
    
    log.info(f"Zaktualizowano obiekt ID={id_val}")
    
    return SchematObiektuWyjscie.z_modelu(obiekt)


@system_api.delete("/satelity/{id}", status_code=204)
async def usun_obiekt(
    id_zasobu: str = Path(alias="id"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Usuwa obiekt z katalogu"""
    id_val = waliduj_identyfikator_dodatni(id_zasobu)
    
    obiekt = sesja.query(ModelObiektuBD).filter(
        ModelObiektuBD.id_rekordu == id_val
    ).first()
    
    if not obiekt:
        raise HTTPException(status_code=404, detail="Satellite not found")
    
    sesja.delete(obiekt)
    sesja.commit()
    
    log.info(f"Usunięto obiekt ID={id_val}")
    
    return Response(status_code=204)


# ===========================================================================================
# ENDPOINTY - Obliczenia pozycji
# ===========================================================================================

@system_api.get("/satelity/{id}/pozycja", response_model=SchematPozycjiWyjscie)
async def oblicz_pozycje_obiektu(
    id_zasobu: str = Path(alias="id"),
    timestamp: str = Query(..., description="ISO-8601 UTC datetime"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Oblicza pozycję obiektu w określonym czasie"""
    try:
        id_val = waliduj_identyfikator_dodatni(id_zasobu)
    except HTTPException as e:
        if e.status_code == 400:
            raise HTTPException(status_code=400, detail="Nieprawidłowy identyfikator lub znacznik czasu")
        raise
    
    # Pobierz obiekt
    obiekt = sesja.query(ModelObiektuBD).filter(
        ModelObiektuBD.id_rekordu == id_val
    ).first()
    
    if not obiekt:
        raise HTTPException(status_code=404, detail="Satellite not found")
    
    # Waliduj znacznik czasu
    try:
        walidator = WalidatorISO8601()
        znacznik = walidator.waliduj_znacznik(timestamp)
    except BladWalidacjiCzasu:
        raise HTTPException(status_code=400, detail="Nieprawidłowy format znacznika czasu")
    
    # Sprawdź czy znacznik nie jest przed wprowadzeniem
    data_wprowadzenia = obiekt.data_wprowadzenia
    if data_wprowadzenia.tzinfo is None:
        data_wprowadzenia = data_wprowadzenia.replace(tzinfo=timezone.utc)
    
    if znacznik < data_wprowadzenia:
        raise HTTPException(status_code=400, detail="Znacznik czasu przed datą wprowadzenia")
    
    # Oblicz pozycję
    wspolrzedne = serwis_obliczen_globalny.oblicz_pozycje_w_czasie(obiekt, znacznik)
    
    if wspolrzedne is None:
        raise HTTPException(status_code=400, detail="Nie można obliczyć pozycji")
    
    return SchematPozycjiWyjscie(
        szerokosc=wspolrzedne.szer_geogr,
        dlugosc=wspolrzedne.dlug_geogr,
        wysokosc=wspolrzedne.wysokosc_npm
    )


# ===========================================================================================
# ENDPOINTY - Analiza zdarzeń
# ===========================================================================================

@system_api.get("/zblizenia", response_model=SchematListyKolizji)
async def wykryj_zblizenia(
    start_date: str = Query(..., description="Data początkowa analizy (ISO-8601)"),
    end_date: str = Query(..., description="Data końcowa analizy (ISO-8601)"),
    precision: str = Query("1m", description="Precyzja czasowa (np. 1m, 5s, 1h)"),
    sesja: Session = Depends(uzyskaj_sesje_bd)
):
    """Wykrywa miejsca zbliżeń (spotkań) satelitów w przedziale czasowym"""
    try:
        walidator = WalidatorISO8601()
        
        # Parsuj daty
        try:
            dt_start = walidator.waliduj_znacznik(start_date)
            dt_koniec = walidator.waliduj_znacznik(end_date)
        except BladWalidacjiCzasu:
            raise HTTPException(status_code=400, detail="Nieprawidłowy format znacznika czasu")
        
        # Waliduj zakres
        if dt_start >= dt_koniec:
            raise HTTPException(status_code=400, detail="Nieprawidłowy format znacznika czasu")
        
        # Parsuj precyzję
        try:
            delta_czasu = serwis_zdarzen_globalny.parsuj_precyzje(precision)
        except ValueError:
            raise HTTPException(status_code=400, detail="Nieprawidłowy format znacznika czasu")
        
        # Pobierz wszystkie obiekty
        obiekty = sesja.query(ModelObiektuBD).join(ModelOrbityBD).all()
        
        # Wykryj zdarzenia
        zdarzenia = serwis_zdarzen_globalny.wykryj_zdarzenia_w_przedziale(
            obiekty,
            dt_start,
            dt_koniec,
            delta_czasu
        )
        
        # Sortuj
        zdarzenia.sort(key=lambda z: (z.moment_czasu, z.obiekt_id_a, z.obiekt_id_b))
        
        # Konwertuj na schematy
        kolizje_out = [
            SchematZdarzeniaKolizji(
                satelita1=z.obiekt_id_a,
                satelita2=z.obiekt_id_b,
                czas=z.moment_czasu.strftime("%Y-%m-%dT%H:%M:%SZ"),
                pozycja=SchematPozycjiWyjscie(
                    szerokosc=z.lokalizacja.szer_geogr,
                    dlugosc=z.lokalizacja.dlug_geogr,
                    wysokosc=z.lokalizacja.wysokosc_npm
                )
            )
            for z in zdarzenia
        ]
        
        return SchematListyKolizji(zblizenia=kolizje_out)
    
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Nieprawidłowy format znacznika czasu")


# ===========================================================================================
# PUNKT WEJŚCIA
# ===========================================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(system_api, host="0.0.0.0", port=8000)
