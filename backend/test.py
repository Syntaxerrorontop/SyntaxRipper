import requests
from pprint import pprint
api_key = "b0bb86e3" # Bekommst du sofort per Mail
movie_title = "Resident Evil: Welcome to Raccoon City"

#url = f"http://www.omdbapi.com/?t={movie_title}&apikey={api_key}"
#response = requests.get(url).json()
#pprint(response)
#print(f"Titel: {response.get('Title')}")
#print(f"Poster URL: {response.get('Poster')}")
#print(f"IMDb Rating: {response.get('imdbRating')}")

import requests
import json

imdb_id = "tt6920084"

# Wichtig: 'plot=full' sorgt für die lange Beschreibung
url = f"http://www.omdbapi.com/?i={imdb_id}&apikey={api_key}&plot=full"

data = requests.get(url).json()

# Ich gebe das mal schön formatiert aus, damit du die Struktur siehst
print(json.dumps(data, indent=4))