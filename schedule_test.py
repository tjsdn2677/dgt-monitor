from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time

options = Options()
options.add_argument("--start-maximized")

driver = webdriver.Chrome(options=options)

try:
    driver.get("https://info.dgtbusan.com/DGT/esvc/vessel/berthScheduleG")

    time.sleep(5)

    text = driver.find_element(By.TAG_NAME, "body").text

    print("===== berthScheduleG 원본 =====")
    print(text)

finally:
    input("\n엔터 누르면 종료...")
    driver.quit()