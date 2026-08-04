import zmq
from datetime import datetime


# connect to open-meteo API

# Forecast API: https://api.open-meteo.com/v1/forecast


# Historical API: https://archive-api.open-meteo.com/v1/archive



# need to get daily data given date range

# get weather data
def get_weather_data():
    # get weather data from open meteo API
    # if date range is within 16 days, use forecast API
    # if date range is beyond 16 days, use historical API
    pass

# Main function ZeroMQ

def main ():
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
        latitude = request.get("lat")
        longitude = request.get("lon")
        start_date = request.get("start_date")
        end_date = request.get("end_date")

        # if any field is missing, return error
        if not latitude or not longitude or not start_date or not end_date:
            response = {"error": "Missing required fields: lat, lon, start_date, end_date"}
            socket.send_json(response)
            continue

        # get weather data from open meteo API
        response = get_weather_data(latitude, longitude, start_date, end_date)

        # send response back to client
        socket.send_json(weather_data)
