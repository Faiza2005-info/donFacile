import requests

def geocode_location(location, api_key):
    url = f"https://api.opencagedata.com/geocode/v1/json?q={location}&key={api_key}&language=fr&limit=1"
    try:
        response = requests.get(url)
        data = response.json()
        if data['results']:
            lat = data['results'][0]['geometry']['lat']
            lng = data['results'][0]['geometry']['lng']
            return lat, lng
    except Exception as e:
        print(f"Erreur géocodage : {e}")
    return None, None
