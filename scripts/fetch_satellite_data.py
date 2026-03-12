import requests
from pathlib import Path

url = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=tle"

response = requests.get(url)

data_path = Path("data/active_satellites.txt")

data_path.parent.mkdir(parents=True, exist_ok=True)

with open(data_path, "w") as f:
    f.write(response.text)

print("Satellite data downloaded!")