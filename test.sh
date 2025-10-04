#!/bin/bash

BASE_URL="http://127.0.0.1:8001"
PASS=0
FAIL=0

test_endpoint() {
    local name="$1"
    local cmd="$2"
    local expected="$3"
    
    echo -n "Testing: $name ... "
    result=$(eval "$cmd" 2>&1)
    
    if echo "$result" | grep -q "$expected"; then
        echo " PASS"
        PASS=$((PASS + 1))
    else
        echo " FAIL"
        echo "  Expected: $expected"
        echo "  Got: $result"
        FAIL=$((FAIL + 1))
    fi
}

echo "========================================="
echo "FINALNY TEST SYSTEMU"
echo "========================================="
echo ""

# Restart bazy (czysta baza dla testów)
echo "Przygotowanie środowiska testowego..."
pkill -f "uvicorn satelity_api:system_api" 2>/dev/null
sleep 1
.venv/bin/uvicorn satelity_api:system_api --host 127.0.0.1 --port 8001 --log-level error > /dev/null 2>&1 &
UVICORN_PID=$!
sleep 3
echo ""

echo "CZĘŚĆ 1: Testy Podstawowe"
echo "-----------------------------------"
test_endpoint "Health Check" \
    "curl -s $BASE_URL/health" \
    "healthy"

test_endpoint "Root Endpoint" \
    "curl -s $BASE_URL/" \
    "System Śledzenia"

echo ""
echo "CZĘŚĆ 2: CRUD Orbit"
echo "-----------------------------------"

# Tworzenie orbit
test_endpoint "Create Orbit 1" \
    "curl -s -X POST $BASE_URL/orbity/ -H 'Content-Type: application/json' -d '{\"nazwa\":\"TEST-LEO\",\"wysokosc\":550,\"inklinacja\":51.6,\"wezel\":90}'" \
    '"id"'

test_endpoint "Create Orbit 2" \
    "curl -s -X POST $BASE_URL/orbity/ -H 'Content-Type: application/json' -d '{\"nazwa\":\"TEST-MEO\",\"wysokosc\":20000,\"inklinacja\":55,\"wezel\":45}'" \
    '"id"'

test_endpoint "List Orbits" \
    "curl -s $BASE_URL/orbity/" \
    '"razem"'

test_endpoint "Get Orbit by ID" \
    "curl -s $BASE_URL/orbity/1" \
    "TEST-LEO"

test_endpoint "Update Orbit" \
    "curl -s -X PUT $BASE_URL/orbity/1 -H 'Content-Type: application/json' -d '{\"nazwa\":\"TEST-LEO-UPDATED\",\"wysokosc\":560,\"inklinacja\":51.6,\"wezel\":90}'" \
    "TEST-LEO-UPDATED"

echo ""
echo "CZĘŚĆ 3: CRUD Satelitów"
echo "-----------------------------------"

test_endpoint "Create Satellite 1" \
    "curl -s -X POST $BASE_URL/satelity/ -H 'Content-Type: application/json' -d '{\"nazwa\":\"SAT-A\",\"operator\":\"TestOrg\",\"data_startu\":\"2020-01-01T00:00:00Z\",\"status\":\"active\",\"dlugosc_poczatkowa\":0,\"id_orbity\":1}'" \
    '"id"'

test_endpoint "Create Satellite 2" \
    "curl -s -X POST $BASE_URL/satelity/ -H 'Content-Type: application/json' -d '{\"nazwa\":\"SAT-B\",\"operator\":\"TestOrg\",\"data_startu\":\"2020-01-01T00:00:00Z\",\"status\":\"active\",\"dlugosc_poczatkowa\":10,\"id_orbity\":1}'" \
    '"id"'

test_endpoint "List Satellites" \
    "curl -s $BASE_URL/satelity/" \
    '"razem"'

test_endpoint "Get Satellite by ID" \
    "curl -s $BASE_URL/satelity/1" \
    "SAT-A"

test_endpoint "Update Satellite" \
    "curl -s -X PUT $BASE_URL/satelity/1 -H 'Content-Type: application/json' -d '{\"nazwa\":\"SAT-A-UPDATED\",\"operator\":\"TestOrg\",\"data_startu\":\"2020-01-01T00:00:00Z\",\"status\":\"active\",\"dlugosc_poczatkowa\":0,\"id_orbity\":1}'" \
    'SAT-A-UPDATED'

echo ""
echo "CZĘŚĆ 4: Obliczenia Orbitalne"
echo "-----------------------------------"

test_endpoint "Calculate Position (2024)" \
    "curl -s '$BASE_URL/satelity/1/pozycja?timestamp=2024-06-15T12:00:00Z'" \
    '"szerokosc"'

test_endpoint "Calculate Position (2025)" \
    "curl -s '$BASE_URL/satelity/2/pozycja?timestamp=2025-01-01T00:00:00Z'" \
    '"dlugosc"'

echo ""
echo "CZĘŚĆ 5: Detekcja Zbliżeń"
echo "-----------------------------------"

test_endpoint "Detect Collisions" \
    "curl -s '$BASE_URL/zblizenia?start_date=2020-01-01T00:00:00Z&end_date=2025-06-30T00:00:00Z'" \
    'zblizenia'

echo ""
echo "CZĘŚĆ 6: Walidacja i Błędy"
echo "-----------------------------------"

test_endpoint "Invalid Altitude (too low)" \
    "curl -s -X POST $BASE_URL/orbity/ -H 'Content-Type: application/json' -d '{\"nazwa\":\"INVALID\",\"wysokosc\":50,\"inklinacja\":51.6,\"wezel\":90}'" \
    '"detail"'

test_endpoint "Invalid Inclination" \
    "curl -s -X POST $BASE_URL/orbity/ -H 'Content-Type: application/json' -d '{\"nazwa\":\"INVALID2\",\"wysokosc\":550,\"inklinacja\":200,\"wezel\":90}'" \
    '"detail"'

test_endpoint "Duplicate Orbit Name" \
    "curl -s -X POST $BASE_URL/orbity/ -H 'Content-Type: application/json' -d '{\"nazwa\":\"TEST-LEO-UPDATED\",\"wysokosc\":550,\"inklinacja\":51.6,\"wezel\":90}'" \
    '"detail"'

test_endpoint "Non-existent Orbit" \
    "curl -s $BASE_URL/orbity/99999" \
    "not found"

test_endpoint "Non-existent Satellite" \
    "curl -s $BASE_URL/satelity/99999" \
    "not found"

echo ""
echo "CZĘŚĆ 7: Usuwanie Zasobów"
echo "-----------------------------------"

test_endpoint "Delete Satellite" \
    "curl -s -X DELETE $BASE_URL/satelity/2 -o /dev/null -w '%{http_code}'" \
    "204"

test_endpoint "Verify Deletion" \
    "curl -s $BASE_URL/satelity/2" \
    "not found"

test_endpoint "Delete Orbit (with satellites)" \
    "curl -s -X DELETE $BASE_URL/orbity/1" \
    "detail"

echo ""
echo "CZĘŚĆ 8: Paginacja"
echo "-----------------------------------"

test_endpoint "Pagination (skip=0, limit=1)" \
    "curl -s '$BASE_URL/satelity/?skip=0&limit=1'" \
    'limit'

test_endpoint "Pagination (skip=1, limit=1)" \
    "curl -s '$BASE_URL/satelity/?skip=1&limit=1'" \
    'pomin'

echo ""
echo "========================================="
echo "WYNIKI KOŃCOWE"
echo "========================================="
echo " Testy zaliczone: $PASS"
echo " Testy niezaliczone: $FAIL"
echo " Razem: $((PASS + FAIL))"
echo ""

if [ $FAIL -eq 0 ]; then
    echo " WSZYSTKIE TESTY ZALICZONE!"
    echo " System działa w 100% poprawnie"
    EXIT_CODE=0
else
    echo " Wykryto błędy w systemie"
    EXIT_CODE=1
fi

# Cleanup
echo ""
echo "Test zakończony."
pkill -f "uvicorn satelity_api:system_api" 2>/dev/null || true
