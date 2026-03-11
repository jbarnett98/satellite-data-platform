import requests
from pathlib import Path

url = "https://celestrak.org/NORAD/elements/stations.txt"

response = requests.get(url)

data_path = Path("data/stations.txt")

data_path.parent.mkdir(parents=True, exist_ok=True)

with open(data_path, "w") as f:
    f.write(response.text)

print("Satellite data downloaded!")