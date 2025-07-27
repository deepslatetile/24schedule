import json
import asyncio
import websockets
from collections import defaultdict
from flask import Flask, render_template_string, jsonify
import os
from datetime import datetime, timedelta
import threading
import requests
import json
import random


app = Flask(__name__)

# Airport configuration
AIRPORTS = {
	"IRFD": {"name": "Greater Rockford", "city": "Rockford"},
	"ILAR": {"name": "Larnaca Intl.", "city": "Cyprus"},
	"IZOL": {"name": "Izolirani Intl.", "city": "Izolirani"},
	"ITKO": {"name": "Tokyo Intl.", "city": "Orenji"},
	"IPPH": {"name": "Perth Intl.", "city": "Perth"},
	"IGRV": {"name": "Grindavik Airport", "city": "Grindavik"},
	"IPAP": {"name": "Paphos Intl.", "city": "Cyprus"},
	"IMLR": {"name": "Mellor Intl.", "city": "Rockford"},
	"ISAU": {"name": "Sauthamptona", "city": "Sauthamptona"},
	"IBTH": {"name": "Saint Barthelemy", "city": "Saint Barthelemy"},
	"ILKL": {"name": "Lukla Airport", "city": "Perth"},
	"IDCS": {"name": "Saba Airport", "city": "Orenji"},
	"IJAF": {"name": "Al Najaf", "city": "Izolirani"},
	"ITRC": {"name": "Training Centre", "city": "Rockford"},
	"IBAR": {"name": "Barra Airport", "city": "Cyprus"},
	"IBLT": {"name": "Boltic Airfield", "city": "Rockford"},
	"IIAB": {"name": "McConnell AFB", "city": "Cyprus"},
	"ISCM": {"name": "RAF Scampton", "city": "Izolirani"},
	"IHEN": {"name": "Henstridge Airfield", "city": "Cyprus"},
	"IGAR": {"name": "Air Base Garry", "city": "Rockford"}
}
airportNameToIcao = {
	"Rockford": "IRFD",
	"Larnaca": "ILAR",
	"Izolirani": "IZOL",
	"Tokyo": "ITKO",
	"Perth": "IPPH",
	"Grindavik": "IGRV",
	"Paphos": "IPAP",
	"Sauthamptona": "ISAU",
	"Mellor": "IMLR",
	"Saint Barthelemy": "IBTH",
	"Lukla": "ILKL",
	"Saba": "IDCS",
	"Al Najaf": "IJAF",
	"Training Centre": "ITRC",
	"Barra": "IBAR",
	"Boltic": "IBLT",
	"McConnell": "IIAB",
	"Scampton": "ISCM",
	"Henstridge": "IHEN",
	"Garry": "IGAR"
}

AIRCRAFT_SHORT_NAMES = {
	"Boeing 787": "b787"
}

AIRCRAFT_IMAGES = [
	"b787_tomjet_1__deepslate",
	"b787_tomjet_2_helloworld"
]

# Global data storage
flights_data = {
	'departures': defaultdict(list),
	'arrivals': defaultdict(list),
	'aircrafts': {},
	'flight_states': {}
}

FLIGHT_PLANS_FILE = 'flight_plans.json'


def wh_log(message_text):
	print(message_text)


def normalize_callsign(callsign):
	if not callsign:
		return ""

	if not isinstance(callsign, str):
		return str(callsign)

	# Удаляем все пробелы и дефисы
	clean_callsign = callsign.replace(" ", "").replace("-", "").upper()

	# Находим индекс первой цифры
	first_digit = None
	for i, char in enumerate(clean_callsign):
		if char.isdigit():
			first_digit = i
			break

	# Если цифры найдены и перед ними нет пробела, добавляем пробел
	if first_digit is not None and first_digit > 0 and clean_callsign[first_digit - 1] != " ":
		normalized = f"{clean_callsign[:first_digit]} {clean_callsign[first_digit:]}"
	else:
		normalized = clean_callsign

	return normalized


def load_flight_plans():
	if os.path.exists(FLIGHT_PLANS_FILE):
		with open(FLIGHT_PLANS_FILE, 'r') as f:
			return json.load(f)
	return {}


def save_flight_plans(plans):
	with open(FLIGHT_PLANS_FILE, 'w') as f:
		json.dump(plans, f)


def get_recent_flight_plans():
	plans = load_flight_plans()
	now = datetime.now()
	recent_plans = {}

	for callsign, plan in plans.items():
		try:
			plan_time = datetime.strptime(plan['timestamp'], '%Y-%m-%d %H:%M:%S')
			if (now - plan_time) <= timedelta(minutes=30):
				recent_plans[callsign] = plan
		except (KeyError, ValueError):
			continue

	return recent_plans


def cleanup_old_plans():
	now = datetime.now()
	plans = load_flight_plans()
	updated_plans = {}

	for callsign, plan in plans.items():
		if callsign in flights_data['aircrafts']:
			updated_plans[callsign] = plan
			continue

		plan_time = datetime.strptime(plan['timestamp'], '%Y-%m-%d %H:%M:%S')
		if (now - plan_time) < timedelta(minutes=30):
			updated_plans[callsign] = plan

	if len(updated_plans) != len(plans):
		save_flight_plans(updated_plans)

	return updated_plans


def refresh_acft(data):
	for realcallsign, acft_data in data.items():
		normalized_realcallsign = normalize_callsign(realcallsign)
		display_callsign = normalize_callsign(acft_data.get('callsign', realcallsign))
		flights_data['aircrafts'][normalized_realcallsign] = {
			**flights_data['aircrafts'].get(normalized_realcallsign, {}),
			**acft_data,
			'live': True,
			'callsign': display_callsign,
			'realcallsign': normalized_realcallsign
		}
		if 'speed' in acft_data:
			flights_data['aircrafts'][normalized_realcallsign]['speed'] = acft_data['speed']
		if 'groundSpeed' in acft_data:
			flights_data['aircrafts'][normalized_realcallsign]['groundSpeed'] = int(str(acft_data['groundSpeed']).split('.')[0])


def new_fpl(data):
	wh_log(f'fpl {data["callsign"]}')
	required_keys = ["callsign", "departing", "arriving", "aircraft"]
	data["callsign"] = normalize_callsign(data["callsign"])
	if "realcallsign" in data:
		data["realcallsign"] = normalize_callsign(data["realcallsign"])
	else:
		data["realcallsign"] = data["callsign"]
	if any(key not in data for key in required_keys):
		print("Error: Missing required keys")
		return

	callsign = data["callsign"]
	realcallsign = data["realcallsign"]
	print(f"fpl {callsign} (real: {realcallsign})")
	data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

	plans = load_flight_plans()
	plans[realcallsign] = data
	save_flight_plans(plans)

	departing = data["departing"]
	arriving = data["arriving"]

	# Продолжаем создание рейсов
	flight_info_departure = {
		"callsign": callsign,
		"realcallsign": realcallsign,
		"aircraft": data["aircraft"],
		"arriving": arriving,
		"live": False,
		"state": 0
	}
	flights_data["departures"][departing].append(flight_info_departure)

	flight_info_arrival = {
		"callsign": callsign,
		"realcallsign": realcallsign,
		"aircraft": data["aircraft"],
		"departing": departing,
		"live": False,
		"state": 0
	}
	flights_data["arrivals"][arriving].append(flight_info_arrival)


def get_sorted_airports():
	try:
		response = requests.get('https://24data.ptfs.app/controllers', timeout=3)
		controllers = response.json() if response.ok else []
	except:
		controllers = []
	airports_with_atc = set()
	for controller in controllers:
		airport_name = controller['airport']
		if airport_name in airportNameToIcao and controller["holder"] is not None:
			print(controller["airport"], controller["position"], controller["holder"])
			airports_with_atc.add(airportNameToIcao[airport_name])

	airport_counts = []
	for icao in AIRPORTS:
		dep_count = len(flights_data['departures'].get(icao, []))
		arr_count = len(flights_data['arrivals'].get(icao, []))
		total_count = dep_count + arr_count
		if total_count > 0 or icao in airports_with_atc:
			airport_counts.append((icao, total_count, dep_count, arr_count))

	return sorted(airport_counts, key=lambda x: x[1], reverse=True)


@app.route('/api/controllers')
def get_controllers():
	try:
		response = requests.get('https://24data.ptfs.app/controllers', timeout=5)
		response.raise_for_status()
		return json.dumps(response.json())
	except Exception as e:
		print(f"Error fetching ATC data: {e}")
		return json.dumps([])


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ATC24 Flight Schedule</title>
    <style>
        :root {
            --bg-color: #121212;
            --card-color: #1e1e1e;
            --text-color: #e0e0e0;
            --accent-color: #3a86ff;
            --border-color: #333333;
            --secondary-text: #b0b0b0;
            --live-accent: #ff4d4d;
        }
        body {
            font-family: 'Segoe UI', system-ui, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 0;
            line-height: 1.5;
        }
        .container {
            max-width: 90vw;
            margin: 0 auto;
            padding: 16px;
            display: flex;
            flex-wrap: wrap;
            justify-content: center;
        }
        .filters {
            width: 100%;
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        .filter-btn {
            padding: 8px 16px;
            background-color: var(--card-color);
            color: var(--text-color);
            border: 1px solid var(--border-color);
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .filter-btn:hover {
            background-color: var(--accent-color);
            color: white;
        }
        .filter-btn.active {
            background-color: var(--accent-color);
            color: white;
        }
        h1 {
            color: var(--text-color);
            font-size: 24px;
            font-weight: 600;
            margin-bottom: 24px;
            text-align: center;
        }
        h2 {
            font-size: 20px;
            font-weight: 600;
            margin: 24px 0 12px 0;
            color: var(--accent-color);
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h3 {
            font-size: 16px;
            font-weight: 500;
            margin: 16px 0 8px 0;
            color: var(--text-color);
        }
        .airport-section {
            background-color: var(--card-color);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
            border: 1px solid var(--border-color);
            width: 350px;
            margin-right: 16px;
            margin-left: 16px;
        }
        .flight-card {
            background-color: #252525;
            border-left: 3px solid var(--accent-color);
            padding: 12px;
            margin-bottom: 12px;
            border-radius: 4px;
            position: relative;
            padding-right: 32px;
            transition: transform 0.2s;
            cursor: pointer;
        }
        .flight-card:hover {
            transform: translateY(-2px);
        }
        .flight-card.live {
            border-left-color: var(--live-accent);
        }
        .flight-time {
            font-weight: 600;
            color: var(--accent-color);
            margin-bottom: 6px;
            font-size: 15px;
        }
        .flight-route {
            font-weight: 500;
            margin-bottom: 6px;
            font-size: 16px;
            color: var(--text-color);
            display: flex;
            gap: 8px;
            align-items: center;
        }
        .flight-callsign {
            font-weight: 500;
            margin-bottom: 6px;
            font-size: 20px;
            color: var(--text-color);
            display: flex;
            align-items: center;
        }
        .flight-acft {
            font-weight: 300;
            margin-bottom: 6px;
            font-size: 20px;
            color: var(--secondary-text);
            display: flex;
            align-items: center;
        }
        .route-arrow {
            color: var(--accent-color);
        }
        .flight-details {
            display: flex;
            flex-direction: column;
            gap: 4px;
            font-size: 14px;
            color: var(--secondary-text);
        }
        .flight-details-row {
            display: flex;
            gap: 12px;
        }
        .live-badge {
            background-color: #ff3d00;
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 500;
            margin-left: 8px;
            display: inline-block;
        }
        .section-divider {
            height: 1px;
            background-color: var(--border-color);
            margin: 16px 0;
            opacity: 0.5;
        }
        .no-flights {
            color: var(--secondary-text);
            font-style: italic;
            padding: 8px 0;
        }
        .no-airports-message {
            color: var(--secondary-text);
            font-style: italic;
            text-align: center;
            width: 100%;
            padding: 20px;
            font-size: 18px;
        }
        .flight-state-icon {
            position: absolute;
            right: 16px;
            top: 64px;
            transform: none;
        }
        
        .flight-state-icon img {
            width: 32px;
            height: 32px;
            vertical-align: middle;
            cursor: help;
            position: sticky;
            top: 16px;
        }
        .flight-counts {
            margin-left: 10px;
            font-size: 14px;
            display: inline-flex;
            gap: 4px;
            flex-direction: column;
        }
        .count-row {
            display: flex;
            gap: 4px;
            align-items: center;
        }
        .total-count {
            opacity: 0.7;
            font-size: 0.9em;
        }
        .live-count {
            font-weight: bold;
        }
        .departure-count {
            color: #4CAF50;
        }
        .arrival-count {
            color: #FF5722;
        }
        .count-separator {
            margin: 0 2px;
            opacity: 0.5;
        }
        .toggle-icon {
            font-size: 14px;
            margin-left: 8px;
        }
        .flight-card::before {
            content: '';
            position: absolute;
            left: 0;
            bottom: 0;
            width: 0;
            height: 100%;
            background-color: #2e3a42;
            z-index: -1;
            transition: width 0.1s ease-in-out;
        }
        .flight-card:hover::before {
            width: 100%;
        }
        /* ATC Styles */
        .atc-container {
            margin-top: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .atc-position {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px 8px;
            background-color: rgba(30, 30, 30, 0.7);
            border-radius: 4px;
        }
        .atc-icon {
            width: 24px;
            height: 24px;
        }
        .atc-queue {
            font-size: 0.9em;
            color: var(--secondary-text);
            margin-left: 4px;
        }
        .atc-holder {
            font-weight: 500;
        }
        .unclaimed {
            opacity: 0.6;
            font-style: italic;
        }
        .atc-divider {
            height: 1px;
            background-color: var(--border-color);
            margin: 8px 0;
            opacity: 0.3;
        }
        .flight-details-expanded {
            display: none;
            margin-top: 12px;
            padding: 12px;
            background-color: #2a2a2a;
            border-radius: 4px;
            border-left: 3px solid var(--accent-color);
        }
        
        .flight-details-grid {
            display: grid;
            grid-template-columns: repeat(1, 1fr);
            gap: 8px;
            margin-bottom: 12px;
        }
        
        .detail-item {
            display: flex;
            flex-direction: column;
        }
        
        .detail-label {
            font-size: 12px;
            color: var(--secondary-text);
            margin-bottom: 2px;
        }
        
        .detail-value {
            font-size: 14px;
            font-weight: 500;
        }
        
        .aircraft-image-container {
            width: 100%;
            margin-top: 12px;
            position: relative;
        }
        
        .aircraft-image {
            width: 100%;
            max-height: 200px;
            object-fit: contain;
            border-radius: 4px;
        }
        
        .image-author {
            position: absolute;
            bottom: 4px;
            right: 4px;
            font-size: 10px;
            color: var(--secondary-text);
            background-color: rgba(0, 0, 0, 0.7);
            padding: 2px 4px;
            border-radius: 2px;
        }
        
        .no-image {
            font-style: italic;
            color: var(--secondary-text);
            text-align: center;
            padding: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>ATC24 Flight Schedule</h1>
    </div>

    <div class="container">
        <div class="filters">
            <button class="filter-btn" id="toggleLive">Show LIVE only</button>
            <button class="filter-btn" id="expandAll">Expand All</button>
            <button class="filter-btn" id="collapseAll">Collapse All</button>
        </div>
    </div>

    <div class="container" id="airportsContainer">
        {% if airports %}
            {% for icao, _, dep_count, arr_count in airports %}
            <div class="airport-section" id="airport-{{ icao }}">
                <h2 onclick="toggleAirport('{{ icao }}')">
                    <span>
                        {{ AIRPORTS[icao].name }} ({{ icao }})
                        <span class="flight-counts">
                            <span class="count-row total-count">
                                <span class="departure-count">{{ dep_count }}↑</span>
                                <span class="count-separator">|</span>
                                <span class="arrival-count">{{ arr_count }}↓</span>
                            </span>
                            <span class="count-row live-count">
                                <span class="departure-count">{{ departures.get(icao, [])|selectattr('live')|list|count }}↑</span>
                                <span class="count-separator">|</span>
                                <span class="arrival-count">{{ arrivals.get(icao, [])|selectattr('live')|list|count }}↓</span>
                            </span>
                        </span>
                    </span>
                    <span class="toggle-icon">▼</span>
                </h2>
                
                <div class="airport-content" id="content-{{ icao }}">
                    <!-- ATC Positions Container -->
                    <div class="atc-container" id="atc-{{ icao }}">
                        <div class="atc-position">
                            <span class="unclaimed">Loading ATC data...</span>
                        </div>
                    </div>

                    <div class="atc-divider"></div>

                    <h3>Departures</h3>
                    {% if departures.get(icao, []) %}
                        {% for flight in departures.get(icao, []) %}
                        <div class="flight-card {% if flight.live %}live{% endif %}" 
                             data-live="{{ flight.live }}" 
                             data-type="departure" 
                             data-realcallsign="{{ flight.realcallsign }}"
                             onclick="toggleFlightDetails(this)">
                            <div class="flight-time">
                                {{ flight.time if 'time' in flight else '--:--' }}
                                {% if flight.live %}<span class="live-badge">LIVE</span>{% endif %}
                            </div>
                            
                            <div class="flight-state-icon">
                                <img src="{{ flight.state | icon_for_state }}" alt="Flight State Icon" title="{{ flight.state | description_for_state }}"/>
                            </div>
                            
                            <div class="flight-details-row">
                                <span class="flight-callsign">{{ flight.callsign.upper() }}</span> <span class="flight-acft">({{ flight.aircraft }})</span>
                            </div>
                            <div class="flight-details-row">
                                <span>{{ flight.departing.upper() }}</span>
                                <span class="route-arrow">→</span>
                                <span>{{ flight.arriving.upper() }}</span>
                            </div>
                            <div class="flight-details">
                                <div class="flight-details-row">
                                    <span>{{ flight.playerName if 'playerName' in flight else 'Unknown' }}</span>
                                </div>
                                <div class="flight-details-row">
                                    <span>FL{{ flight.flightlevel if 'flightlevel' in flight else '---' }}</span>
                                </div>
                            </div>
                            
                            <!-- Expanded Flight Details -->
                            <div class="flight-details-expanded">
                                <div class="flight-details-grid">
                                    <div class="detail-item">
                                        <span class="detail-label">Altitude</span>
                                        <span class="detail-value altitude-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Speed</span>
                                        <span class="detail-value speed-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Heading</span>
                                        <span class="detail-value heading-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Route</span>
                                        <span class="detail-value route-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Position</span>
                                        <span class="detail-value position-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Wind</span>
                                        <span class="detail-value wind-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Ground Speed</span>
                                        <span class="detail-value groundspeed-value">---</span>
                                    </div>
                                </div>
                                
                                <div class="aircraft-image-container">
                                    <div class="no-image">Loading aircraft image...</div>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="no-flights">No scheduled departures</div>
                    {% endif %}
                    
                    <div class="section-divider"></div>
                    
                    <h3>Arrivals</h3>
                    {% if arrivals.get(icao, []) %}
                        {% for flight in arrivals.get(icao, []) %}
                        <div class="flight-card {% if flight.live %}live{% endif %}" 
                             data-live="{{ flight.live }}" 
                             data-type="arrival" 
                             data-realcallsign="{{ flight.realcallsign }}"
                             onclick="toggleFlightDetails(this)">
                            <div class="flight-time">
                                {{ flight.time if 'time' in flight else '--:--' }}
                                {% if flight.live %}<span class="live-badge">LIVE</span>{% endif %}
                            </div>
                            
                            <div class="flight-state-icon">
                                <img src="{{ flight.state | icon_for_state }}" alt="Flight State Icon" title="{{ flight.state | description_for_state }}"/>
                            </div>
                            
                            <div class="flight-details-row">
                                <span class="flight-callsign">{{ flight.callsign.upper() }}</span> <span class="flight-acft">({{ flight.aircraft }})</span>
                            </div>
                            <div class="flight-details-row">
                                <span>{{ flight.departing.upper() }}</span>
                                <span class="route-arrow">→</span>
                                <span>{{ flight.arriving.upper() }}</span>
                            </div>
                            <div class="flight-details">
                                <div class="flight-details-row">
                                    <span>{{ flight.playerName if 'playerName' in flight else 'Unknown' }}</span>
                                </div>
                                <div class="flight-details-row">
                                    <span>FL{{ flight.flightlevel if 'flightlevel' in flight else '---' }}</span>
                                </div>
                            </div>
                            
                            <!-- Expanded Flight Details -->
                            <div class="flight-details-expanded">
                                <div class="flight-details-grid">
                                    <div class="detail-item">
                                        <span class="detail-label">Altitude</span>
                                        <span class="detail-value altitude-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Speed</span>
                                        <span class="detail-value speed-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Heading</span>
                                        <span class="detail-value heading-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Route</span>
                                        <span class="detail-value route-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Position</span>
                                        <span class="detail-value position-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Wind</span>
                                        <span class="detail-value wind-value">---</span>
                                    </div>
                                    <div class="detail-item">
                                        <span class="detail-label">Ground Speed</span>
                                        <span class="detail-value groundspeed-value">---</span>
                                    </div>
                                </div>
                                
                                <div class="aircraft-image-container">
                                    <div class="no-image">Loading aircraft image...</div>
                                </div>
                            </div>
                        </div>
                        {% endfor %}
                    {% else %}
                        <div class="no-flights">No scheduled arrivals</div>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        {% else %}
            <div class="no-airports-message">No active airports with flights at the moment</div>
        {% endif %}
    </div>


<script>
    const airportNameToIcao = {
        "Rockford": "IRFD",
        "Larnaca": "ILAR",
        "Izolirani": "IZOL",
        "Tokyo": "ITKO",
        "Perth": "IPPH",
        "Grindavik": "IGRV",
        "Paphos": "IPAP",
        "Sauthamptona": "ISAU",
        "Mellor": "IMLR",
        "Saint Barthelemy": "IBTH",
        "Lukla": "ILKL",
        "Saba": "IDCS",
        "Al Najaf": "IJAF",
        "Training Centre": "ITRC",
        "Barra": "IBAR",
        "Boltic": "IBLT",
        "McConnell": "IIAB",
        "Scampton": "ISCM",
        "Henstridge": "IHEN",
        "Garry": "IGAR"
    };

    function toggleFlightDetails(card) {
        const details = card.querySelector('.flight-details-expanded');
        const isExpanded = details.style.display === 'block';
        
        if (isExpanded) {
            details.style.display = 'none';
        } else {
            details.style.display = 'block';
            
            // Only load data if it hasn't been loaded yet
            if (details.getAttribute('data-loaded') !== 'true') {
                loadFlightDetails(card);
            }
        }
    }

    async function loadFlightDetails(card) {
        const realcallsign = card.dataset.realcallsign;
        const details = card.querySelector('.flight-details-expanded');
        const imageContainer = card.querySelector('.aircraft-image-container');
        
        try {
            // Fetch aircraft data
            const response = await fetch(`/api/flight/${encodeURIComponent(realcallsign)}`);
            if (!response.ok) throw new Error('Failed to fetch flight data');
            
            const data = await response.json();
            
            // Update all details
            if (data.altitude) details.querySelector('.altitude-value').textContent = `${data.altitude} ft`;
            if (data.speed) details.querySelector('.speed-value').textContent = `${data.speed} kts`;
            if (data.heading) details.querySelector('.heading-value').textContent = `${data.heading}°`;
            if (data.route) details.querySelector('.route-value').textContent = data.route;
            if (data.position) details.querySelector('.position-value').textContent = data.position;
            if (data.wind) details.querySelector('.wind-value').textContent = data.wind;
            if (data.groundspeed) details.querySelector('.groundspeed-value').textContent = `${data.groundspeed} kts`;
            
            // Load aircraft image
            if (data.aircraft) {
                const callsignPrefix = realcallsign.replace(/\d+/g, '').toLowerCase();
                
                try {
                    const imageResponse = await fetch(`/api/aircraft-image/${encodeURIComponent(data.aircraft)}/${callsignPrefix}`);
                    if (imageResponse.ok) {
                        const imageData = await imageResponse.json();
                        if (imageData.imageUrl) {
                            imageContainer.innerHTML = `
                                <img src="${imageData.imageUrl}" 
                                     alt="${data.aircraft}" 
                                     class="aircraft-image"
                                     onerror="this.onerror=null;this.parentElement.innerHTML='<div class=\'no-image\'>Image failed to load</div>'">
                                ${imageData.author ? `<span class="image-author">by ${imageData.author}</span>` : ''}
                            `;
                        } else {
                            imageContainer.innerHTML = '<div class="no-image">No image available for this aircraft</div>';
                        }
                    } else {
                        imageContainer.innerHTML = '<div class="no-image">No image available for this aircraft</div>';
                    }
                } catch (e) {
                    console.error('Error loading aircraft image:', e);
                    imageContainer.innerHTML = '<div class="no-image">Error loading image</div>';
                }
            } else {
                imageContainer.innerHTML = '<div class="no-image">No aircraft type specified</div>';
            }
            
            details.setAttribute('data-loaded', 'true');
        } catch (error) {
            console.error('Error loading flight details:', error);
            const noImageElement = details.querySelector('.no-image') || imageContainer.querySelector('.no-image');
            if (noImageElement) {
                noImageElement.textContent = 'Error loading flight data';
            }
        }
    }

    async function loadAtcData() {
        try {
            const response = await fetch('/api/controllers');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const controllers = await response.json();
            updateAtcDisplay(controllers);
        } catch (error) {
            console.error('Error loading ATC data:', error);
            document.querySelectorAll('.atc-container').forEach(container => {
                container.innerHTML = `
                    <div class="atc-position">
                        <span class="unclaimed">Failed to load ATC data</span>
                    </div>
                `;
            });
        }
    }

    function updateAtcDisplay(controllers) {
        // Group controllers by airport
        const airportControllers = {};
        
        controllers.forEach(controller => {
            if (!airportNameToIcao[controller.airport]) return;
            
            const icao = airportNameToIcao[controller.airport];
            if (!airportControllers[icao]) {
                airportControllers[icao] = [];
            }
            airportControllers[icao].push(controller);
        });

        Object.keys(airportControllers).forEach(icao => {
            const atcContainer = document.querySelector(`#atc-${icao}`);
            if (!atcContainer) return;

            atcContainer.innerHTML = '';
            const sortedControllers = airportControllers[icao].sort((a, b) => {
                if (a.position === 'Tower') return -1;
                if (b.position === 'Tower') return 1;
                return 0;
            });

            let hasActiveControllers = false;
            
            sortedControllers.forEach(controller => {
                // Skip if position is unclaimed and no queue
                if (!controller.holder && controller.queue.length === 0) return;
                
                hasActiveControllers = true;
                
                const positionDiv = document.createElement('div');
                positionDiv.className = 'atc-position';
                
                if (controller.holder) {
                    // Create position icon
                    const icon = document.createElement('img');
                    icon.className = 'atc-icon';
                    icon.src = `https://raw.githubusercontent.com/deepslatetile/24schedule/main/${controller.position.toLowerCase()}_atc.png`;
                    icon.alt = controller.position;
                    icon.title = controller.position;
                    
                    // Create element with controller name
                    const holderSpan = document.createElement('span');
                    holderSpan.className = 'atc-holder';
                    holderSpan.textContent = controller.holder;
                    
                    positionDiv.appendChild(icon);
                    positionDiv.appendChild(holderSpan);
                    
                    // Add queue if exists
                    if (controller.queue.length > 0) {
                        const queueSpan = document.createElement('span');
                        queueSpan.className = 'atc-queue';
                        queueSpan.textContent = `(${controller.queue.length})`;
                        positionDiv.appendChild(queueSpan);
                    }
                } else {
                    // Position is unclaimed but has queue
                    const holderSpan = document.createElement('span');
                    holderSpan.className = 'atc-holder unclaimed';
                    holderSpan.textContent = `${controller.position} (unclaimed)`;
                    positionDiv.appendChild(holderSpan);
                    
                    if (controller.queue.length > 0) {
                        const queueSpan = document.createElement('span');
                        queueSpan.className = 'atc-queue';
                        queueSpan.textContent = `(${controller.queue.length})`;
                        positionDiv.appendChild(queueSpan);
                    }
                }
                
                atcContainer.appendChild(positionDiv);
            });

            if (!hasActiveControllers) {
                atcContainer.innerHTML = `
                    <div class="atc-position">
                        <span class="unclaimed">No active ATC positions</span>
                    </div>
                `;
            }
        });

        document.querySelectorAll('.airport-section').forEach(section => {
            const icao = section.id.replace('airport-', '');
            const atcContainer = document.querySelector(`#atc-${icao}`);
            
            if (atcContainer && atcContainer.innerHTML.trim() === '') {
                atcContainer.innerHTML = `
                    <div class="atc-position">
                        <span class="unclaimed">No ATC data available</span>
                    </div>
                `;
            }
        });
    }

    const collapsedAirports = JSON.parse(localStorage.getItem('collapsedAirports') || '{}');

    function toggleAirport(icao) {
        const content = document.getElementById(`content-${icao}`);
        const icon = document.querySelector(`#airport-${icao} h2 .toggle-icon`);
        
        if (!content || !icon) return;
        
        if (collapsedAirports[icao]) {
            // Show content
            content.style.display = 'block';
            icon.textContent = '▼';
            collapsedAirports[icao] = false;
        } else {
            // Hide content
            content.style.display = 'none';
            icon.textContent = '▶';
            collapsedAirports[icao] = true;
        }
        
        localStorage.setItem('collapsedAirports', JSON.stringify(collapsedAirports));
    }

    function expandAllAirports() {
        const airports = document.querySelectorAll('.airport-section');
        airports.forEach(airport => {
            const icao = airport.id.replace('airport-', '');
            const content = document.getElementById(`content-${icao}`);
            const icon = document.querySelector(`#airport-${icao} h2 .toggle-icon`);
            
            if (content && icon) {
                content.style.display = 'block';
                icon.textContent = '▼';
                collapsedAirports[icao] = false;
            }
        });
        
        localStorage.setItem('collapsedAirports', JSON.stringify(collapsedAirports));
    }

    function collapseAllAirports() {
        const airports = document.querySelectorAll('.airport-section');
        airports.forEach(airport => {
            const icao = airport.id.replace('airport-', '');
            const content = document.getElementById(`content-${icao}`);
            const icon = document.querySelector(`#airport-${icao} h2 .toggle-icon`);
            
            if (content && icon) {
                content.style.display = 'none';
                icon.textContent = '▶';
                collapsedAirports[icao] = true;
            }
        });
        
        localStorage.setItem('collapsedAirports', JSON.stringify(collapsedAirports));
    }

    function toggleLiveFilter() {
        const btn = document.getElementById('toggleLive');
        if (!btn) return;
        
        const showLiveOnly = btn.classList.toggle('active');
        
        localStorage.setItem('showLiveOnly', showLiveOnly);
        
        const flightCards = document.querySelectorAll('.flight-card');
        flightCards.forEach(card => {
            if (!card) return;
            
            if (showLiveOnly) {
                // Show only LIVE flights
                card.style.display = card.dataset.live === 'True' ? 'block' : 'none';
            } else {
                // Show all flights
                card.style.display = 'block';
            }
        });

        updateLiveCounts();
    }
    
    // Function to update LIVE flight counters
    function updateLiveCounts() {
        const airports = document.querySelectorAll('.airport-section');
        airports.forEach(airport => {
            const icao = airport.id.replace('airport-', '');

            const liveDepCount = airport.querySelectorAll('.flight-card[data-live="True"][data-type="departure"]').length;
            const liveArrCount = airport.querySelectorAll('.flight-card[data-live="True"][data-type="arrival"]').length;

            const liveDepElement = airport.querySelector('.live-count .departure-count');
            const liveArrElement = airport.querySelector('.live-count .arrival-count');
            
            if (liveDepElement) liveDepElement.textContent = `${liveDepCount}↑`;
            if (liveArrElement) liveArrElement.textContent = `${liveArrCount}↓`;
        });
    }
    
    document.addEventListener('DOMContentLoaded', () => {
        Object.keys(collapsedAirports).forEach(icao => {
            if (collapsedAirports[icao]) {
                const content = document.getElementById(`content-${icao}`);
                const icon = document.querySelector(`#airport-${icao} h2 .toggle-icon`);
                if (content && icon) {
                    content.style.display = 'none';
                    icon.textContent = '▶';
                }
            }
        });
        
        const showLiveOnly = localStorage.getItem('showLiveOnly') === 'true';
        if (showLiveOnly) {
            const btn = document.getElementById('toggleLive');
            if (btn) {
                btn.classList.add('active');
                toggleLiveFilter();
            }
        }
        
        document.getElementById('toggleLive')?.addEventListener('click', toggleLiveFilter);
        document.getElementById('expandAll')?.addEventListener('click', expandAllAirports);
        document.getElementById('collapseAll')?.addEventListener('click', collapseAllAirports);

        updateLiveCounts();

        loadAtcData();
        setInterval(loadAtcData, 30000);
    });
</script>


</body>
</html>
"""


@app.route('/api/flight/<callsign>')
def get_flight_details(callsign):
	flight_data = flights_data['aircrafts'].get(normalize_callsign(callsign), {})
	flight_plans = load_flight_plans()
	fpl = flight_plans.get(normalize_callsign(callsign), {})

	position = "---"
	if 'position' in flight_data:
		if isinstance(flight_data['position'], dict):
			x = flight_data['position'].get("x", "---")
			y = flight_data['position'].get("y", "---")
			position = f"{x}, {y}"
		else:
			position = str(flight_data['position'])

	print(flight_data.get('aircraft', fpl.get('aircraft', 'Unknown')), callsign)
	response = {
		'altitude': flight_data.get('altitude', '---'),
		'speed': flight_data.get('speed', '---'),
		'heading': flight_data.get('heading', '---'),
		'route': fpl.get('route', '---'),
		'position': position,
		'wind': flight_data.get('wind', '---'),
		'groundspeed': flight_data.get('groundSpeed', flight_data.get('speed', '---')),
		'aircraft': flight_data.get('aircraft', fpl.get('aircraft', 'Unknown')),  # Изменили aircraftType на aircraft
		'aircraftType': AIRCRAFT_SHORT_NAMES.get(flight_data.get('aircraft', fpl.get('aircraft', 'Unknown')), 'unknown')  # Добавили сокращенный тип
	}

	return jsonify(response)


@app.route('/api/aircraft-image/<aircraft_type>/<callsign_prefix>')
def get_aircraft_image(aircraft_type, callsign_prefix):
	callsign_prefix = callsign_prefix.lower()
	short_type = AIRCRAFT_SHORT_NAMES.get(aircraft_type, aircraft_type.split()[-1].lower())
	base_url = "https://raw.githubusercontent.com/deepslatetile/24schedule/main/pictures"
	matching_images = []

	for image_name in AIRCRAFT_IMAGES:
		parts = image_name.split('_', 3)
		if len(parts) < 4:
			continue

		img_type = parts[0]
		img_airline = parts[1]
		img_index = parts[2]
		img_author = parts[3]

		if img_type == short_type and img_airline == callsign_prefix:
			matching_images.append({
				'author': img_author,
				'filename': image_name + '.png'
			})

	if matching_images:
		selected_image = random.choice(matching_images)
		return jsonify({
			'imageUrl': f"{base_url}/{selected_image['filename']}",
			'author': selected_image['author']
		})

	generic_images = []
	for image_name in AIRCRAFT_IMAGES:
		if image_name.startswith(short_type + '_'):
			parts = image_name.split('_')
			img_author = ' '.join(parts[3:])
			generic_images.append({
				'author': img_author,
				'filename': image_name + '.png'
			})

	if generic_images:
		selected_image = random.choice(generic_images)
		return jsonify({
			'imageUrl': f"{base_url}/{selected_image['filename']}",
			'author': selected_image['author']
		})

	return jsonify({'imageUrl': None, 'author': None}), 404


def icon_for_state(state):
	icons = {
		0: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/boarding.png',
		1: 'https://raw.githubusercontent.com/deepslatetile/24schedule/refs/heads/main/taxiing.png',
		2: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/departure.png',
		3: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/cruise.png',
		4: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/arrival.png',
		5: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/ground.png'
	}
	return icons.get(state, '')


def description_for_state(state):
	descriptions = {
		0: 'Boarding',
		1: 'Taxiing',
		2: 'Climbing',
		3: 'Cruising',
		4: 'Descending',
		5: 'Arrived'
	}
	return descriptions.get(state, '')


app.jinja_env.filters['icon_for_state'] = icon_for_state
app.jinja_env.filters['description_for_state'] = description_for_state


@app.route('/')
def index():
	flight_plans = get_recent_flight_plans()
	current_time = datetime.now()

	flights_data['departures'] = defaultdict(list)
	flights_data['arrivals'] = defaultdict(list)

	for realcallsign, plan in flight_plans.items():
		if not all(key in plan for key in ['departing', 'arriving', 'aircraft']):
			continue

		display_callsign = normalize_callsign(plan.get('callsign', realcallsign))
		flight_level = str(plan.get('flightlevel', '0')).replace('FL', '').strip()

		flight_info = {
			'callsign': display_callsign,
			'realcallsign': realcallsign,
			'aircraft': plan['aircraft'],
			'flightlevel': flight_level,
			'playerName': plan.get('robloxName', 'Unknown'),
			'timestamp': plan['timestamp'],
			'time': datetime.strptime(plan['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M'),
			'live': realcallsign in flights_data['aircrafts'],
			'is_local': plan['departing'] == plan['arriving'],
			'departing_name': AIRPORTS.get(plan['departing'], {}).get('name', plan['departing']),
			'arriving_name': AIRPORTS.get(plan['arriving'], {}).get('name', plan['arriving'])
		}

		if not flight_info['is_local'] or plan['departing'] in AIRPORTS:
			departure_info = flight_info.copy()
			departure_info.update({
				'departing': plan['departing'],
				'arriving': plan['arriving'],
				'state': 0
			})
			flights_data['departures'][plan['departing']].append(departure_info)

		if not flight_info['is_local'] or plan['arriving'] in AIRPORTS:
			arrival_info = flight_info.copy()
			arrival_info.update({
				'departing': plan['departing'],
				'arriving': plan['arriving'],
				'state': 0
			})
			flights_data['arrivals'][plan['arriving']].append(arrival_info)

	update_flight_statuses()
	sorted_airports = get_sorted_airports()

	return render_template_string(
		HTML_TEMPLATE,
		airports=get_sorted_airports(),
		departures=flights_data['departures'],
		arrivals=flights_data['arrivals'],
		AIRPORTS=AIRPORTS,
		current_time=current_time.strftime('%Y-%m-%d %H:%M:%S')
	)


def get_flight_state(realcallsign, acft_data):
	normalized_callsign = normalize_callsign(realcallsign)
	realcallsign = normalized_callsign

	if not acft_data:
		wh_log(f"{realcallsign} check: No aircraft data")
		return None

	flight_plans = load_flight_plans()
	fpl = flight_plans.get(realcallsign)

	if not fpl:
		wh_log(f"{realcallsign} check: Flight plan not found")
		return None

	prev_state = flights_data['flight_states'].get(realcallsign, 0)
	speed = acft_data.get('speed', 0)
	is_on_ground = acft_data.get('isOnGround', True)
	altitude = acft_data.get('altitude', 0)
	flight_level = 0
	try:
		flight_level = int(fpl["flightlevel"]) * 100
	except:
		flight_level = 0
		wh_log(f"{normalized_callsign} check: Invalid flight level in FPL: {fpl.get('flightlevel', 'N/A')}")

	normalized_callsign = normalize_callsign(realcallsign)
	log_message = (
		f"{normalized_callsign}\n"
		f"FPL FL: {flight_level}ft, "
		f"{altitude}ft "
		f"{speed}kts "
		f"{is_on_ground} "
		f"{prev_state}\n"
	)
	print(log_message)

	new_state = prev_state

	if is_on_ground:
		if speed > 10 and prev_state == 0:
			new_state = 1  # departing
		elif speed < 30 and prev_state in [2, 3, 4]:
			new_state = 5  # landed
	else:
		if prev_state in [0, 1]:
			new_state = 2  # climbing
		elif prev_state == 2 and altitude > (flight_level - 300):
			new_state = 3  # cruise
		elif prev_state == 3 and altitude < (flight_level - 400):
			new_state = 4  # descending

	if new_state != prev_state:
		state_change_msg = (
			f"{normalized_callsign} STATE CHANGE: "
			f"{prev_state}->{new_state} | "
			f"FL: {flight_level}ft | "
			f"Alt: {altitude}ft | "
			f"Speed: {speed}kts | "
			f"OnGround: {is_on_ground}"
		)
		# print(state_change_msg)
		flights_data['flight_states'][normalized_callsign] = new_state
	else:
		pass

	return new_state


def update_flight_statuses():
	for realcallsign, acft_data in flights_data['aircrafts'].items():
		display_callsign = acft_data.get('callsign', realcallsign)

		for airport, flights in flights_data['departures'].items():
			for flight in flights:
				flight_realcallsign = flight.get('realcallsign', flight.get('callsign', ''))
				if normalize_callsign(flight_realcallsign) == normalize_callsign(realcallsign):
					flight['live'] = True
					flight['state'] = get_flight_state(realcallsign, acft_data)
					flight['callsign'] = display_callsign

		for airport, flights in flights_data['arrivals'].items():
			for flight in flights:
				flight_realcallsign = flight.get('realcallsign', flight.get('callsign', ''))
				if normalize_callsign(flight_realcallsign) == normalize_callsign(realcallsign):
					flight['live'] = True
					flight['state'] = get_flight_state(realcallsign, acft_data)
					flight['callsign'] = display_callsign


async def websocket_listener():
	uri = "wss://24data.ptfs.app/wss"
	while True:
		try:
			async with websockets.connect(uri) as websocket:
				while True:
					message = await websocket.recv()
					data = json.loads(message)
					if data['t'] == "ACFT_DATA":
						refresh_acft(data['d'])
					elif data['t'] == "FLIGHT_PLAN":
						new_fpl(data['d'])

					update_flight_statuses()
		except Exception as e:
			print(f"WebSocket error: {e}")
			await asyncio.sleep(5)


def run_websocket():
	loop = asyncio.new_event_loop()
	asyncio.set_event_loop(loop)
	loop.run_until_complete(websocket_listener())


def run_flask():
	app.run(host='0.0.0.0', port=62424, debug=True, use_reloader=False)


if __name__ == '__main__':
	ws_thread = threading.Thread(target=run_websocket, daemon=True)
	ws_thread.start()
	run_flask()
