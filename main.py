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


def load_flight_plans():
    if os.path.exists(FLIGHT_PLANS_FILE):
        with open(FLIGHT_PLANS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_flight_plans(plans):
    with open(FLIGHT_PLANS_FILE, 'w') as f:
        json.dump(plans, f)


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
    for callsign, acft_data in data.items():
        flights_data['aircrafts'][callsign] = acft_data
        flights_data['aircrafts'][callsign]['live'] = True
        flights_data['aircrafts'][callsign]['callsign'] = callsign


def new_fpl(data):
    callsign = data['callsign']
    print(f"fpl {callsign}")
    data['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    plans = load_flight_plans()
    plans[callsign] = data
    save_flight_plans(plans)

    departing = data['departing']
    arriving = data['arriving']

    flight_info = {
        'callsign': callsign,
        'aircraft': data['aircraft'],
        'arriving': arriving,
        'status': 'scheduled',
        'live': False,
        'state': 0
    }
    flights_data['departures'][departing].append(flight_info)

    flight_info = {
        'callsign': callsign,
        'aircraft': data['aircraft'],
        'departing': departing,
        'status': 'scheduled',
        'live': False,
        'state': 0
    }
    flights_data['arrivals'][arriving].append(flight_info)


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
                        <img src="/static/{{ flight.state | icon_for_state }}" alt="Flight State Icon" title="{{ flight.state | description_for_state }}"/>
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
                        <img src="/static/{{ flight.state | icon_for_state }}" alt="Flight State Icon" title="{{ flight.state | description_for_state }}"/>
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
        0: 'ground.png',
        1: 'departure.png',
        2: 'departure.png',
        3: 'cruise.png',
        4: 'arrival.png',
        5: 'ground.png'
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
    flight_plans = cleanup_old_plans()
    current_time = datetime.now()

    # Очищаем предыдущие данные
    flights_data['departures'] = defaultdict(list)
    flights_data['arrivals'] = defaultdict(list)

    # Обрабатываем каждый flight plan
    for callsign, plan in flight_plans.items():
        if not all(key in plan for key in ['departing', 'arriving', 'aircraft']):
            continue
        flight_level = str(plan.get('flightlevel', '0')).replace('FL', '').strip()

        print(plan.get('realcallsign', callsign).replace('-', ' ').replace(' ', '-').lower(), plan.get('realcallsign', callsign).replace('-', ' ').replace(' ', '-').lower() in [acft.lower().replace('-', ' ').replace(' ', '-') for acft in flights_data['aircrafts']])

        flight_info = {
            'callsign': callsign,
            'realcallsign': plan.get('realcallsign', callsign),
            'aircraft': plan['aircraft'],
            'flightlevel': flight_level,
            'playerName': plan.get('robloxName', 'Unknown'),
            'timestamp': plan['timestamp'],
            'time': datetime.strptime(plan['timestamp'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M'),
            'live': plan.get('realcallsign', callsign).replace('-', ' ').replace(' ', '-').lower() in [acft.lower().replace('-', ' ').replace(' ', '-') for acft in flights_data['aircrafts']],
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


def get_flight_state(callsign, acft_data, fpl=None):
    """Определяет state со строгой последовательностью переходов"""
    if not acft_data:
        print(f'no acft data for {callsign}')
        return None

    # Получаем предыдущее состояние
    prev_state = flights_data['flight_states'].get(callsign)

    # Извлекаем данные о самолете
    speed = acft_data.get('speed', 0)
    is_on_ground = acft_data.get('isOnGround', True)
    altitude = acft_data.get('altitude', 0)

    # Определяем целевой flight level из плана полета
    if fpl:
        try:
            flight_level = int(fpl.get('flightlevel', '0').replace('FL', '')) * 100
        except:
            flight_level = 0
    else:
        flight_level = 0

    # Определяем RAW состояние без учета предыдущего
    new_state = prev_state if prev_state is not None else 0

    if speed > 10 and is_on_ground and prev_state == 0:
        new_state = 1  # Руление
        print(new_state, callsign)
    if not is_on_ground and altitude < (flight_level - 300) and prev_state < 2:
        new_state = 2  # Набор высоты
        print(new_state, callsign)
    if not is_on_ground and flight_level - 300 < altitude and (prev_state == 2):
        new_state = 3  # Крейсерский полет
        print(new_state, callsign)
    if not is_on_ground and altitude < (flight_level - 500) and prev_state != 1:
        new_state = 4  # Снижение
        print(new_state, callsign)
    if is_on_ground and speed < 30 and prev_state == 4:
        new_state = 5  # Посадка
        print(new_state, callsign)

    # Если предыдущего состояния нет - сохраняем текущее
    if prev_state is None and new_state is not None:
        flights_data['flight_states'][callsign] = new_state
        return new_state

    # Если состояние не изменилось - возвращаем предыдущее
    if new_state == prev_state:
        return prev_state

    # Разрешаем переход только на следующее состояние
    if new_state is not None:
        if new_state == prev_state + 1:
            flights_data['flight_states'][callsign] = new_state
            return new_state

    # Во всех остальных случаях возвращаем предыдущее состояние
    return prev_state


def update_flight_statuses():
    for callsign, acft_data in flights_data['aircrafts'].items():

        for airport in flights_data['departures']:
            for flight in flights_data['departures'][airport]:
                if flight['realcallsign'] == callsign:
                    flight['live'] = True
                    flight['state'] = get_flight_state(callsign, acft_data)
                    print(f"Updated flight status for {callsign}: live={flight['live']}, state={flight['state']}")

        for airport in flights_data['arrivals']:
            for flight in flights_data['arrivals'][airport]:
                if flight['realcallsign'] == callsign:
                    flight['live'] = True
                    flight['state'] = get_flight_state(callsign, acft_data)
                    print(f"Updated flight status for {callsign}: live={flight['live']}, state={flight['state']}")


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
