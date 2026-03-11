from pathlib import Path
import pandas as pd

file_path = Path("data/stations.txt")

with open(file_path) as f:
    lines = f.readlines()

satellites = []

for i in range(0,len(lines),6):
    name = lines[i].strip()
    line1 = lines[i+2].split()
    line2 = lines[i+4].split()


    
    designator = float(line2[1])
    inclination = float(line2[2])
    right_ascension = float(line2[3])
    eccentricity = float(('0.'+line2[4]))
    perigee = float(line2[5])
    mean_anomaly = float(line2[6])
    mean_motion = float(line2[7])

    satellites.append({
        "satellite":name,
        "inclination":inclination,
        "eccentricity":eccentricity,
        "mean_motion":mean_motion,
    })

df = pd.DataFrame(satellites)
df.to_csv("data/satellites_clean.csv", index=False)

print(df.head())
