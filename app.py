import requests
from flask import Flask, Response, request, stream_with_context
from datetime import datetime
from dotenv import load_dotenv
import os
import io
from packaging import parse

load_dotenv()
RESTRICT_DATE = os.getenv("RESTRICT_DATE")
# Local available pypi proxy nexus repository pointing to https://pypi.org/
REPO_PYPI = os.getenv("REPO_PYPI")
# Local available raw inline proxy nexus repository pointing to https://pypi.org/pypi
REPO_PYPI_FEED =  os.getenv("REPO_PYPI_FEED")

# Full url of nexus npm repo, like http://192.168.122.135:8081/repository/npm-proxy/
REPO_NPM = os.getenv("REPO_NPM")

# The location part of npm repo url, like "/repository/npm-proxy/"
REPO_NPM_PATH = os.getenv("REPO_NPM_PATH")

# Nexus host to be placed into headers, like nexus domain name
NEXUS_HOST = os.getenv("NEXUS_HOST")

app = Flask(__name__)

def get_package_links(package_name):
    return requests.get(f"{REPO_PYPI}/simple/{package_name}").text

def get_package_meta(package_name):
    return requests.get(f"{REPO_PYPI_FEED}/{package_name}/json").json()
 
def compare_dates(date1):
    parsed_date1 = datetime.fromisoformat(date1.replace('Z', '+00:00'))
    parsed_date2 = datetime.fromisoformat(RESTRICT_DATE.replace('Z', '+00:00'))
    return parsed_date1 > parsed_date2

@app.route("/repository/pypi/simple/<package_name>/")
def simple(package_name):
    package_links = get_package_links(package_name)
    package_meta = get_package_meta(package_name)
    new_links = []
    for link in package_links.split("\n"):
        link = link.strip()
        if link.startswith("<a href"):
           link_version = link.split('/')[4]
           # if not withdrawn
           if package_meta.get('releases').get(link_version):
                link_version_upload_date = package_meta.get('releases').get(link_version)[0].get('upload_time_iso_8601')
                if not compare_dates(link_version_upload_date):
                        print(f"{link_version} == {link_version_upload_date}")
                        new_links.append(link)
        else:
            new_links.append(link)
    return "\n".join(new_links)

 
@app.route("/repository/pypi/packages/<package_name>/<package_version>/<package_data>")
def download(package_name,package_version,package_data):
    try:
        package_meta = get_package_meta(package_name)
        link_version_upload_date = package_meta.get('releases').get(package_version)[0].get('upload_time_iso_8601')
        if compare_dates(link_version_upload_date):
            print(f"{package_version} == {link_version_upload_date}")
            return f"Запрещено к скачиванию. Дата публикации {link_version_upload_date}", 403
    except Exception as e:
        return str(e), 404
    req = requests.get(f"{REPO_PYPI}/packages/{package_name}/{package_version}/{package_data}", stream = True)
    return Response(stream_with_context(req.iter_content(chunk_size=1024)), content_type = req.headers['content-type'])

def get_npm_latest_version(data):
    versions = []
    for key in data["versions"].keys():
        versions.append(key)

    if len(versions) == 0:
        return

    vers = []
    for v in versions:
        no_letters = True
        # make sure there is no letters in version
        for c in v:
            if not (c.isdigit() or c == "."):
                no_letters = False
                break
        if no_letters:
            vers.append(v)

        if len(vers) > 0:
            vers.sort(key=parse)
            return vers[-1]
        else:
            versions.sort(key=parse)
            return versions[-1]

@app.route(f"{REPO_NPM_PATH}<path:package_name>")
def index_npm(package_name):
    # ToDo: Менять версию latest в индексе!

    # Headers нужны для корректного формирования tarball path в индексе
    headers = {'Host': NEXUS_HOST}
    response = requests.get(f"{REPO_NPM}{package_name}", headers=headers)
    if response.status_code != 200:
        return response.text, response.status_code
    
    try:
        npm_index = response.json()
    except:
        return response.content, response.status_code

    versions_to_remove = []

    # { "1.2.11": "2015-07-17T03:21:56.994Z", "1.2.10": "2015-07-01T20:17:54.682Z",}
    versions = npm_index.get('time')
    if versions is None:
        return "Incorrect version part of the index", 404

    for version, date in versions.items():
        if version not in ['modified', 'created']:
            if compare_dates(date):            
                versions_to_remove.append(version)

    for version in versions_to_remove:
        if version in npm_index['versions']:
            npm_index['versions'].pop(version)
        npm_index['time'].pop(version)

    latest = get_npm_latest_version(npm_index)
    if latest:
        npm_index["dist-tags"] = { "latest": latest}
    return npm_index


@app.route(f"{REPO_NPM_PATH}<path:scope_package>/-/<package_and_version>.tgz")
def npm_index_direct_download(scope_package, package_and_version):
    # app.logger.info('this is an INFO message')
    # print("npm_index_direct_download", flush=True)
    package_name = scope_package
    # check for path like /repository/npm-proxy/@angular/core/-/core-1.2.3.tgz
    parts = scope_package.split("/")
    if len(parts) > 1:
        package_name = parts[1]

    # skip "-" after package_name to get package version
    p_version = package_and_version.replace(package_name, "")
    if len(p_version) == 0:
        return "Incorrect package version", 403
    p_version = p_version[1:]
    #  print(package_name,package_name2,package_version)
    response = requests.get(f"{REPO_NPM}{scope_package}")
    if response.status_code != 200:
        return "Incorrect package name", 403

    npm_index = response.json()
    if npm_index.get('time') is None:
        return f"Forbidden. Incorrect index", 403

    date = npm_index.get('time').get(p_version)
    if compare_dates(date):
        return f"Forbidden. Last modified {date}", 403

    resp = requests.get(f"{REPO_NPM}{scope_package}/-/{package_and_version}.tgz")
    if resp.status_code == 200:
        return send_file(io.BytesIO(resp.content), as_attachment = True, download_name = f"{package_and_version}.tgz", mimetype = "application/gzip")
    else:
        return resp.text, 404

@app.route(f"{REPO_NPM_PATH}<path:path>", methods=["POST"])
def post(path):
    resp = requests.post(f"{REPO_NPM}{path}")
    return resp.raw.read(), resp.status_code, resp.headers.items()
