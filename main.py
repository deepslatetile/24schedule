import asyncio
import json
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from flask import Flask
import websockets
import requests
from flask_cors import CORS

app = Flask(__name__)
cors_origins = ["https://two4schedule.onrender.com", "http://localhost:*", "http://127.0.0.1:*"]
CORS(app, origins=cors_origins)

# Global data stores
dsr = {}  # Основное хранилище рейсов
edsr = {}  # Хранилище event рейсов
flight_times = defaultdict(dict)
atc = {}

AIRPORTS = {
	"IRFD": {"name": "Greater Rockford", "city": "Rockford"},
	"ILAR": {"name": "Larnaca Intl.", "city": "Cyprus"},
	"IZOL": {"name": "Izolirani Intl.", "city": "Izolirani"},
	"ITKO": {"name": "Tokyo Intl.", "city": "Orenji"},
	"IPPH": {"name": "Perth Intl.", "city": "Perth"},
	"IGRV": {"name": "Grindavik Airport", "city": "Grindavik"},
	"IPAP": {"name": "Paphos Intl.", "city": "Cyprus"},
	"IMLR": {"name": "Mellor Intl.", "city": "Rockford"},
	"ISAU": {"name": "Sauthemptona", "city": "Sauthemptona"},
	"IBTH": {"name": "Saint Barthélemy", "city": "Saint Barthélemy"},
	"ILKL": {"name": "Lukla Airport", "city": "Perth"},
	"IDCS": {"name": "Saba Airport", "city": "Orenji"},
	"IJAF": {"name": "Al Najaf", "city": "Izolirani"},
	"ITRC": {"name": "Training Centre", "city": "Rockford"},
	"IBAR": {"name": "Barra Airport", "city": "Cyprus"},
	"IBLT": {"name": "Boltic Airfield", "city": "Rockford"},
	"IIAB": {"name": "McConnell AFB", "city": "Cyprus"},
	"ISCM": {"name": "RAF Scampton", "city": "Izolirani"},
	"IHEN": {"name": "Henstridge Airfield", "city": "Cyprus"},
	"IGAR": {"name": "Air Base Garry", "city": "Rockford"},
	"ISKP": {"name": "Skopelos Airfield", "city": "Skopelos"}
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
	"Skopelos": "ISKP"
}

ARPT_TO_CTR = {
	'IRFD': "IRCC",
	'IMLR': "IRCC",
	'IGAR': "IRCC",
	'IBLT': "IRCC",
	'ITRC': "IRCC",
	'ILAR': "ICCC",
	'IPAP': "ICCC",
	'IIAB': "ICCC",
	'IHEN': "ICCC",
	'IBAR': "ICCC",
	'IZOL': "IZCC",
	'IJAF': "IZCC",
	'ISCM': "IZCC",
	'ITKO': "IOCC",
	'IDCS': "IOCC",
	'IPPH': "IPCC",
	'ILKL': "IPCC",
	'IBTH': "IBCC",
	'ISKP': "IBCC",
	'IGRV': "IGCC",
	'ISAU': "ISCC",
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
	"A10 Warthog": "A10",
	"An 225": "A225",
	"Airbus A320": "A320",
	"A330 MRTT": "A332",
	"Airbus A330": "A333",
	"Airbus A340": "A343",
	"Airbus A350": "A359",
	"Airbus A380": "A388",
	"Airbus Beluga": "A3ST",
	"An22": "AN22",
	"ATR72": "AT76",
	"ATR72F": "AT76",
	"B1 Lancer": "B1",
	"B2 Spirit Bomber": "B2",
	"B29 SuperFortress": "B29",
	"Bell 412": "B412",
	"Bell 412 Rescue": "B412",
	"707AF1": "B703",
	"Boeing 707": "B703",
	"KC-707": "B703",
	"Boeing 727": "B722",
	"Boeing 727 Cargo": "B722",
	"C40": "B737",
	"Boeing 737": "B738",
	"Boeing 737 Cargo": "B738",
	"747AF1": "B742",
	"Boeing 747": "B744",
	"Boeing 747 Cargo": "B744",
	"Boeing 757": "B752",
	"Boeing 757 Cargo": "B752",
	"C-32": "B752",
	"KC767": "B762",
	"Boeing 767": "B763",
	"Boeing 767 Cargo": "B763",
	"Boeing 777 Cargo": "B77L",
	"Boeing 777": "B77W",
	"Boeing 787": "B789",
	"Balloon": "BALL",
	"Airbus A220": "BCS1",
	"KingAir 260": "BE20",
	"DreamLifter": "BLCF",
	"C130 Hercules": "C130",
	"EC-18B": "C135",
	"C17": "C17",
	"Cessna 172": "C172",
	"Cessna 172 Amphibian": "C172",
	"Cessna 172 Student": "C172",
	"Cessna 182": "C182",
	"Cessna 182 Amphibian": "C182",
	"Cessna Caravan": "C208",
	"Cessna Caravan Amphibian": "C208",
	"Cessna Caravan Cargo": "C208",
	"KC130J": "C30J",
	"Cessna 402": "C402",
	"Concorde": "CONC",
	"Diamond DA50": "DA50",
	"F4U Corsair": "CORS",
	"Bombardier CRJ700": "CRJ7",
	"Bombardier Q400": "DH8D",
	"DHC-6 Twin Otter": "DHC6",
	"DHC-6 Twin Otter Amphibian": "DHC6",
	"Fokker Dr1": "DR1",
	"E190": "E190",
	"Extra 300s": "E300",
	"E-3 Sentry": "E3TF",
	"H135": "EC35",
	"Eurofighter Typhoon": "EUFI",
	"F14": "F14",
	"F15": "F15",
	"F16": "F16",
	"F/A-18 Super Hornet": "F18S",
	"F22": "F22",
	"F35": "F35",
	"F4 Phantom": "F4",
	"BaggageTruck": "GRND",
	"BaggageTruckSmall": "GRND",
	"Bus": "GRND",
	"CateringTruck": "GRND",
	"FireTruck": "GRND",
	"FollowMeTruck": "GRND",
	"FuelTruck": "GRND",
	"FuelTruckSmall": "GRND",
	"PushBackBig": "GRND",
	"PushBackGreen": "GRND",
	"PushBackSmall": "GRND",
	"StairTruck": "GRND",
	"StairTruck737": "GRND",
	"Chinook": "H47",
	"UH-60": "H60",
	"UH-60 Coast Guard": "H60",
	"Harrier": "HAR",
	"Hawk T1": "HAWK",
	"Hurricane": "HURI",
	"Piper Cub": "J3",
	"Piper Cub Amphibian": "J3",
	"KC-1": "L101",
	"Lockheed Tristar": "L101",
	"Bombardier Learjet 45": "LJ45",
	"English Electric Lightning": "LTNG",
	"Douglas MD11": "MD11",
	"Douglas MD11 Cargo": "MD11",
	"Douglas MD90": "MD90",
	"Mig-15": "MG15",
	"Piper PA28181": "P28A",
	"P38 Lightning": "P38",
	"P51 Mustang": "P51",
	"P8": "P8",
	"Paratrike": "PARA",
	"Sikorsky S92": "S92",
	"Sikorsky S92 Coast Guard": "S92",
	"Gripen": "SB39",
	"Cirrus Vision": "SF50",
	"Blimp": "SHIP",
	"CaravanBlimp": "SHIP",
	"Sled": "SLEI",
	"SR71 BlackBird": "SR71",
	"SU27": "SU27",
	"SU57": "SU57",
	"Derek Plane": "ULAC",
	"Avro Vulcan": "VULC",
	"Wright Brothers Plane": "WF",
	"A6M Zero": "ZERO",
	"Caproni Stipa": "ZZZZ",
	"Might Walrus": "YYYY",
	"Rescue Boat": "ZZZZ",
	"UFO": "ZZZZ"
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

# WebSocket configuration
WEBSOCKET_URL = "wss://24data.ptfs.app/wss"
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

		# print(dsr)

	except json.JSONDecodeError as e:
		print(f"JSON decode error: {e}")
	except Exception as e:
		print(f"Error processing WebSocket data: {e}")


def process_acft_data(data, event=False, received_at=None):
	if received_at is None:
		received_at = datetime.now(timezone.utc)

	unalive_flights(event)

	store = edsr if event else dsr

	for realcallsign, flight_data in data.items():
		player_name = flight_data.get("playerName")
		if not player_name:
			continue

		# Ищем существующий рейс по имени игрока
		callsign = None
		for cs, flight_info in store.items():
			if flight_info.get("player_name") == player_name:
				callsign = cs
				break

		# Если рейс не найден, создаем новый с realcallsign в качестве ключа
		if callsign is None:
			callsign = realcallsign
			if callsign not in store:
				store[callsign] = {}

		# Сохраняем предыдущее состояние для отслеживания изменений
		previous_state = store[callsign].get("state", 0)

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
			"state": get_flight_state(callsign, flight_data, event=event),
			"previous_state": previous_state,
			# Сохраняем отображаемый callsign, если он уже есть в данных
			"cs": store[callsign].get("cs", realcallsign)
		})

		if not event:
			track_flight_times(callsign, store[callsign], received_at)


def process_flight_plan(data, event=False, received_at=None):
	if received_at is None:
		received_at = datetime.now(timezone.utc)

	player_name = data.get("robloxName")
	callsign_from_fpl = data.get("callsign")
	realcallsign = data.get("realcallsign")

	if not player_name:
		return

	store = edsr if event else dsr

	# Ищем существующий рейс по имени игрока
	existing_callsign = None
	for cs, flight_info in store.items():
		if flight_info.get("player_name") == player_name:
			existing_callsign = cs
			break

	# Если рейс найден, используем его callsign, иначе создаем новый
	if existing_callsign:
		callsign = existing_callsign
		# Очищаем старые данные флайтплана
		if "departure" in store[callsign]:
			del store[callsign]["departure"]
		if "arrival" in store[callsign]:
			del store[callsign]["arrival"]
		if "flight_level" in store[callsign]:
			del store[callsign]["flight_level"]
		if "flightrules" in store[callsign]:
			del store[callsign]["flightrules"]
		if "route" in store[callsign]:
			del store[callsign]["route"]
	else:
		# Создаем новый рейс, используя callsign из флайтплана или realcallsign
		callsign = callsign_from_fpl if callsign_from_fpl else realcallsign
		if callsign not in store:
			store[callsign] = {}

	# Парсим flight level
	flight_level = 0
	try:
		fl_str = data.get("flightlevel", "FL0").replace("FL", "").lstrip("0")
		flight_level = 100 * int(fl_str) if fl_str else 0
	except (ValueError, AttributeError):
		flight_level = 0

	# Обновляем данные рейса
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
		"cs": callsign_from_fpl if callsign_from_fpl else realcallsign  # Отображаемый позывной
	})

	# Инициализируем tracking times
	if callsign not in flight_times:
		flight_times[callsign] = {}

	# Всегда обновляем время создания флайтплана
	flight_times[callsign].update({
		"fpl_created": received_at,
		"last_update": received_at,
	})


def track_flight_times(callsign, flight_data, received_at):
	if callsign not in dsr:
		return

	current_state = flight_data.get("state", 0)
	previous_state = flight_data.get("previous_state", 0)

	# Переход на state 1 (Taxiing) - начало руления
	if current_state == 1 and previous_state < 1:
		if "taxi_start" not in flight_times[callsign]:
			flight_times[callsign]["taxi_start"] = received_at

	# Переход на state 2 или выше (Climbing/Cruise) - взлет
	if current_state >= 2 and previous_state < 2:
		if "off_block_time" not in flight_times[callsign]:
			flight_times[callsign]["off_block_time"] = received_at
			# Если не было начала руления, но уже взлет - устанавливаем taxi_start как текущее время
			if "taxi_start" not in flight_times[callsign]:
				flight_times[callsign]["taxi_start"] = received_at


def get_flight_state(callsign, flight_data, event=False):
	store = edsr if event else dsr
	data = store.get(callsign, {})

	# Получаем текущие параметры полета
	is_on_ground = flight_data.get("isOnGround", False)
	speed = flight_data.get("speed", 0)
	altitude = flight_data.get("altitude", 0)
	previous_state = data.get("state", 0)
	departure = data.get("departure", "")
	arrival = data.get("arrival", "")

	# Определяем круизный эшелон (примерно 30,000 ft)
	cruise_altitude = 30000
	is_training_flight = departure and departure == arrival

	# Проверка на некорректное состояние (в небе, но state=5)
	if not is_on_ground and previous_state == 5:
		return 2  # Переводим в состояние Climbing

	# State 6 - Training (имеет приоритет над другими состояниями в небе)
	if not is_on_ground and is_training_flight:
		return 6

	# State 5 - Arrived (на земле, скорость < 10, был в небе)
	if is_on_ground and speed < 10 and previous_state in {2, 3, 4}:
		return 5

	# State 1 - Taxiing (на земле, скорость > 10)
	if is_on_ground and speed >= 10:
		return 1

	# State 0 - Boarding (на земле, скорость < 10, не был в небе)
	if is_on_ground and speed < 10 and previous_state not in {2, 3, 4, 5}:
		return 0

	# State 3 - Cruise (в небе, на круизном эшелоне)
	if not is_on_ground and altitude >= cruise_altitude:
		return 3

	# State 4 - Descending (в небе, ниже круизного эшелона, был на круизе или наборе)
	if not is_on_ground and altitude < cruise_altitude and previous_state in {2, 3}:
		return 4

	# State 2 - Climbing (в небе, был на рулении)
	if not is_on_ground and previous_state == 1:
		return 2

	# Если ни одно условие не подошло, возвращаем предыдущее состояние
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

	for store in [dsr, edsr]:
		to_delete = [
			callsign
			for callsign, data in store.items()
			if data.get("last_fresh_time")
			   and (current_time - data["last_fresh_time"]) > DATA_TIMEOUT
		]

		for callsign in to_delete:
			del store[callsign]
			if callsign in flight_times:
				del flight_times[callsign]


def calculate_airport_stats():
	airport_stats = defaultdict(lambda: {"taxi_times": [], "obt_times": []})
	current_time = datetime.now(timezone.utc)
	one_hour_ago = current_time - timedelta(hours=1)

	for callsign, times in flight_times.items():
		if callsign not in dsr:
			continue

		# Пропускаем рейсы старше 1 часа
		if "fpl_created" in times and times["fpl_created"] < one_hour_ago:
			continue

		departure = dsr[callsign].get("departure")
		if not departure:
			continue

		current_state = dsr[callsign].get("state", 0)

		# Calculate OBT - от создания флайтплана до изменения state на 1 или выше
		if "fpl_created" in times and current_state >= 1:
			# Находим время первого перехода на state >= 1
			transition_time = None

			if "taxi_start" in times:
				transition_time = times["taxi_start"]  # Начало руления
			elif "off_block_time" in times:
				transition_time = times["off_block_time"]  # Взлет (если пропустили state 1)

			if transition_time:
				obt_time = (transition_time - times["fpl_created"]).total_seconds() / 60
				airport_stats[departure]["obt_times"].append(obt_time)

		# Calculate Taxi Time - от начала руления (state 1) до взлета (state 2 или выше)
		if "taxi_start" in times and current_state >= 2:
			# Находим время перехода на state >= 2 (взлет)
			takeoff_time = None

			if "off_block_time" in times:
				takeoff_time = times["off_block_time"]  # Взлет
			else:
				# Если нет точного времени взлета, используем время первого перехода на state >= 2
				# Это может быть приблизительное время
				pass

			if takeoff_time:
				taxi_time = (takeoff_time - times["taxi_start"]).total_seconds() / 60
				airport_stats[departure]["taxi_times"].append(taxi_time)

	return airport_stats


def fetch_atc_data():
	try:
		response = requests.get('https://24data.ptfs.app/controllers', timeout=5)
		response.raise_for_status()
		controllers = response.json()

		filtered_controllers = []
		for controller in controllers:
			position = controller.get("position")

			if controller.get("airport") == "ATC 24 Staff Chat":
				position = "Staff"

			filtered_controllers.append({
				"holder": controller.get("holder"),
				"airport": CTR_TO_ARPT.get(controller.get("airport"), controller.get("airport")),
				"position": position,
				"queue": controller.get("queue", []),
				"frequency": FREQ_LIST.get(f'{controller.get("airport")}_{position}')
			})

		# Обновляем глобальную переменную
		global atc
		atc = filtered_controllers

		pepe = []
		for ps in filtered_controllers:
			if ps["holder"]:
				pepe.append(ps["airport"] + "_" + ps["position"] + f" ({len(ps['queue'])})".replace(" (0)", ""))
		print(", ".join(pepe))
		print("ATC data updated successfully")

	except requests.exceptions.RequestException as e:
		print(f"Error fetching ATC data: {e}")
	except json.JSONDecodeError as e:
		print(f"Error parsing ATC data: {e}")
	except Exception as e:
		print(f"Unexpected error in fetch_atc_data: {e}")


def run_atc_updater():
	while True:
		fetch_atc_data()
		time.sleep(10)


@app.route("/")
def index():
	try:
		with open('web.html', 'r', encoding='utf-8') as file:
			return file.read()
	except FileNotFoundError:
		return "Error: web.html file not found", 404
	except Exception as e:
		return f"Error loading web page: {str(e)}", 500


@app.route("/event/")
def index_event():
	try:
		with open('webevent.html', 'r', encoding='utf-8') as file:
			return file.read()
	except FileNotFoundError:
		return "Error: webevent.html file not found", 404
	except Exception as e:
		return f"Error loading web page: {str(e)}", 500


@app.route('/api/v1/dsr')
def api_v1_dsr():
	try:
		# print(dsr)
		return json.dumps(dsr, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
	except Exception as e:
		return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/edsr')
def api_v1_edsr():
	try:
		# print(edsr)
		return json.dumps(edsr, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
	except Exception as e:
		return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/atc')
def api_v1_atc():
	try:
		return json.dumps(atc, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
	except Exception as e:
		return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


@app.route('/api/v1/airport_stats')
def api_v1_airport_stats():
	try:
		stats = calculate_airport_stats()
		return json.dumps(stats, default=str, ensure_ascii=False), 200, {'Content-Type': 'application/json'}
	except Exception as e:
		return json.dumps({"error": str(e)}), 500, {'Content-Type': 'application/json'}


def run_websocket_client():
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	loop.run_until_complete(listen_websocket(WEBSOCKET_URL))


def run_cleanup_loop():
	while True:
		cleanup_old_data()
		time.sleep(60)


if __name__ == "__main__":
	# Start WebSocket client in background thread
	ws_thread = threading.Thread(target=run_websocket_client)
	ws_thread.daemon = True
	ws_thread.start()

	# Start cleanup thread
	cleanup_thread = threading.Thread(target=run_cleanup_loop)
	cleanup_thread.daemon = True
	cleanup_thread.start()

	# Start ATC updater thread
	atc_thread = threading.Thread(target=run_atc_updater)
	atc_thread.daemon = True
	atc_thread.start()

	print("Starting Flask application...")
	app.run(port=2424, debug=True)