import json
import asyncio
import websockets
from collections import defaultdict
from flask import Flask, render_template_string
import os
from datetime import datetime, timedelta
import threading

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

# Global data storage
flights_data = {
    'departures': defaultdict(list),
    'arrivals': defaultdict(list),
    'aircrafts': {},
    'flight_states': {}
}

FLIGHT_PLANS_FILE = 'flight_plans.json'


import requests
import json

def wh_log(message_text):
    # Замените эту ссылку на ваш вебхук
    WEBHOOK_URL = "https://discord.com/api/webhooks/1398545462310735922/rrjxryjo59vDVtYIScwOomSjvFPPp2Y1lDhupxO2c5JR4u4wRv_ct03oxunXqS2IOMEI"
    
    try:
        # Подготавливаем данные для отправки
        payload = {
            "content": message_text,
        }
        
        # Отправляем POST-запрос
        response = requests.post(
            WEBHOOK_URL,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        # Проверяем успешность запроса
        if response.status_code in [200, 204]:
            return True
        else:
            print(f"Webhook error: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Error sending to webhook: {str(e)}")
        return False
        

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
            if (now - plan_time) <= timedelta(minutes=120):
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
        if (now - plan_time) < timedelta(minutes=90):
            updated_plans[callsign] = plan

    if len(updated_plans) != len(plans):
        save_flight_plans(updated_plans)

    return updated_plans

def refresh_acft(data):
    for callsign, acft_data in data.items():
        flights_data['aircrafts'][callsign] = acft_data
        flights_data['aircrafts'][callsign]['live'] = True
        flights_data['aircrafts'][callsign]['callsign'] = callsign


def new_fpl(data):
    wh_log(f'fpl {data["callsign"]}')
    required_keys = ["callsign", "departing", "arriving", "aircraft"]

    # Нормализуем callsign
    data["callsign"] = data["callsign"].replace("-", "").replace(" ", "").upper()
    
    # Проверка необходимых ключей
    if any(key not in data for key in required_keys):
        print("Error: Missing required keys")
        return

    callsign = data["callsign"]
    print(f"fpl {callsign}")
    data["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    plans = load_flight_plans()
    plans[callsign] = data
    save_flight_plans(plans)

    departing = data["departing"]
    arriving = data["arriving"]

    # Продолжаем создание рейсов
    flight_info_departure = {
        "callsign": callsign,
        "aircraft": data["aircraft"],
        "arriving": arriving,
        "live": False,
        "state": 0
    }
    flights_data["departures"][departing].append(flight_info_departure)

    flight_info_arrival = {
        "callsign": callsign,
        "aircraft": data["aircraft"],
        "departing": departing,
        "live": False,
        "state": 0
    }
    flights_data["arrivals"][arriving].append(flight_info_arrival)


def get_sorted_airports():
    airport_counts = []
    for icao in AIRPORTS:
        count = len(flights_data['departures'].get(icao, [])) + \
                len(flights_data['arrivals'].get(icao, []))
        airport_counts.append((icao, count))

    return sorted(airport_counts, key=lambda x: x[1], reverse=True)


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
            justify-content: center
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
        .detail-label {
            font-weight: 500;
            color: var(--text-color);
            min-width: 80px;
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
        .flight-state-icon {
            position: absolute;
            right: 16px;
            top: 50%;
            transform: translateY(-50%);
        }
        
        .flight-state-icon img {
            width: 32px;
            height: 32px;
            vertical-align: middle;
            cursor: help;
        }
        
        .flight-card {
            position: relative;
            padding-right: 32px; /* Добавляем отступ справа для иконки */
            transition: transform 0.2s;
        }
        
        .flight-card:hover {
            transform: translateY(-2px);
        }
        
        .flight-card.live {
            border-left-color: var(--live-accent);
        }
        
        .flight-card {
    position: relative;
    overflow: hidden;
    transition: transform 0.1s ease-in-out;
}
.flight-card::before {
    content: '';
    position: absolute;
    left: 0;
    bottom: 0;
    width: 0;
    height: 100%;
    background-color: #2e3a42; /* Голубой цвет */
    z-index: -1;
    transition: width 0.1s ease-in-out;
}
.flight-card:hover::before {
    width: 100%; /* Полностью покрывает карточку */
}
    </style>
</head>
<body>
    <div class="container">
        <h1>ATC24 Flight Schedule</h1>
    </div>

    <div class="container">
        {% for icao, _ in airports %}
        <div class="airport-section">
            <h2>{{ AIRPORTS[icao].name }} ({{ icao }})</h2>
            
            <h3>Departures</h3>
            {% if departures.get(icao, []) %}
                {% for flight in departures.get(icao, []) %}
                <div class="flight-card">
                    <!-- Время вылета -->
                    <div class="flight-time">
                        {{ flight.time if 'time' in flight else '--:--' }}
                        {% if flight.live %}<span class="live-badge">LIVE</span>{% endif %}
                    </div>
                    
                    <!-- Информация о состоянии рейса -->
                    <div class="flight-state-icon">
                        <img src="{{ flight.state | icon_for_state }}" alt="Flight State Icon" title="{{ flight.state | description_for_state }}"/>
                    </div>
                    
                    <!-- Маршрут и название самолета -->
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
                </div>
                {% endfor %}
            {% else %}
                <div class="no-flights">No scheduled departures</div>
            {% endif %}
            
            <div class="section-divider"></div>
            
            <h3>Arrivals</h3>
            {% if arrivals.get(icao, []) %}
                {% for flight in arrivals.get(icao, []) %}
                <div class="flight-card">
                    <!-- Время вылета -->
                    <div class="flight-time">
                        {{ flight.time if 'time' in flight else '--:--' }}
                        {% if flight.live %}<span class="live-badge">LIVE</span>{% endif %}
                    </div>
                    
                    <!-- Информация о состоянии рейса -->
                    <div class="flight-state-icon">
                        <img src="{{ flight.state | icon_for_state }}" alt="Flight State Icon" title="{{ flight.state | description_for_state }}"/>
                    </div>
                    
                    <!-- Маршрут и название самолета -->
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
                </div>
                {% endfor %}
            {% else %}
                <div class="no-flights">No scheduled arrivals</div>
            {% endif %}
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""


def icon_for_state(state):
    icons = {
        0: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/boarding.png',
        1: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/departure1.png',
        2: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/departure.png',
        3: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/cruise.png',
        4: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/arrival.png',
        5: 'https://raw.githubusercontent.com/deepslatetile/24schedule/c5cbe3d8bc5e3028a7872edd61ce78172aba82c9/ground.png'
    }
    return icons.get(state, '')


def description_for_state(state):
    descriptions = {
        0: 'Boarding',
        1: 'Departing',
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
    # Загружаем актуальные flight plans
    flight_plans = get_recent_flight_plans()
    current_time = datetime.now()

    # Очищаем предыдущие данные
    flights_data['departures'] = defaultdict(list)
    flights_data['arrivals'] = defaultdict(list)

    # Обрабатываем каждый flight plan
    for callsign, plan in flight_plans.items():
        if not all(key in plan for key in ['departing', 'arriving', 'aircraft']):
            continue
        
        # Нормализуем callsign
        callsign = callsign.replace("-", "").replace(" ", "").upper()
        flight_level = str(plan.get('flightlevel', '0')).replace('FL', '').strip()

        flight_info = {
            'callsign': callsign,
            'aircraft': plan['aircraft'],
            'flightlevel': flight_level,
            'playerName': plan.get('robloxName', 'Unknown'),
            'timestamp': plan['timestamp'],
            'time': datetime.strptime(plan['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M'),
            'live': callsign in [acft.replace("-", "").replace(" ", "").upper() for acft in flights_data['aircrafts']],
            'is_local': plan['departing'] == plan['arriving'],
            'departing_name': AIRPORTS.get(plan['departing'], {}).get('name', plan['departing']),
            'arriving_name': AIRPORTS.get(plan['arriving'], {}).get('name', plan['arriving'])
        }

        # Добавляем в departures
        if not flight_info['is_local'] or plan['departing'] in AIRPORTS:
            departure_info = flight_info.copy()
            departure_info.update({
                'departing': plan['departing'],
                'arriving': plan['arriving'],
                'state': 0
            })
            flights_data['departures'][plan['departing']].append(departure_info)

        # Добавляем в arrivals
        if not flight_info['is_local'] or plan['arriving'] in AIRPORTS:
            arrival_info = flight_info.copy()
            arrival_info.update({
                'departing': plan['departing'],
                'arriving': plan['arriving'],
                'state': 0
            })
            flights_data['arrivals'][plan['arriving']].append(arrival_info)

    # Обновляем статусы для активных рейсов
    update_flight_statuses()

    # Сортируем аэропорты по активности
    sorted_airports = get_sorted_airports()

    return render_template_string(
        HTML_TEMPLATE,
        airports=sorted_airports,
        departures=flights_data['departures'],
        arrivals=flights_data['arrivals'],
        AIRPORTS=AIRPORTS,
        current_time=current_time.strftime('%Y-%m-%d %H:%M:%S')
    )


def get_flight_state(callsign, acft_data):
    """Определяет state со строгой последовательностью переходов"""
    if not acft_data:
        wh_log(f"{callsign} check: No aircraft data")
        return None

    # Нормализуем callsign для поиска в flight plans
    normalized_callsign = callsign.replace("-", "").replace(" ", "").upper()
    
    # Загружаем flight plans
    flight_plans = load_flight_plans()
    
    # Ищем flight plan с нормализованным callsign
    fpl = None
    for plan_callsign, plan in flight_plans.items():
        if plan_callsign.replace("-", "").replace(" ", "").upper() == normalized_callsign:
            fpl = plan
            break

    if not fpl:
        wh_log(f"{normalized_callsign} check: Flight plan not found")
        return None

    # Получаем предыдущее состояние
    prev_state = flights_data['flight_states'].get(normalized_callsign, 0)

    # Извлекаем данные о самолете
    speed = acft_data.get('speed', 0)
    is_on_ground = acft_data.get('isOnGround', True)
    altitude = acft_data.get('altitude', 0)

    # Определяем целевой flight level из плана полета
    flight_level = 0
    try:
        flight_level = int(fpl["flightlevel"]) * 100
    except:
        flight_level = 0
        wh_log(f"{normalized_callsign} check: Invalid flight level in FPL: {fpl.get('flightlevel', 'N/A')}")

    # Логируем параметры перед определением состояния
    log_message = (
        f"{normalized_callsign}\n"
        f"FPL FL: {flight_level}ft, "
        f"{altitude}ft "
        f"{speed}kts "
        f"{is_on_ground} "
        f"{prev_state}\n"
    )
    print(log_message)

    # Определяем новое состояние
    new_state = prev_state

    if is_on_ground:
        if speed > 10 and prev_state == 0:
            new_state = 1  # departing
        elif speed < 30 and prev_state in [2, 3, 4]:
            new_state = 5  # landed
    else:
        if prev_state == 1:
            new_state = 2  # climbing
        elif prev_state == 2 and altitude > (flight_level - 300):
            new_state = 3  # cruise
        elif prev_state == 3 and altitude < (flight_level - 400):
            new_state = 4  # descending

    # Логируем результат проверки состояния
    if new_state != prev_state:
        state_change_msg = (
            f"{normalized_callsign} STATE CHANGE: "
            f"{prev_state}->{new_state} | "
            f"FL: {flight_level}ft | "
            f"Alt: {altitude}ft | "
            f"Speed: {speed}kts | "
            f"OnGround: {is_on_ground}"
        )
        print(state_change_msg)
        flights_data['flight_states'][normalized_callsign] = new_state
    else:
        #print(f"{normalized_callsign} state remains {prev_state}")
        pass

    return new_state


def update_flight_statuses():
    for callsign, acft_data in flights_data['aircrafts'].items():
        # Нормализуем callsign для поиска
        normalized_callsign = callsign.replace("-", "").replace(" ", "").upper()

        # Обновляем departures
        for airport in flights_data['departures']:
            for flight in flights_data['departures'][airport]:
                if flight['callsign'] == normalized_callsign:
                    flight['live'] = True
                    flight['state'] = get_flight_state(callsign, acft_data)

        # Обновляем arrivals
        for airport in flights_data['arrivals']:
            for flight in flights_data['arrivals'][airport]:
                if flight['callsign'] == normalized_callsign:
                    flight['live'] = True
                    flight['state'] = get_flight_state(callsign, acft_data)
                    

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
    app.run(host='0.0.0.0', port=2424, debug=True, use_reloader=False)


if __name__ == '__main__':
    ws_thread = threading.Thread(target=run_websocket, daemon=True)
    ws_thread.start()
    run_flask()