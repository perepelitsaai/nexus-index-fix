import requests
from flask import Flask, send_file
from datetime import datetime

from threading import Lock
import json
import os
import io

app = Flask(__name__)
RESTRICT_DATE = "2021-01-01T00:00:00.000000Z"
restrict_date_parsed = datetime.fromisoformat(RESTRICT_DATE.replace('Z', '+00:00'))
REPO_NAME = "maven-central"
REPO_MAVEN_NEXUS = f'http://192.168.122.132:8081/repository/{REPO_NAME}/'
REPO_DATA_NEXUS = 'http://192.168.122.132:8081/repository/data2/'
ORIGINAL_NEXUS_HOST = "192.168.122.132:8081"
NEXUS_HOST = "192.168.122.1"
REPO_MAVEN_PATH = f"/repository/{REPO_NAME}/"

lock = Lock()
lock2 = Lock()

# paths
white_list = set()

# { path: ts }
dates = {}

def get_date(path, index_url):
    try:
        req = requests.head(f'{index_url}{path}', timeout=5)
        last_mod = req.headers["Last-Modified"]
        last_updated_pattern = "%a, %d %b %Y %H:%M:%S %Z"
        dt = datetime.strptime(last_mod, last_updated_pattern)
        return dt


    except Exception as e:
        return None

def write_to_file(name, jsonobj):
    with open(name, "w") as f:
        s = json.dumps(jsonobj, indent=4)
        f.write(s)

def path_to_str(path):
    return path.replace("/",".") + ".json"

def put_json_to_nexus(path, jobj):
    fname = path_to_str(path)
    write_to_file(fname, jobj)
    with open(fname, 'rb') as f:
        r = requests.put(f"{REPO_DATA_NEXUS}{fname}", auth=("admin", "12345"), data=f)
    os.remove(fname)

def get_from_nexus(path):
    fname = path_to_str(path)
    return requests.get(f"{REPO_DATA_NEXUS}{fname}")

def get_ts(path):
    ts = dates.get(path)
    print("get_ts from dates", ts)
    if ts:
        return ts

    response = get_from_nexus(path)
    if response.status_code == 200:
        print("get_ts", 200)
        # ts, date format
        ts, _ = response.json()
        print("get_ts, ts=", ts)
        dates[path] = ts
        return ts
    else:
        dt = get_date(path, "https://repo1.maven.org/maven2/")
        print("get_ts, dt=", dt)
        if dt:
            put_json_to_nexus(path, (dt.timestamp(), str(dt)))
            dates[path] = dt.timestamp()
            return dt.timestamp()
    return None

def is_valid(path):

    ts = get_ts(path)
    if ts and ts < restrict_date_parsed.timestamp():
        return True

    lock.acquire()
    valid = path in white_list
    lock.release()
    return valid

@app.route(f"{REPO_MAVEN_PATH}<path:path>")
def maven_index(path):
    print(f"maven index, path={path}")

    if not (path.endswith(".jar") or path.endswith(".zip") or path.endswith(".aar")):
        resp = requests.get(f"{REPO_MAVEN_NEXUS}{path}", stream=True)
        return resp.raw.read(), resp.status_code, resp.headers.items()

    if is_valid(path):
        resp = requests.get(f"{REPO_MAVEN_NEXUS}{path}")
        if resp.status_code != 200:
            return resp.raw.read(), resp.status_code, resp.headers.items()

        print("maven index", resp.headers)
        #return Response(stream_with_context(resp.iter_content(chunk_size=1024)),
        #                content_type=resp.headers['content-type'])
        download_name = path.split("/")[-1]
        return send_file(io.BytesIO(resp.content),
                         as_attachment = True,
                         download_name= download_name,
                         mimetype = resp.headers['content-type'])
    else:
        return "Forbidden", 403
