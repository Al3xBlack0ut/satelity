# System Śledzenia Orbit Satelitarnych

Kompletny system zarządzania i śledzenia obiektów orbitalnych z detekcją zbliżeń i propagacją Keplerianowską

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-2.0-green.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-ORM-orange.svg)](https://www.sqlalchemy.org/)

**Autor:** Aleks Czarnecki  

---

## Spis treści

1. [Wprowadzenie](#wprowadzenie)
2. [Architektura systemu](#architektura-systemu)  
3. [Struktura projektu](#struktura-projektu)
4. [Instalacja i konfiguracja](#instalacja-i-konfiguracja)
5. [API REST Server](#api-rest-server)
6. [Podstawowe użycie](#podstawowe-użycie)
7. [Propagacja orbit](#propagacja-orbit)
8. [Detekcja zbliżeń](#detekcja-zbliżeń)
9. [Modele danych](#modele-danych)
10. [Testy](#testy)
11. [Przykłady użycia](#przykłady-użycia)
12. [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Wprowadzenie

**System Śledzenia Orbit Satelitarnych** to zaawansowane narzędzie do zarządzania, monitorowania i analizy orbit obiektów kosmicznych. System wykorzystuje **propagację Keplerianowską** do precyzyjnego obliczania pozycji satelitów i oferuje kompleksowe API REST do zarządzania danymi orbitalnymi.

### Główne funkcjonalności

- **Propagacja Keplerowska** — precyzyjne obliczanie pozycji satelitów w czasie
- **REST API Server** — serwer FastAPI z automatyczną dokumentacją Swagger
- **Zarządzanie orbitami** — pełne CRUD dla orbit i satelitów  
- **Obliczanie pozycji** — pozycja satelity w dowolnym momencie czasu (szerokosc, dlugosc, wysokosc)
- **Detekcja zbliżeń** — automatyczne wykrywanie miejsc spotkań między satelitami
- **Baza danych** — SQLAlchemy ORM (in-memory)
- **Walidacja danych** — Pydantic schematy z pełną walidacją
- **Paginacja** — wydajne przeglądanie dużych zbiorów danych
- **Wzorce projektowe** — Strategy, Service Layer, Dependency Injection
- **Testy** — 25 testów funkcjonalnych

---

## Architektura systemu

```text
┌────────────────────────────────────────────┐
│  REST API Server (FastAPI)                 │ ← HTTP API + Swagger UI
├────────────────────────────────────────────┤
│  SerwisObliczenOrbitalalnych               │ ← Serwis obliczeń pozycji
│  SerwisAnalizyZdarzen                      │ ← Serwis detekcji kolizji
├────────────────────────────────────────────┤
│  PropagatorKeplerowski                     │ ← Propagacja orbit
│  WalidatorISO8601                          │ ← Walidacja czasu
├────────────────────────────────────────────┤
│  Models: ModelOrbityBD, ModelObiektuBD     │ ← SQLAlchemy ORM
│  Schemas: Pydantic validation              │ ← Walidacja danych
├────────────────────────────────────────────┤
│  SQLAlchemy Database (in-memory)           │ ← Baza danych
└────────────────────────────────────────────┘
```

### Architektura modułowa

System podzielony na 3 logiczne moduły:

```text
satelity_api.py (FastAPI + serwisy)
    ↓
satelity_serwisy.py (logika biznesowa)
    ↓
satelity_modele.py (struktury danych)
```

**Zasada**: Każdy moduł zależy tylko od modułów "niższych" w hierarchii. Brak circular dependencies.

## Struktura projektu

```text
hackaton/
├── satelity_modele.py           # Modele danych
│   ├── Dataclasses              # WspolrzedneGeodezyjne, ParametryOrbitalne
│   ├── SQLAlchemy Models        # ModelOrbityBD, ModelObiektuBD
│   ├── Pydantic Schemas         # Walidacja API
│   └── Database Config          # Silnik, sesja
├── satelity_serwisy.py          # Logika biznesowa
│   ├── PropagatorKeplerowski    # Propagacja orbit
│   ├── WalidatorISO8601         # Walidacja czasu
│   └── Funkcje pomocnicze       # Obliczenia i walidacje
├── satelity_api.py              # FastAPI endpoints
│   ├── Serwisy                  # SerwisObliczen, SerwisZdarzen
│   ├── 14 endpointów REST       # CRUD + obliczenia + zbliżenia
│   └── Obsługa błędów           # Walidacja i wyjątki
├── test.sh                      # Testy funkcjonalne (25 testów)
├── run.sh                       # Skrypt startowy serwera
├── requirements.txt             # Zależności Python
└── README.md                    # Ta dokumentacja
```

### Kluczowe komponenty

**Modele danych** (`satelity_modele.py`):

- `WspolrzedneGeodezyjne` — współrzędne lat/lon/alt z metodami konwersji
- `ParametryOrbitalne` — parametry Keplerowskie (a, i, RAAN)
- `ModelOrbityBD` — model SQLAlchemy dla orbit
- `ModelObiektuBD` — model SQLAlchemy dla satelitów
- Schematy Pydantic — pełna walidacja danych wejściowych/wyjściowych

**Logika biznesowa** (`satelity_serwisy.py`):

- `PropagatorKeplerowski` — propagacja pozycji metodą Keplerowską
- `WalidatorISO8601` — parsowanie i walidacja dat ISO 8601
- Funkcje pomocnicze — obliczenia czasu, walidacja parametrów

**API REST** (`satelity_api.py`):

- `SerwisObliczenOrbitalalnych` — obliczanie pozycji satelitów
- `SerwisAnalizyZdarzen` — wykrywanie zbliżeń w przedziale czasowym
- 14 endpointów REST — pełne CRUD + obliczenia + analiza zbliżeń

### Scentralizowane stałe konfiguracyjne

Wszystkie kluczowe parametry konfiguracyjne zostały scentralizowane w **satelity_modele.py**:

```python
# Stałe planetarne i orbitalne
PARAMETR_GRAWIT_ZIEMI = 398600.4418  # km³/s²
SREDNICA_BAZOWA_ZIEMI = 6371.0  # km
TOLERANCJA_ZBLIZENIA = 0.01  # km - prog wykrywania kolizji

# Limity operacyjne
MAX_OBIEKTOW_NA_STRONE = 100
DOMYSLNA_WIELKOSC_STRONY = 10
MINIMALNA_WYSOKOSC_ORBITY = 160.0  # km
MAKSYMALNA_WYSOKOSC_ORBITY = 40000.0  # km
```

---

## Instalacja i konfiguracja

### Wymagania systemowe

- **Python 3.13+** (zalecane)
- **pip** (menedżer pakietów Python)

### Instalacja krok po kroku

#### 1. Klonowanie repozytorium

```bash
git clone <repository-url>
cd hackaton
```

#### 2. Instalacja zależności

```bash
# Instalacja pakietów Python
pip install -r requirements.txt
```

#### 3. Uruchomienie serwera

```bash
# Uruchom serwer FastAPI
./run.sh

# Lub bezpośrednio:
uvicorn satelity_api:system_api --host 0.0.0.0 --port 8000
```

#### 4. Test instalacji

```bash
# Uruchom testy
./test.sh

# Oczekiwany wynik: 25/25 testów zaliczonych ✅
```

---

## API REST Server

### Uruchomienie serwera

```bash
./run.sh
```

Serwer zostanie uruchomiony pod adresem: `http://localhost:8000`

**Dostępne interfejsy:**

- **API**: `http://localhost:8000`
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Główne endpointy API

#### Podstawowe

| Method | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/` | Strona główna z informacjami o systemie |
| `GET` | `/status` | Sprawdzenie statusu |

#### Orbity (CRUD)

| Method | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/orbity/` | Tworzenie nowej orbity |
| `GET` | `/orbity/` | Lista orbit (z paginacją i filtrowaniem) |
| `GET` | `/orbity/{id}` | Szczegóły orbity |
| `PUT` | `/orbity/{id}` | Aktualizacja orbity |
| `DELETE` | `/orbity/{id}` | Usuwanie orbity |

#### Satelity (CRUD)

| Method | Endpoint | Opis |
|--------|----------|------|
| `POST` | `/satelity/` | Dodanie satelity |
| `GET` | `/satelity/` | Lista satelitów (z paginacją i filtrowaniem) |
| `GET` | `/satelity/{id}` | Szczegóły satelity |
| `PUT` | `/satelity/{id}` | Aktualizacja satelity |
| `DELETE` | `/satelity/{id}` | Usuwanie satelity |

#### Obliczenia i analiza

| Method | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/satelity/{id}/pozycja?timestamp=...` | Pozycja satelity w czasie |
| `GET` | `/zblizenia?start_date=...&end_date=...&precision=...` | Wykrywanie zbliżeń orbitów |

### Przykłady wywołań API

**Utworzenie orbity:**

```bash
curl -X POST http://localhost:8000/orbity/ \
  -H "Content-Type: application/json" \
  -d '{
    "nazwa": "ISS-Orbit",
    "wysokosc": 408.0,
    "inklinacja": 51.6,
    "wezel": 45.0
  }'
```

**Dodanie satelity:**

```bash
curl -X POST http://localhost:8000/satelity/ \
  -H "Content-Type: application/json" \
  -d '{
    "nazwa": "ISS",
    "operator": "NASA/Roscosmos",
    "data_startu": "1998-11-20T00:00:00Z",
    "status": "active",
    "dlugosc_poczatkowa": 0.0,
    "id_orbity": 1
  }'
```

**Obliczenie pozycji:**

```bash
curl "http://localhost:8000/satelity/1/pozycja?timestamp=2024-06-15T12:00:00Z"
```

**Odpowiedź:**

```json
{
  "szerokosc": 45.3,
  "dlugosc": -12.7,
  "wysokosc": 408.0
}
```

**Detekcja zbliżeń:**

```bash
curl "http://localhost:8000/zblizenia?start_date=2020-01-01T00:00:00Z&end_date=2020-01-02T00:00:00Z&precision=1h"
```

---

## Podstawowe użycie

### Python SDK

```python
import requests

BASE_URL = "http://localhost:8000"

# Utworzenie orbity
orbit = requests.post(f"{BASE_URL}/orbity/", json={
    "nazwa": "LEO-400",
    "wysokosc": 400.0,
    "inklinacja": 51.6,
    "wezel": 0.0
}).json()

print(f"Utworzono orbitę ID={orbit['id']}")

# Dodanie satelity
satellite = requests.post(f"{BASE_URL}/satelity/", json={
    "nazwa": "TestSat-1",
    "operator": "TestOrg",
    "data_startu": "2020-01-01T00:00:00Z",
    "status": "active",
    "dlugosc_poczatkowa": 0.0,
    "id_orbity": orbit['id']
}).json()

print(f"Utworzono satelitę ID={satellite['id']}")

# Obliczenie pozycji
position = requests.get(
    f"{BASE_URL}/satelity/{satellite['id']}/pozycja",
    params={"timestamp": "2024-06-15T12:00:00Z"}
).json()

print(f"Pozycja: lat={position['lat']:.2f}°, lon={position['lon']:.2f}°, alt={position['alt']:.1f}km")
```

### Swagger UI

Otwórz przeglądarkę: `http://localhost:8000/docs`

- ✅ Interaktywna dokumentacja API
- ✅ Możliwość testowania wszystkich endpointów
- ✅ Automatyczne schematy JSON
- ✅ Walidacja danych w czasie rzeczywistym

---

## Propagacja orbit

System wykorzystuje **propagację Keplerowską** do obliczania pozycji satelitów:

### Parametry orbitalne

- **Semi-major axis (a)** — wielka półoś orbity [km]
- **Inclination (i)** — inklinacja orbity [stopnie, 0-180°]
- **RAAN (Ω)** — Right Ascension of Ascending Node [stopnie, 0-360°]

### Algorytm propagacji

1. Oblicz prędkość kątową: `ω = 2π/T`, gdzie `T = 2π√(a³/μ)`
2. Oblicz anomalię prawdziwą: `ν = ωt + ν₀`
3. Konwertuj na współrzędne orbitalne
4. Transformuj do współrzędnych geodezyjnych (lat, lon, alt)

### Przykład obliczeń

```python
from satelity_modele import ParametryOrbitalne, SREDNICA_BAZOWA_ZIEMI
from satelity_serwisy import PropagatorKeplerowski

# Parametry ISS
params = ParametryOrbitalne(
    polOs_wielka=SREDNICA_BAZOWA_ZIEMI + 408.0,  # 408km wysokość
    inklinacja_kat=51.6,                          # 51.6° inklinacja
    wezl_wstepujacy=45.0                          # 45° RAAN
)

# Oblicz okres orbitalny
T = params.oblicz_okres_orbitalny()
print(f"Okres orbitalny: {T/60:.1f} minut")

# Propagacja pozycji
propagator = PropagatorKeplerowski()
pozycja = propagator.propaguj_pozycje(
    parametry=params,
    czas_od_epoki=3600.0,  # 1 godzina
    dlug_poczatkowa=0.0
)

print(f"Pozycja po 1h: {pozycja.szer_geogr:.2f}°, {pozycja.dlug_geogr:.2f}°")
```

---

## Detekcja zbliżeń

System automatycznie wykrywa miejsca spotkań między satelitami (nie rzeczywiste kolizje fizyczne).

### Parametry detekcji

- **start_date** — początek przedziału czasowego (ISO 8601)
- **end_date** — koniec przedziału czasowego (ISO 8601)
- **precision** — krok czasowy (`1ms`, `1s`, `1m`, `1h`, `1d`)

### Próg wykrywania

Domyślny próg zbliżenia: **0.015 km** (15 metrów)

### Przykład użycia

```bash
# Wykryj zbliżenia w ciągu 24h z precyzją 1h
curl "http://localhost:8000/zblizenia?start_date=2020-01-01T00:00:00Z&end_date=2020-01-02T00:00:00Z&precision=1h"
```

**Odpowiedź:**

```json
{
  "zblizenia": [
    {
      "satelita1": 1,
      "satelita2": 2,
      "czas": "2020-01-01T14:30:00Z",
      "pozycja": {
        "szerokosc": 45.3,
        "dlugosc": -12.7,
        "wysokosc": 405.0
      }
    }
  ]
}
```

### Algorytm

1. Podziel przedział czasowy na kroki (precision)
2. Dla każdego kroku:
   - Oblicz pozycje wszystkich aktywnych satelitów
   - Porównaj dystanse między wszystkimi parami
   - Jeśli dystans < próg → zapisz zdarzenie
3. Zwróć listę wykrytych zdarzeń

---

## Modele danych

### Dataclasses

**WspolrzedneGeodezyjne** — współrzędne geograficzne:

```python
@dataclass
class WspolrzedneGeodezyjne:
    szer_geogr: float  # szerokość geograficzna [-90°, 90°]
    dlug_geogr: float  # długość geograficzna [-180°, 180°]
    wysokosc: float    # wysokość nad poziomem morza [km]
    
    def dystans_do(self, inne: 'WspolrzedneGeodezyjne') -> float:
        """Oblicza dystans 3D do innych współrzędnych"""
    
    def do_kartezjanskich(self) -> Tuple[float, float, float]:
        """Konwersja do współrzędnych kartezjańskich (x, y, z)"""
```

**ParametryOrbitalne** — parametry Keplerowskie:

```python
@dataclass
class ParametryOrbitalne:
    polOs_wielka: float        # wielka półoś [km]
    inklinacja_kat: float      # inklinacja [stopnie]
    wezl_wstepujacy: float     # RAAN [stopnie]
    
    def oblicz_okres_orbitalny(self) -> float:
        """Oblicza okres orbitalny T = 2π√(a³/μ) [sekundy]"""
```

### SQLAlchemy Models

**ModelOrbityBD** — orbita w bazie danych:

```python
class ModelOrbityBD(Base):
    __tablename__ = "orbity"
    
    id: int
    nazwa: str
    wysokosc_orbitalna: float  # km
    inklinacja: float          # stopnie
    raan: float                # stopnie
    data_utworzenia: datetime
```

**ModelObiektuBD** — satelita w bazie danych:

```python
class ModelObiektuBD(Base):
    __tablename__ = "obiekty"
    
    id: int
    nazwa: str
    operator: str
    data_startu: datetime
    status: TypObiektu
    dlugosc_poczatkowa: float  # stopnie
    orbita_id: int
    orbita: ModelOrbityBD      # relacja
```

### Pydantic Schemas

System używa 10 schematów Pydantic do walidacji:

- `SchematOrbitWejscie` / `SchematOrbitWyjscie`
- `SchematObiektuWejscie` / `SchematObiektuWyjscie`
- `SchematPozycjiWyjscie`
- `SchematListyOrbit` / `SchematListyObiektow`
- `SchematZdarzeniaKolizji` / `SchematListyKolizji`

**Przykład walidacji:**

```python
class SchematOrbitWejscie(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    orbital_altitude: float = Field(..., ge=160.0, le=40000.0)
    inclination: float = Field(..., ge=0.0, le=180.0)
    raan: float = Field(..., ge=0.0, lt=360.0)
```

---

## Testy

System posiada **25 testów funkcjonalnych** pokrywających wszystkie funkcjonalności.

### Uruchomienie testów

```bash
./test.sh
```

---

## Przykłady użycia

### Przykład 1: Śledzenie ISS

```python
import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

# Utworzenie orbity ISS
orbit = requests.post(f"{BASE_URL}/orbity/", json={
    "nazwa": "ISS-Orbit",
    "wysokosc": 408.0,
    "inklinacja": 51.6,
    "wezel": 45.0
}).json()

# Dodanie ISS
iss = requests.post(f"{BASE_URL}/satelity/", json={
    "nazwa": "ISS",
    "operator": "NASA/Roscosmos",
    "data_startu": "1998-11-20T00:00:00Z",
    "status": "active",
    "dlugosc_poczatkowa": 0.0,
    "id_orbity": orbit['id']
}).json()

# Śledzenie pozycji co 10 minut przez 2 godziny
start = datetime.utcnow()
for i in range(12):
    timestamp = (start + timedelta(minutes=10*i)).isoformat() + "Z"
    pos = requests.get(
        f"{BASE_URL}/satelity/{iss['id']}/pozycja",
        params={"timestamp": timestamp}
    ).json()
    
    print(f"T+{10*i:3d}min: lat={pos['lat']:6.2f}°, lon={pos['lon']:7.2f}°, alt={pos['alt']:.1f}km")
```

### Przykład 2: Monitoring konstelacji Starlink

```python
import requests

BASE_URL = "http://localhost:8000"

# Utworzenie orbity Starlink
orbit = requests.post(f"{BASE_URL}/orbity/", json={
    "nazwa": "Starlink-Shell-1",
    "wysokosc": 550.0,
    "inklinacja": 53.0,
    "wezel": 0.0
}).json()

# Dodanie 10 satelitów Starlink
satellites = []
for i in range(10):
    sat = requests.post(f"{BASE_URL}/satelity/", json={
        "nazwa": f"Starlink-{i+1}",
        "operator": "SpaceX",
        "data_startu": "2020-01-01T00:00:00Z",
        "status": "active",
        "dlugosc_poczatkowa": i * 36.0,  # Co 36° długości
        "id_orbity": orbit['id']
    }).json()
    satellites.append(sat)

print(f"Utworzono konstelację {len(satellites)} satelitów")

# Lista wszystkich satelitów
response = requests.get(f"{BASE_URL}/satelity/").json()
print(f"Razem satelitów w systemie: {response['total']}")
```

### Przykład 3: Analiza zbliżeń

```python
import requests

BASE_URL = "http://localhost:8000"

# Wykryj potencjalne zbliżenia w ciągu tygodnia
response = requests.get(f"{BASE_URL}/zblizenia", params={
    "start_date": "2020-01-01T00:00:00Z",
    "end_date": "2020-01-08T00:00:00Z",
    "precision": "1h"
}).json()

collisions = response.get('collisions', [])

if collisions:
    print(f"⚠️  Wykryto {len(collisions)} potencjalnych zbliżeń!")
    for col in collisions:
        print(f"  • Satelity {col['satellite1']} <-> {col['satellite2']}")
        print(f"    Czas: {col['time']}")
        print(f"    Pozycja: {col['position']['lat']:.2f}°, {col['position']['lon']:.2f}°")
else:
    print("✅ Brak wykrytych kolizji")
```

---

## Rozwiązywanie problemów

### Błąd: "ModuleNotFoundError"

**Przyczyna:** Brak zainstalowanych zależności.

**Rozwiązanie:**

```bash
# Zainstaluj wszystkie zależności
pip install -r requirements.txt
```

### Błąd: "Connection refused" na localhost:8000

**Przyczyna:** Serwer nie jest uruchomiony.

**Rozwiązanie:**

```bash
# Uruchom serwer
./run.sh

# Sprawdź czy działa
curl http://localhost:8000/status
```

### Błąd: "Invalid altitude" podczas tworzenia orbity

**Przyczyna:** Wysokość orbity poza dozwolonym zakresem (160-40,000 km).

**Rozwiązanie:**

```python
# ❌ Niepoprawne
{
  "wysokosc": 100.0  # Za nisko
}

# ✅ Poprawne
{
  "wysokosc": 400.0  # W zakresie 160-40,000 km
}
```

### Błąd: "Invalid timestamp format"

**Przyczyna:** Niepoprawny format czasu (wymagany ISO 8601 UTC).

**Rozwiązanie:**

```python
# ❌ Niepoprawne
"timestamp": "2024-06-15 12:00:00"

# ✅ Poprawne
"timestamp": "2024-06-15T12:00:00Z"
```

### Debug mode

```python
import logging

# Włączenie szczegółowych logów
logging.basicConfig(level=logging.DEBUG)

# Test API
import requests
response = requests.get("http://localhost:8000/status")
print(response.json())
```

### Testy systemu

```bash
# Uruchomienie wszystkich testów
./test.sh

# Oczekiwany wynik: 25/25 testów 
```

---

## Technologie

- **Python 3.13+** — język programowania
- **FastAPI 2.0** — framework REST API
- **SQLAlchemy** — ORM i zarządzanie bazą danych
- **Pydantic** — walidacja danych i schematy
- **dateutil** — parsowanie dat ISO 8601
- **Uvicorn** — serwer ASGI

---

## Stałe fizyczne

System wykorzystuje standardowe stałe astronomiczne:

- **μ (parametr grawitacyjny Ziemi)**: 398,600.4418 km³/s²
- **R (promień Ziemi)**: 6,371.0 km
- **Próg wykrywania kolizji**: 0.01 km (10 metrów)

---

## Wzorce projektowe

System wykorzystuje profesjonalne wzorce projektowe:

### Strategy Pattern

- **PropagatorOrbity** — abstrakcja dla różnych metod propagacji
- **PropagatorKeplerowski** — konkretna implementacja Keplerowska

### Service Layer

- **SerwisObliczenOrbitalalnych** — oddzielenie logiki biznesowej od API
- **SerwisAnalizyZdarzen** — modułowa analiza zdarzeń

### Repository Pattern

- **Warstwa dostępu do danych** — SQLAlchemy ORM
- **Abstrakcja bazy danych** — możliwość zmiany silnika DB bez zmian w logice

---

## Autor

### Aleks Czarnecki

System zaprojektowany z wykorzystaniem profesjonalnych wzorców projektowych i nowoczesnej architektury modułowej.

---

**Ostatnia aktualizacja**: 2025-10-04  
**Wersja**: 2.0.0  
