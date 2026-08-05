from datetime import datetime, timedelta
import requests
import zmq



def get_forecast(latitude, longitude, departure, return_date):
    """Get weather forecast from Open-Meteo API for dates within 16 days."""
    url = "https://api.open-meteo.com/v1/forecast" # connect to forecast API
    # set parameters for API request
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "weathercode"],
        "start_date": departure,
        "end_date": return_date,
        "timezone": "auto"
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def get_historical(latitude, longitude, departure, return_date):
    """Get historical weather averages from Open-Meteo API for dates beyond 16 days."""
    url = "https://archive-api.open-meteo.com/v1/archive"

    # use same dates from last year for historical averages
    dep = datetime.strptime(departure, "%Y-%m-%d")
    ret = datetime.strptime(return_date, "%Y-%m-%d")
    last_year_dep = dep.replace(year=dep.year - 1).strftime("%Y-%m-%d")
    last_year_ret = ret.replace(year=ret.year - 1).strftime("%Y-%m-%d")

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "weathercode"],
        "start_date": last_year_dep,
        "end_date": last_year_ret,
        "timezone": "auto"
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return None

def parse_weathercode(code):
    """Convert Open-Meteo weather code to human readable condition."""
    conditions = {
        0: "Clear Sky",
        1: "Partly Cloudy", 2: "Partly Cloudy", 3: "Partly Cloudy",
        45: "Foggy", 48: "Foggy",
        51: "Drizzle", 53: "Drizzle", 55: "Drizzle",
        61: "Rainy", 63: "Rainy", 65: "Rainy",
        71: "Snowy", 73: "Snowy", 75: "Snowy",
        80: "Rain Showers", 81: "Rain Showers", 82: "Rain Showers",
        95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm"
    }
    return conditions.get(code, "Unknown")

def build_daily_breakdown(data, departure, is_historical=False):
    """Build daily weather breakdown from API response."""
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    highs = daily.get("temperature_2m_max", [])
    lows = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    codes = daily.get("weathercode", [])

    breakdown = []
    for i, date in enumerate(dates):
        # if historical, replace last year's date with actual travel date
        if is_historical:
            actual_date = datetime.strptime(departure, "%Y-%m-%d") + timedelta(days=i)
            date_str = actual_date.strftime("%Y-%m-%d")
        else:
            date_str = date

        breakdown.append({
            "date": date_str,
            "high": highs[i] if highs[i] is not None else "N/A",
            "low": lows[i] if lows[i] is not None else "N/A",
            "conditions": parse_weathercode(codes[i]) if codes[i] is not None else "Unknown",
            "precipitation_mm": precip[i] if precip[i] is not None else 0.0
        })

    return breakdown

def get_weather_data(latitude, longitude, departure, return_date):
    """Main function to get weather data — forecast or historical."""

    # check if dates are within 16 days
    today = datetime.today()
    dep_date = datetime.strptime(departure, "%Y-%m-%d")
    days_until_trip = (dep_date - today).days

    if days_until_trip <= 16:
        # use forecast
        print(f"Fetching forecast for {departure} to {return_date}...")
        data = get_forecast(latitude, longitude, departure, return_date)
        is_historical = False
        data_type = "forecast"
    else:
        # use historical averages
        print("Dates beyond 16 days, fetching historical averages...")
        data = get_historical(latitude, longitude, departure, return_date)
        is_historical = True
        data_type = "historical"

    if data is None:
        return {"error": "Network error: Unable to reach weather service. Please try again later."}

    # build daily breakdown
    daily = build_daily_breakdown(data, departure, is_historical)

    if not daily:
        return {"error": "No weather data available for the given dates."}

    return {
        "data_type": data_type,
        "departure": departure,
        "return": return_date,
        "unit": "C",
        "daily": daily
    }

# Main function ZeroMQ

def main ():
    """Run the ZeroMQ REP server: listen on port 3015 and serve weather requests."""
    context = zmq.Context()
    socket = context.socket(zmq.REP)
    socket.bind("tcp://*:3015")

    # message to show that service is running
    print("🌤️ Weather Service is running on port 3015...")
    print("Waiting for requests...")

    while True:
        request = socket.recv_json()
        print(f"Received: {request}")

        # required fields: latitude, longitude, start_date, end_date
        latitude = request.get("latitude")
        longitude = request.get("longitude")
        start_date = request.get("start_date")
        end_date = request.get("end_date")

        # if any field is missing, return error
        if latitude is None or longitude is None or not start_date or not end_date:
            response = {"error": "Missing required fields: latitude, longitude, start_date, end_date"}
            socket.send_json(response)
            continue

        # get weather data from open meteo API
        response = get_weather_data(latitude, longitude, start_date, end_date)

        # send response back to client
        socket.send_json(response)

if __name__ == "__main__":
    main()
