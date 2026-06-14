from flask import Flask, render_template, jsonify
from datetime import datetime, timedelta
from scraper import get_vessel_status, get_berth_schedule
import threading
import time
import scraper
import os   

print("사용 중인 scraper 위치:", scraper.__file__)

app = Flask(__name__)

latest_berths = []
latest_schedules = []
latest_time = "-"
history = []


def safe_int(value):
    try:
        return int(value)
    except:
        return 0


def get_qc_done_total(qc):
    return safe_int(qc["unload_done"]) + safe_int(qc["load_done"])


def add_hourly_count(berths):
    global history

    now = datetime.now()

    history.append({
        "time": now,
        "berths": berths
    })

    limit = now - timedelta(hours=1)

    while history and history[0]["time"] < limit:
        history.pop(0)

    old_data = history[0]["berths"] if history else []

    for berth in berths:
        old_berth = next(
            (b for b in old_data if b["name"] == berth["name"]),
            None
        )

        for qc in berth.get("qc_list", []):
            current_done = get_qc_done_total(qc)
            hourly_count = 0

            if old_berth:
                old_qc = next(
                    (q for q in old_berth.get("qc_list", []) if q["qc"] == qc["qc"]),
                    None
                )

                if old_qc:
                    old_done = get_qc_done_total(old_qc)
                    hourly_count = current_done - old_done

            qc["hourly_count"] = hourly_count

    return berths


def background_collector():
    global latest_berths, latest_schedules, latest_time

    while True:
        try:
            print("DGT 데이터 수집 중...")

            berths = get_vessel_status()
            berths = add_hourly_count(berths)

            latest_berths = berths
            latest_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            print("latest_berths 저장값:")
            for b in latest_berths:
                print(b["name"], b["ship"])

            # 접안 예정은 1분마다 갱신
            if not latest_schedules or datetime.now().second < 10:
                latest_schedules = get_berth_schedule()

            print("DGT 데이터 수집 완료:", latest_time)

        except Exception as e:
            print("백그라운드 수집 오류:", e)

        time.sleep(10)


@app.route("/")
def home():
    return render_template(
        "index.html",
        berths=latest_berths,
        schedules=latest_schedules,
        now=latest_time
    )


@app.route("/data")
def data():
    print("/data 응답값:")
    for b in latest_berths:
        print(b["name"], b["ship"])

    return jsonify({
        "now": latest_time,
        "berths": latest_berths,
        "schedules": latest_schedules
    })


if __name__ == "__main__":
    collector_thread = threading.Thread(
        target=background_collector,
        daemon=True
    )
    collector_thread.start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)