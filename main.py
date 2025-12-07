
import asyncio
import json
import threading
import time
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify
import websockets
import requests
from flask_cors import CORS
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

app = Flask(__name__)
cors_origins = ["*"]
CORS(app, origins=cors_origins)

# Конфигурация из .env
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", 2424))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
EXTERNAL_API_URL = os.getenv("EXTERNAL_API_URL", "https://24data.ptfs.app")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "default_event_token")
ATC_UPDATE_INTERVAL = int(os.getenv("ATC_UPDATE_INTERVAL", 10))
ATIS_UPDATE_INTERVAL = int(os.getenv("ATIS_UPDATE_INTERVAL", 30))
WEBSOCKET_UPDATE_INTERVAL = int(os.getenv("WEBSOCKET_UPDATE_INTERVAL", 5))
WEBSOCKET_URL = os.getenv("WEBSOCKET_URL", "wss://24data.ptfs.app/wss")

# Раздельные хранилища для обычных и ивентовых данных
dsr = {}  # Обычные рейсы
edsr = {}  # Ивентовые рейсы
flight_times = defaultdict(dict)
event_flight_times = defaultdict(dict)

# Раздельные хранилища ATC и ATIS
atc = []  # Обычные ATC (получаем из внешнего API)
eatc = []  # Ивентовые ATC (приходят POST запросом)
atis = {}  # Обычные ATIS (получаем из внешнего API)
eatis = {}  # Ивентовые ATIS (приходят POST запросом)

AIRPORTS = {
    "IRFD": {"name": "Greater Rockford", "city": "Rockford", "fir": "IRCC"},
    "ILAR": {"name": "Larnaca Intl.", "city": "Cyprus", "fir": "ICCC"},
    "IZOL": {"name": "Izolirani Intl.", "city": "Izolirani", "fir": "IZCC"},
    "ITKO": {"name": "Tokyo Intl.", "city": "Orenji", "fir": "IOCC"},
    "IPPH": {"name": "Perth Intl.", "city": "Perth", "fir": "IPCC"},
    "IGRV": {"name": "Grindavik Airport", "city": "Grindavik", "fir": "IGCC"},
    "IPAP": {"name": "Paphos Intl.", "city": "Cyprus", "fir": "ICCC"},
    "IMLR": {"name": "Mellor Intl.", "city": "Rockford", "fir": "IRCC"},
    "ISAU": {"name": "Sauthemptona", "city": "Sauthemptona", "fir": "ISCC"},
    "IBTH": {"name": "Saint Barthélemy", "city": "Saint Barthélemy", "fir": "IBCC"},
    "ILKL": {"name": "Lukla Airport", "city": "Perth", "fir": "IPCC"},
    "IDCS": {"name": "Saba Airport", "city": "Orenji", "fir": "IOCC"},
    "IBRD": {"name": "Bird Island", "city": "Orenji", "fir": "IOCC"},
    "IJAF": {"name": "Al Najaf", "city": "Izolirani", "fir": "IZCC"},
    "ITRC": {"name": "Training Centre", "city": "Rockford", "fir": "IRCC"},
    "IBAR": {"name": "Barra Airport", "city": "Cyprus", "fir": "ICCC"},
    "IBLT": {"name": "Boltic Airfield", "city": "Rockford", "fir": "IRCC"},
    "IIAB": {"name": "McConnell AFB", "city": "Cyprus", "fir": "ICCC"},
    "ISCM": {"name": "RAF Scampton", "city": "Izolirani", "fir": "IZCC"},
    "IHEN": {"name": "Henstridge Airfield", "city": "Cyprus", "fir": "ICCC"},
    "IGAR": {"name": "Air Base Garry", "city": "Rockford", "fir": "IRCC"},
    "ISKP": {"name": "Skopelos Airfield", "city": "Skopelos", "fir": "IBCC"}
}

AIRPORT_NAME_TO_ICAO = {
    "Rockford": "IRFD",
    "Larnaca": "ILAR",
    "Izolirani": "IZOL",
    "Tokyo": "ITKO",
    "Perth": "IPPH",
    "Grindavik": "IGRV",
    "Paphos": "IPAP",
    "Sauthemptona": "ISAU",
    "Mellor": "IMLR",
    "Saint Barthélemy": "IBTH",
    "Lukla": "ILKL",
    "Saba": "IDCS",
    "Al Najaf": "IJAF",
    "Training Centre": "ITRC",
    "Barra": "IBAR",
    "Boltic": "IBLT",
    "McConnell": "IIAB",
    "Scampton": "ISCM",
    "Henstridge": "IHEN",
    "Garry": "IGAR",
    "Skopelos": "ISKP",
    "Bird Island": "IBRD",
}

CTR_TO_ARPT = {
    'IRCC': "IRFD",
    'ICCC': "ILAR",
    'IZCC': "IZOL",
    'IOCC': "ITKO",
    'IPCC': "IPPH",
    'IBCC': "IBTH",
    'IGCC': "IGRV",
    'ISCC': "ISAU",
}

FREQ_LIST = {
    'IRCC_CTR': '124.850',
    'IRFD_TWR': '118.100',
    'IRFD_GND': '120.400',
    'IMLR_TWR': '133.850',
    'IGAR_TWR': '125.600',
    'IBLT_TWR': '120.250',
    'ITRC_TWR': '119.150',
    'ICCC_CTR': '126.300',
    'ILAR_TWR': '121.200',
    'ILAR_GND': '119.400',
    'IPAP_TWR': '119.900',
    'IIAB_TWR': '127.250',
    'IHEN_TWR': '130.250',
    'IBAR_TWR': '118.750',
    'IZCC_CTR': '125.650',
    'IZOL_TWR': '118.700',
    'IZOL_GND': '121.900',
    'IJAF_TWR': '119.100',
    'ISCM_TWR': '121.300',
    'IOCC_CTR': '132.300',
    'ITKO_TWR': '118.800',
    'ITKO_GND': '118.225',
    'IDCS_TWR': '118.250',
    'IBRD_TWR': '118.300',
    'IPCC_CTR': '135.250',
    'IPPH_TWR': '127.400',
    'IPPH_GND': '121.700',
    'ILKL_TWR': '120.150',
    'IBCC_CTR': '128.600',
    'IBTH_TWR': '118.700',
    'ISKP_TWR': '123.250',
    'IGCC_CTR': '126.750',
    'IGRV_TWR': '118.300',
    'ISCC_CTR': '127.825',
    'ISAU_TWR': '118.200'
}

AIRCRAFT_SHORT_NAMES = {
    "A10 Warthog":                  "A10",
    "An 225":                       "A225",
    "Airbus A320":                  "A320",
    "A330 MRTT":                    "A332",
    "Airbus A330":                  "A332",
    "Airbus A340":                  "A345",
    "Airbus A350":                  "A359",
    "Airbus A380":                  "A388",
    "Airbus Beluga":                "A3ST",
    "An22":                         "AN22",
    "ATR72":                        "AT76",
    "ATR72F":                       "AT76",
    "B1 Lancer":                    "B1",
    "B2 Spirit Bomber":             "B2",
    "B29 SuperFortress":            "B29",
    "Bell 412":                     "B412",
    "Bell 412 Rescue":              "B412",
    "707AF1":                       "B703",
    "Boeing 707":                   "B703",
    "KC-707":                       "B703",
    "Boeing 727":                   "B722",
    "Boeing 727 Cargo":             "B722",
    "C40":                          "B737",
    "Boeing 737":                   "B738",
    "Boeing 737 Cargo":             "B738",
    "747AF1":                       "B742",
    "Boeing 747":                   "B744",
    "Boeing 747 Cargo":             "B744",
    "Boeing 757":                   "B752",
    "Boeing 757 Cargo":             "B752",
    "C-32":                         "B752",
    "KC767":                        "B762",
    "Boeing 767":                   "B763",
    "Boeing 767 Cargo":             "B763",
    "Boeing 777 Cargo":             "B77L",
    "Boeing 777":                   "B77W",
    "Boeing 787":                   "B789",
    "Balloon":                      "BALL",
    "Airbus A220":                  "BCS1",
    "KingAir 260":                  "BE20",
    "DreamLifter":                  "BLCF",
    "C130 Hercules":                "C130",
    "EC-18B":                       "C135",
    "C17":                          "C17",
    "Cessna 172":                   "C172",
    "Cessna 172 Amphibian":         "C172",
    "Cessna 172 Student":           "C172",
    "Cessna 182":                   "C182",
    "Cessna 182 Amphibian":         "C182",
    "Cessna Caravan":               "C208",
    "Cessna Caravan Amphibian":     "C208",
    "Cessna Caravan Cargo":         "C208",
    "KC130J":                       "C30J",
    "Cessna 402":                   "C402",
    "Concorde":                     "CONC",
    "F4U Corsair":                  "CORS",
    "Bombardier CRJ700":            "CRJ7",
    "Diamond DA50":                 "DA50",
    "Bombardier Q400":              "DH8D",
    "DHC-6 Twin Otter":             "DHC6",
    "DHC-6 Twin Otter Amphibian":   "DHC6",
    "Fokker Dr1":                   "DR1",
    "E190":                         "E190",
    "Extra 300s":                   "E300",
    "E-3 Sentry":                   "E3TF",
    "H135":                         "EC35",
    "Eurofighter Typhoon":          "EUFI",
    "F14":                          "F14",
    "F15":                          "F15",
    "F16":                          "F16",
    "F/A-18 Super Hornet":          "F18S",
    "F22":                          "F22",
    "F35":                          "F35",
    "F4 Phantom":                   "F4",
    "BaggageTruck":                 "GRND",
    "BaggageTruckSmall":            "GRND",
    "Bus":                          "GRND",
    "CateringTruck":                "GRND",
    "FireTruck":                    "GRND",
    "FollowMeTruck":                "GRND",
    "FuelTruck":                    "GRND",
    "FuelTruckSmall":               "GRND",
    "PushBackBig":                  "GRND",
    "PushBackGreen":                "GRND",
    "PushBackSmall":                "GRND",
    "StairTruck":                   "GRND",
    "StairTruck737":                "GRND",
    "Chinook":                      "H47",
    "UH-60":                        "H60",
    "UH-60 Coast Guard":            "H60",
    "Harrier":                      "HAR",
    "Hawk T1":                      "HAWK",
    "Hurricane":                    "HURI",
    "Piper Cub":                    "J3",
    "Piper Cub Amphibian":          "J3",
    "KC-1":                         "L101",
    "Lockheed Tristar":             "L101",
    "Bombardier Learjet 45":        "LJ45",
    "English Electric Lightning":   "LTNG",
    "Douglas MD11":                 "MD11",
    "Douglas MD11 Cargo":           "MD11",
    "Douglas MD90":                 "MD90",
    "Mig-15":                       "MG15",
    "Piper PA28181":                "P28A",
    "P38 Lightning":                "P38",
    "P51 Mustang":                  "P51",
    "P8":                           "P8",
    "Paratrike":                    "PARA",
    "Sikorsky S92":                 "S92",
    "Sikorsky S92 Coast Guard":     "S92",
    "Gripen":                       "SB39",
    "Cirrus Vision":                "SF50",
    "Blimp":                        "SHIP",
    "CaravanBlimp":                 "SHIP",
    "Sled":                         "SLEI",
    "SR71 BlackBird":               "SR71",
    "SU27":                         "SU27",
    "SU57":                         "SU57",
    "Derek Plane":                  "ULAC",
    "Avro Vulcan":                  "VULC",
    "Wright Brothers Plane":        "WF",
    "A6M Zero":                     "ZERO",
    "Caproni Stipa":                "ZZZZ",
    "Might Walrus":                 "ZZZZ",
    "Rescue Boat":                  "ZZZZ",
    "UFO":                          "ZZZZ"
}

FLIGHT_STATES = {
    0: {"name": "Boarding", "icon": "boarding.png"},
    1: {"name": "Taxiing", "icon": "taxiing.png"},
    2: {"name": "Climbing", "icon": "departure.png"},
    3: {"name": "Cruising", "icon": "cruise.png"},
    4: {"name": "Descending", "icon": "arrival.png"},
    5: {"name": "Arrived", "icon": "ground.png"},
    6: {"name": "Training", "icon": "training.png"}
}

# Конфигурация
RECONNECT_DELAY = 2
DATA_TIMEOUT = timedelta(minutes=30)
LIVE_TIMEOUT = timedelta(seconds=10)


async def listen_websocket(uri):
    while True:
        try:
            print(f"Connecting to WebSocket at {uri}...")
            async with websockets.connect(uri) as websocket:
                print("WebSocket connected successfully!")
                while True:
                    try:
                        wss_data = await websocket.recv()
                        process_websocket_data(wss_data)
                    except websockets.exceptions.ConnectionClosed as e:
                        print(f"WebSocket connection closed: {e}")
                        break
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        break
        except Exception as e:
            print(f"WebSocket connection error: {e}")
            print(f"Reconnecting in {RECONNECT_DELAY} seconds...")
            await asyncio.sleep(RECONNECT_DELAY)


def process_websocket_data(wss_data):
    try:
        data = json.loads(wss_data) if isinstance(wss_data, str) else wss_data
        if not isinstance(data, dict):
            return

        received_at = datetime.now(timezone.utc)
        msg_type = data.get("t")
        msg_data = data.get("d", {})

        if msg_type == "ACFT_DATA":
            process_acft_data(msg_data, received_at=received_at)
        elif msg_type == "FLIGHT_PLAN":
            process_flight_plan(msg_data, received_at=received_at)
        elif msg_type == "EVENT_ACFT_DATA":
            process_acft_data(msg_data, event=True, received_at=received_at)
        elif msg_type == "EVENT_FLIGHT_PLAN":
            process_flight_plan(msg_data, event=True, received_at=received_at)

    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
    except Exception as e:
        print(f"Error processing WebSocket data: {e}")


def process_acft_data(data, event=False, received_at=None):
    if received_at is None:
        received_at = datetime.now(timezone.utc)

    unalive_flights(event)

    store = edsr if event else dsr
    times_store = event_flight_times if event else flight_times

    for realcallsign, flight_data in data.items():
        player_name = flight_data.get("playerName")
        if not player_name:
            continue

        callsign = None
        for cs, flight_info in store.items():
            if flight_info.get("player_name") == player_name:
                callsign = cs
                break

        if callsign is None:
            callsign = realcallsign
            if callsign not in store:
                store[callsign] = {}

        previous_state = store[callsign].get("state", 0)
        current_state = get_flight_state(callsign, flight_data, event=event)

        store[callsign].update({
            "realcallsign": realcallsign,
            "heading": flight_data.get("heading"),
            "player_name": player_name,
            "altitude": flight_data.get("altitude"),
            "aircraft": AIRCRAFT_SHORT_NAMES.get(
                flight_data.get("aircraftType"),
                flight_data.get("aircraftType")
            ),
            "pos_x": flight_data.get("position", {}).get("x"),
            "pos_y": flight_data.get("position", {}).get("y"),
            "speed": flight_data.get("speed"),
            "ground_speed": round(flight_data.get("groundSpeed", 0), 0),
            "wind": flight_data.get("wind"),
            "is_on_ground": flight_data.get("isOnGround", False),
            "live": True,
            "data_valid": True,
            "last_fresh_time": received_at,
            "state": current_state,
            "previous_state": previous_state,
            "is_emergency": flight_data.get("isEmergencyOccuring", False),
            "cs": store[callsign].get("cs", realcallsign)
        })

        # Трекинг времени для обычных рейсов
        if not event:
            track_flight_times(callsign, store[callsign], received_at, previous_state, current_state)


def process_flight_plan(data, event=False, received_at=None):
    if received_at is None:
        received_at = datetime.now(timezone.utc)

    player_name = data.get("robloxName")
    callsign_from_fpl = data.get("callsign")
    realcallsign = data.get("realcallsign")

    if not player_name:
        return

    store = edsr if event else dsr
    times_store = event_flight_times if event else flight_times

    existing_callsign = None
    for cs, flight_info in store.items():
        if flight_info.get("player_name") == player_name:
            existing_callsign = cs
            break

    if existing_callsign:
        callsign = existing_callsign
        for field in ["departure", "arrival", "flight_level", "flightrules", "route"]:
            if field in store[callsign]:
                del store[callsign][field]
    else:
        callsign = callsign_from_fpl if callsign_from_fpl else realcallsign
        if callsign not in store:
            store[callsign] = {}

    flight_level = 0
    try:
        fl_str = data.get("flightlevel", "FL0").replace("FL", "").lstrip("0")
        flight_level = 100 * int(fl_str) if fl_str else 0
    except (ValueError, AttributeError):
        flight_level = 0

    store[callsign].update({
        "realcallsign": realcallsign,
        "fpl_created_time": received_at.strftime("%H:%M") + "z",
        "departure": data.get("departing", "ZZZZ"),
        "arrival": data.get("arriving", "ZZZZ"),
        "flight_level": flight_level,
        "player_name": player_name,
        "aircraft": AIRCRAFT_SHORT_NAMES.get(data.get("aircraft"), data.get("aircraft")),
        "flightrules": data.get("flightrules"),
        "route": data.get("route", "N/A"),
        "data_valid": False,
        "live": False,
        "last_fresh_time": received_at,
        "state": 0,
        "previous_state": 0,
        "is_emergency": data.get("isEmergencyOccuring", False),
        "cs": callsign_from_fpl if callsign_from_fpl else realcallsign
    })

    if callsign not in times_store:
        times_store[callsign] = {}

    times_store[callsign].update({
        "fpl_created": received_at,
        "last_update": received_at,
    })


def track_flight_times(callsign, flight_data, received_at, previous_state, current_state):
    """Трекинг времени для рейсов"""
    if callsign not in flight_times:
        flight_times[callsign] = {}

    # Фиксируем начало Off-Block (state 0 -> state 1)
    if current_state == 1 and previous_state == 0:
        if "obt_start" not in flight_times[callsign]:
            flight_times[callsign]["obt_start"] = received_at
            print(f"⏱️ {callsign}: Off-Block started at {received_at.strftime('%H:%M:%S')}")

    # Фиксируем начало Taxi (state 1 -> state 2 или выше)
    elif current_state >= 2 and previous_state == 1:
        if "taxi_start" not in flight_times[callsign]:
            flight_times[callsign]["taxi_start"] = received_at
            print(f"🚕 {callsign}: Taxi started at {received_at.strftime('%H:%M:%S')}")

            # Если OBT ещё не зафиксирован, фиксируем его тоже
            if "obt_start" not in flight_times[callsign]:
                flight_times[callsign]["obt_start"] = received_at


def get_flight_state(callsign, flight_data, event=False):
    store = edsr if event else dsr
    data = store.get(callsign, {})

    is_on_ground = flight_data.get("isOnGround", False)
    speed = flight_data.get("speed", 0)
    altitude = flight_data.get("altitude", 0)
    previous_state = data.get("state", 0)
    departure = data.get("departure", "")
    arrival = data.get("arrival", "")

    cruise_altitude = 25000
    is_training_flight = departure and departure == arrival

    if not is_on_ground and is_training_flight:
        return 6

    if is_on_ground and speed < 5 and previous_state in {2, 3, 4}:
        return 5

    if is_on_ground and speed >= 5 and speed < 50:
        return 1

    if is_on_ground and speed < 5 and previous_state not in {2, 3, 4, 5}:
        return 0

    if not is_on_ground and previous_state in {0, 1}:
        return 2

    if not is_on_ground and previous_state in {2, 3} and speed < 300:
        return 4

    if not is_on_ground and altitude >= cruise_altitude:
        return 3

    return previous_state


def unalive_flights(event=False):
    current_time = datetime.now(timezone.utc)
    store = edsr if event else dsr

    for callsign, data in store.items():
        if data.get("live") and data.get("last_fresh_time"):
            if current_time - data["last_fresh_time"] > LIVE_TIMEOUT:
                data["live"] = False


def cleanup_old_data():
    current_time = datetime.now(timezone.utc)

    # Очистка обычных данных
    for store, times_store in [(dsr, flight_times), (edsr, event_flight_times)]:
        to_delete = [
            callsign
            for callsign, data in store.items()
            if data.get("last_fresh_time")
               and (current_time - data["last_fresh_time"]) > DATA_TIMEOUT
        ]

        for callsign in to_delete:
            del store[callsign]
            if callsign in times_store:
                del times_store[callsign]
                print(f"🧹 Удалены устаревшие данные для {callsign}")

    # Очистка устаревших flight_times
    for times_store in [flight_times, event_flight_times]:
        times_to_delete = [
            callsign
            for callsign, times in times_store.items()
            if "fpl_created" in times and (current_time - times["fpl_created"]) > timedelta(hours=2)
        ]

        for callsign in times_to_delete:
            del times_store[callsign]


def calculate_airport_stats(event=False):
    """Расчёт статистики аэропортов"""
    airport_stats = defaultdict(lambda: {"taxi_times": [], "obt_times": []})
    current_time = datetime.now(timezone.utc)
    one_hour_ago = current_time - timedelta(hours=1)

    store = edsr if event else dsr
    times_store = event_flight_times if event else flight_times

    for callsign, times in times_store.items():
        if callsign not in store:
            continue

        # Пропускаем старые данные (старше 1 часа)
        if "fpl_created" in times and times["fpl_created"] < one_hour_ago:
            continue

        departure = store[callsign].get("departure")
        if not departure:
            continue

        # Расчёт Off-Block Time (OBT) - время от подачи плана до начала движения (state 0 -> state 1)
        if "fpl_created" in times and "obt_start" in times:
            obt_time = (times["obt_start"] - times["fpl_created"]).total_seconds() / 60
            if 0 < obt_time < 120:  # От 0 до 120 минут
                airport_stats[departure]["obt_times"].append(obt_time)

        # Расчёт Taxi Time - время от начала движения до взлета (state 1 -> state 2)
        if "taxi_start" in times:
            # Нужно время когда рейс взлетел (state >= 2)
            # Пока просто используем текущее время если рейс уже в state >= 2
            current_state = store[callsign].get("state", 0)
            if current_state >= 2:
                # Для простоты используем время последнего обновления
                taxi_time = (times.get("last_update", current_time) - times["taxi_start"]).total_seconds() / 60
                if 0 < taxi_time < 60:  # От 0 до 60 минут
                    airport_stats[departure]["taxi_times"].append(taxi_time)

    return airport_stats


def get_active_arpts(event=False):
    """Получение активных аэропортов"""
    active = set()
    store = edsr if event else dsr

    for callsign, data in store.items():
        if data.get('departure') and data.get('arrival'):
            dep = data['departure']
            arr = data['arrival']
            if dep not in active:
                active.add(dep)
            if arr not in active:
                active.add(arr)
    return active


def fetch_external_atc_data():
    """Получение обычных ATC данных из внешнего API (GET запрос)"""
    try:
        url = f"{EXTERNAL_API_URL}/controllers"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        controllers = response.json()

        active_arpt = get_active_arpts(event=False)
        active_firs = []
        filtered_controllers = []

        for controller in controllers:
            arpt = CTR_TO_ARPT.get(controller.get("airport"), controller.get("airport", 'ZZZZ'))

            if controller['position'] == 'CTR':
                fir_code = AIRPORTS[arpt].get('fir', 'ZZZZ')
                position_name = fir_code + '_CTR'
                active_firs.append(fir_code)
            else:
                position_name = arpt + '_' + controller.get('position', 'ZZZ')

            active_arpt.add(arpt)

            filtered_controllers.append({
                "holder": controller.get("holder"),
                "airport": arpt,
                "position": controller.get('position', 'ZZZ'),
                "queue": controller.get("queue", []),
                "frequency": FREQ_LIST.get(position_name, 'ZZZ.ZZZ'),
                "position_name": position_name
            })

        for arpt in list(active_arpt):
            if arpt not in 'ISAU IGRV ITKO IPPH IZOL IBTH ILAR IRFD'.split():
                fir_code = AIRPORTS[arpt].get('fir', 'ZZZZ')

                if fir_code in active_firs:
                    ctr_controller = None
                    for controller in controllers:
                        if controller['position'] == 'CTR':
                            ctr_arpt = CTR_TO_ARPT.get(controller.get("airport"),
                                                       controller.get("airport", 'ZZZZ'))
                            if AIRPORTS[ctr_arpt].get('fir', 'ZZZZ') == fir_code:
                                ctr_controller = controller
                                break

                    if ctr_controller:
                        position_name = fir_code + '_CTR'
                        filtered_controllers.append({
                            "holder": ctr_controller.get("holder"),
                            "airport": arpt,
                            "position": 'CTR',
                            "queue": ctr_controller.get("queue", []),
                            "frequency": FREQ_LIST.get(position_name, 'ZZZ.ZZZ'),
                            "position_name": position_name
                        })

        position_priority = {'CTR': 0, 'TWR': 1, 'GND': 2}

        def sort_key(controller):
            pos = controller['position']
            priority = position_priority.get(pos, 99)
            return priority, controller['airport']

        filtered_controllers.sort(key=sort_key)

        global atc
        atc = filtered_controllers
        print(f"External ATC data updated: {len(atc)} controllers")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching external ATC data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error parsing external ATC data: {e}")
    except Exception as e:
        print(f"Unexpected error in fetch_external_atc_data: {e}")
        import traceback
        traceback.print_exc()


def fetch_external_atis_data():
    """Получение обычных ATIS данных из внешнего API (GET запрос)"""
    try:
        url = f"{EXTERNAL_API_URL}/atis"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        atis_data = response.json()

        global atis
        atis = {item["airport"]: item for item in atis_data if "airport" in item}
        print(f"External ATIS data updated: {len(atis)} airports")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching external ATIS data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error parsing external ATIS data: {e}")
    except Exception as e:
        print(f"Unexpected error in fetch_external_atis_data: {e}")
        import traceback
        traceback.print_exc()


def run_updater():
    """Обновление внешних данных"""
    atc_counter = 0
    atis_counter = 0

    while True:
        # Обновляем ATC каждые ATC_UPDATE_INTERVAL секунд
        if atc_counter % ATC_UPDATE_INTERVAL == 0:
            fetch_external_atc_data()

        # Обновляем ATIS каждые ATIS_UPDATE_INTERVAL секунд
        if atis_counter % ATIS_UPDATE_INTERVAL == 0:
            fetch_external_atis_data()

        atc_counter += 1
        atis_counter += 1
        time.sleep(1)


def check_auth():
    """Проверка авторизации для POST запросов"""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False

    # Проверяем Bearer token
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        return token == AUTH_TOKEN

    return False


@app.route("/")
def index():
    """Главная страница (обычная версия)"""
    try:
        with open('web.html', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "Error: web.html file not found", 404
    except Exception as e:
        return f"Error loading web page: {str(e)}", 500


@app.route("/event/")
def index_event():
    """Страница ивентов"""
    try:
        with open('webevent.html', 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return "Error: webevent.html file not found", 404
    except Exception as e:
        return f"Error loading web page: {str(e)}", 500


# API эндпоинты для обычных данных (GET запросы к внешнему API)
@app.route('/api/v1/dsr')
def api_v1_dsr():
    """API для обычных рейсов"""
    try:
        return json.dumps(dsr, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/atc')
def api_v1_atc():
    """API для обычных ATC"""
    try:
        return json.dumps(atc, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/airport_stats')
def api_v1_airport_stats():
    """API для статистики аэропортов (обычные)"""
    try:
        stats = calculate_airport_stats(event=False)
        return json.dumps(stats, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/atis')
def api_v1_atis():
    """API для обычных ATIS"""
    try:
        return json.dumps(atis, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


# API эндпоинты для ивентовых данных (приходят через WebSocket)
@app.route('/api/v1/edsr')
def api_v1_edsr():
    """API для ивентовых рейсов"""
    try:
        return json.dumps(edsr, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/eatc')
def api_v1_eatc():
    """API для ивентовых ATC"""
    try:
        return json.dumps(eatc, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/eairport_stats')
def api_v1_eairport_stats():
    """API для статистики аэропортов (ивенты)"""
    try:
        stats = calculate_airport_stats(event=True)
        return json.dumps(stats, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/eatis')
def api_v1_eatis():
    """API для ивентовых ATIS"""
    try:
        return json.dumps(eatis, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


# POST эндпоинты для приёма ивентовых данных (с авторизацией)
@app.route('/api/v1/event/atc', methods=['POST'])
def api_v1_event_atc():
    """POST endpoint для приёма ивентовых ATC данных"""
    try:
        # Проверка авторизации
        if not check_auth():
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        global eatc
        eatc = data

        print(f"Event ATC data received via POST: {len(eatc)} controllers")
        return jsonify({"status": "success", "count": len(eatc)}), 200

    except Exception as e:
        print(f"Error processing event ATC data: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/event/atis', methods=['POST'])
def api_v1_event_atis():
    """POST endpoint для приёма ивентовых ATIS данных"""
    try:
        # Проверка авторизации
        if not check_auth():
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        global eatis
        eatis = {item["airport"]: item for item in data if "airport" in item}

        print(f"Event ATIS data received via POST: {len(eatis)} airports")
        return jsonify({"status": "success", "count": len(eatis)}), 200

    except Exception as e:
        print(f"Error processing event ATIS data: {e}")
        return jsonify({"error": str(e)}), 500


def run_websocket_client():
    """Запуск WebSocket клиента"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_websocket(WEBSOCKET_URL))


def run_cleanup_loop():
    """Запуск цикла очистки старых данных"""
    while True:
        cleanup_old_data()
        time.sleep(60)


if __name__ == "__main__":
    # Запуск WebSocket клиента в фоновом потоке
    ws_thread = threading.Thread(target=run_websocket_client)
    ws_thread.daemon = True
    ws_thread.start()

    # Запуск очистки старых данных
    cleanup_thread = threading.Thread(target=run_cleanup_loop)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    # Запуск обновления внешних данных
    updater_thread = threading.Thread(target=run_updater)
    updater_thread.daemon = True
    updater_thread.start()

    print(f"Starting Flask application on {FLASK_HOST}:{FLASK_PORT}...")
    print(f"Debug mode: {DEBUG}")
    print(f"External API: {EXTERNAL_API_URL}")
    print(f"Auth token: {'*' * len(AUTH_TOKEN) if AUTH_TOKEN else 'Not set'}")

    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=DEBUG)