from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import re


VESSEL_NAME_CACHE = {}


def safe_int(value):
    return int(value) if str(value).isdigit() else 0


def clean_ship_code(code):
    if not code:
        return "-"

    code = str(code).strip().upper()
    code = code.split("/")[0]
    code = code.replace("-", "")

    return code


def display_code(code):
    code = clean_ship_code(code)

    if not code or code == "-":
        return "-"

    m = re.match(r"([A-Z]{3,5})(\d{3})", code)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    return code


def display_ship(code):
    code = clean_ship_code(code)

    if not code or code == "-":
        return "대기중"

    name = VESSEL_NAME_CACHE.get(code)

    if name:
        return f"{name} ({display_code(code)})"

    return display_code(code)


def make_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--blink-settings=imagesEnabled=false")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    driver.set_script_timeout(30)

    return driver


def extract_detail_value(text, label):
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for i, line in enumerate(lines):
        if label in line and i + 1 < len(lines):
            return lines[i + 1].strip()

    return None


def scrape_vessel_name_map(driver):
    vessel_map = {}

    try:
        print("[MAP] berthScheduleG 접속 시작")
        driver.get("https://info.dgtbusan.com/DGT/esvc/vessel/berthScheduleG")
        print("[MAP] berthScheduleG 접속 완료")

        time.sleep(2)

        detail_divs = driver.find_elements(By.XPATH, "//div[starts-with(@id, 'detail_')]")
        print("detail div 개수:", len(detail_divs))

        for div in detail_divs:
            try:
                div_id = div.get_attribute("id")
                if not div_id:
                    continue

                raw_code = div_id.replace("detail_", "")
                code = clean_ship_code(raw_code)

                text = (
                    div.get_attribute("textContent")
                    or div.get_attribute("innerText")
                    or div.text
                    or ""
                )

                if not text.strip():
                    continue

                vessel_name = extract_detail_value(text, "모선명")
                voyage_text = extract_detail_value(text, "모선항차")

                if voyage_text:
                    m = re.search(r"([A-Z]{3,5}-?\d{3})", voyage_text)
                    if m:
                        code = clean_ship_code(m.group(1))

                if vessel_name and code:
                    vessel_map[code] = vessel_name

            except Exception as e:
                print("detail 파싱 오류:", repr(e))
                continue

    except Exception as e:
        print("선박명 맵 생성 오류:", repr(e))

    print("선박명 맵 개수:", len(vessel_map))
    return vessel_map


def parse_qc_list(section_lines):
    qc_list = []

    for i, line in enumerate(section_lines):
        m = re.search(r"^(\d+)\(총 작업량\s*:\s*(\d+)\)", line)
        if not m:
            continue

        qc_no = m.group(1)
        total = m.group(2)

        unload_done = "-"
        load_done = "-"
        unload_remain = "-"
        load_remain = "-"

        if i + 2 < len(section_lines):
            parts = section_lines[i + 2].split()
            if len(parts) >= 4:
                unload_done = parts[0]
                load_done = parts[1]
                unload_remain = parts[2]
                load_remain = parts[3]

        qc_list.append({
            "qc": qc_no,
            "total": total,
            "unload_total": safe_int(unload_done) + safe_int(unload_remain),
            "load_total": safe_int(load_done) + safe_int(load_remain),
            "unload_done": unload_done,
            "load_done": load_done,
            "unload_remain": unload_remain,
            "load_remain": load_remain
        })

    return qc_list


def parse_vessel_status(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    berths = []
    berth_indexes = []

    for idx, line in enumerate(lines):
        if line in ["B1", "B2", "B3", "B4"]:
            berth_indexes.append((line, idx))

    for n, (berth_name, i) in enumerate(berth_indexes):
        next_i = berth_indexes[n + 1][1] if n + 1 < len(berth_indexes) else len(lines)
        section = lines[i:next_i]

        progress = section[1] if len(section) > 1 else "0%"
        ship_code = section[2] if len(section) > 2 else "-"
        ship_code = clean_ship_code(ship_code)

        eta = section[3] if len(section) > 3 else "-"
        alongside = section[4] if len(section) > 4 else "-"
        start = section[5] if len(section) > 5 else "-"
        etd = section[6] if len(section) > 6 else "-"

        qc_list = parse_qc_list(section)

        try:
            progress_num = int(progress.replace("%", "")) if "%" in progress else 0
        except:
            progress_num = 0

        empty_ship_codes = ["-", "", "대기중", "없음", "null", "None"]
        is_wait = ship_code in empty_ship_codes and not qc_list

        if is_wait:
            progress_num = 0
            ship_name = "대기중"
            ship_code_display = "-"
        else:
            ship_name = display_ship(ship_code)
            ship_code_display = display_code(ship_code)

        unload_total = "-"
        load_total = "-"
        total = "-"

        for line in section:
            m = re.search(r"양하\((\d+)\)\s*/\s*적하\((\d+)\)\s*/\s*TOTAL\((\d+)\)", line)
            if m:
                unload_total = m.group(1)
                load_total = m.group(2)
                total = m.group(3)
                break

        unload_done_sum = sum(safe_int(qc["unload_done"]) for qc in qc_list)
        load_done_sum = sum(safe_int(qc["load_done"]) for qc in qc_list)
        unload_remain_sum = sum(safe_int(qc["unload_remain"]) for qc in qc_list)
        load_remain_sum = sum(safe_int(qc["load_remain"]) for qc in qc_list)

        berths.append({
            "name": berth_name,
            "ship": ship_name,
            "ship_code": ship_code_display,
            "qc": f"{len(qc_list)}G" if qc_list and not is_wait else "-",
            "qc_list": qc_list if not is_wait else [],
            "unload": f"{unload_done_sum} / {unload_total}" if not is_wait else "0 / -",
            "load": f"{load_done_sum} / {load_total}" if not is_wait else "0 / -",
            "shift": "-",
            "remain": f"양하 {unload_remain_sum} / 적하 {load_remain_sum}" if not is_wait else "양하 0 / 적하 0",
            "progress": progress_num,
            "status": "대기중" if is_wait else "작업중",
            "eta": eta if not is_wait else "-",
            "alongside": alongside if not is_wait else "-",
            "start": start if not is_wait else "-",
            "etd": etd if not is_wait else "-",
            "total": total
        })

    return berths


def get_vessel_status():
    global VESSEL_NAME_CACHE

    print("[1] 드라이버 생성 전")
    driver = make_driver()
    print("[2] 드라이버 생성 완료")

    try:
        if not VESSEL_NAME_CACHE:
            print("[3] 선박명 맵 수집 시작")
            VESSEL_NAME_CACHE = scrape_vessel_name_map(driver)
            print("[4] 선박명 맵 수집 완료:", len(VESSEL_NAME_CACHE))
        else:
            print("[3] 선박명 맵 캐시 사용:", len(VESSEL_NAME_CACHE))

        print("[5] vesselStatus 접속 시작")
        driver.get("https://info.dgtbusan.com/DGT/esvc/vessel/vesselStatus")
        print("[6] vesselStatus 접속 완료")

        time.sleep(2)

        print("[7] body 읽기 시작")
        text = driver.find_element(By.TAG_NAME, "body").text
        print("[8] body 읽기 완료:", len(text))

        print("[9] 파싱 시작")
        berths = parse_vessel_status(text)
        print("[10] 파싱 완료:", len(berths))

        for b in berths:
            print(b["name"], b["ship"])

        return berths

    except Exception as e:
        print("get_vessel_status 오류:", repr(e))
        return []

    finally:
        print("[11] 드라이버 종료")
        driver.quit()


def get_berth_schedule():
    global VESSEL_NAME_CACHE

    print("[S1] 스케줄 드라이버 생성")
    driver = make_driver()

    try:
        if not VESSEL_NAME_CACHE:
            print("[S2] 선박명 맵 없음 → 새로 수집")
            VESSEL_NAME_CACHE = scrape_vessel_name_map(driver)
        else:
            print("[S2] 선박명 맵 캐시 사용:", len(VESSEL_NAME_CACHE))

        print("[S3] berthScheduleG 접속 시작")
        driver.get("https://info.dgtbusan.com/DGT/esvc/vessel/berthScheduleG")
        print("[S4] berthScheduleG 접속 완료")

        time.sleep(2)

        schedules = []
        detail_divs = driver.find_elements(By.XPATH, "//div[starts-with(@id, 'detail_')]")
        print("[S5] 스케줄 detail 개수:", len(detail_divs))

        for div in detail_divs:
            try:
                div_id = div.get_attribute("id")
                if not div_id:
                    continue

                raw_code = div_id.replace("detail_", "")
                code = clean_ship_code(raw_code)

                text = (
                    div.get_attribute("textContent")
                    or div.get_attribute("innerText")
                    or div.text
                    or ""
                )

                if not text.strip():
                    continue

                vessel_name = extract_detail_value(text, "모선명")
                voyage_text = extract_detail_value(text, "모선항차")
                eta = extract_detail_value(text, "접안예정시간")

                if not eta:
                    continue

                dm = re.search(r"(\d{4})-(\d{2})-(\d{2})", eta)
                tm = re.search(r"(\d{2}):(\d{2})", eta)

                if not dm or not tm:
                    continue

                if voyage_text:
                    m = re.search(r"([A-Z]{3,5}-?\d{3})", voyage_text)
                    if m:
                        code = clean_ship_code(m.group(1))

                ship_text = f"{vessel_name} ({display_code(code)})" if vessel_name else display_ship(code)

                schedules.append({
                    "date": f"{dm.group(2)}/{dm.group(3)}",
                    "time": f"{tm.group(1)}:{tm.group(2)}",
                    "ship": ship_text,
                    "ship_code": display_code(code),
                    "berth": "-",
                    "type": "접안 예정",
                    "qc": ""
                })

            except Exception as e:
                print("스케줄 파싱 오류:", repr(e))
                continue

        schedules = sorted(schedules, key=lambda item: (item["date"], item["time"]))
        print("[S6] 스케줄 파싱 완료:", len(schedules))

        return schedules[:14]

    except Exception as e:
        print("get_berth_schedule 오류:", repr(e))
        return []

    finally:
        print("[S7] 스케줄 드라이버 종료")
        driver.quit()


if __name__ == "__main__":
    result = get_berth_schedule()
    for item in result:
        print(item)