import requests
from  flask import Flask, Response, request, stream_with_context
from datetime import datetime
app = Flask(__name__)
RESTRICT_DATE = "2022-02-20T00:00:00.000000Z"
# Local avaliable pypi proxy nexus repository pointed to https://pypi.org/
REPO_PYPI = 'http://localhost:8081/repository/pypi'
# Local avaliable raw inline proxy nexus repository pointed to https://pypi.org/pypi
REPO_PYPI_FEED = 'http://localhost:8081/repository/pypi-feed'

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
 
