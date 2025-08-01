import os
import time
import requests
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def create_driver():
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(options=options)
    driver.maximize_window()
    return driver

def download_image(img_url, folder, title, page, idx):
    if not img_url or not img_url.startswith("http"):
        return ""
    ensure_dir(f"images/{folder}")
    safe_title = "".join(c for c in title if c.isalnum())[:15]
    fname = f"{safe_title}_{page}_{idx}.jpg"
    path = os.path.join("images", folder, fname)
    try:
        resp = requests.get(img_url, timeout=10)
        with open(path, "wb") as f:
            f.write(resp.content)
        return path
    except:
        return ""

def crawl_yes24(keyword, pages):
    driver = create_driver()
    wait = WebDriverWait(driver, 10)
    rows = []

    for p in range(1, pages+1):
        url = f"https://www.yes24.com/Product/Search?domain=BOOK&query={keyword}&page={p}"
        driver.get(url)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#yesSchList li")))
        items = driver.find_elements(By.CSS_SELECTOR, "#yesSchList li")

        for i, itm in enumerate(items, start=1):
            row = {"검색어": keyword}
            # 제목
            try:
                row["책제목"] = itm.find_element(By.CSS_SELECTOR, "a.gd_name").text.strip()
            except:
                row["책제목"] = ""
            # 저자·출판사·출판일
            try:
                auth_pub = itm.find_element(By.CSS_SELECTOR, ".authPub.info_auth").text
                parts = [x.strip() for x in auth_pub.split("|")]
                row["저자"]    = parts[0] if len(parts)>0 else ""
                row["출판사"]  = parts[1] if len(parts)>1 else ""
                row["출판일"]  = parts[2] if len(parts)>2 else ""
            except:
                row.update({"저자":"","출판사":"","출판일":""})
            # 가격
            try:
                row["가격"] = itm.find_element(By.CSS_SELECTOR, ".yes_b").text.strip()
            except:
                row["가격"] = ""
            # 이미지
            try:
                img_url = itm.find_element(By.CSS_SELECTOR, "div.item_img img").get_attribute("src")
                row["이미지"] = download_image(img_url, "yes24", row["책제목"], p, i)
            except:
                row["이미지"] = ""
            rows.append(row)

    driver.quit()
    return rows

def crawl_aladin(keyword, pages):
    driver = create_driver()
    wait = WebDriverWait(driver, 10)
    rows = []

    for p in range(1, pages+1):
        url = f"https://www.aladin.co.kr/search/wsearchresult.aspx?SearchTarget=All&SearchWord={keyword}&page={p}"
        driver.get(url)
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.ss_book_box")))
        items = driver.find_elements(By.CSS_SELECTOR, "div.ss_book_box")

        for i, itm in enumerate(items, start=1):
            row = {"검색어": keyword}
            # 제목
            try:
                row["책제목"] = itm.find_element(By.CSS_SELECTOR, "a.bo3").text.strip()
            except:
                row["책제목"] = ""
            # 저자·출판사·출판일
            try:
                li2 = itm.find_elements(By.CSS_SELECTOR, ".ss_book_list ul li")[1]
                parts = [x.strip() for x in li2.text.split("|")]
                row["저자"]    = parts[0] if len(parts)>0 else ""
                row["출판사"]  = parts[1] if len(parts)>1 else ""
                row["출판일"]  = parts[2] if len(parts)>2 else ""
            except:
                row.update({"저자":"","출판사":"","출판일":""})
            # 가격
            try:
                row["가격"] = itm.find_element(By.CSS_SELECTOR, "span.ss_p2 em").text.strip()
            except:
                row["가격"] = ""
            # 이미지
            try:
                img_url = itm.find_element(By.CSS_SELECTOR, "div.cover_area img").get_attribute("src")
                row["이미지"] = download_image(img_url, "aladin", row["책제목"], p, i)
            except:
                row["이미지"] = ""
            rows.append(row)

    driver.quit()
    return rows

def run_crawl(keyword, yes24_pages, aladin_pages):
    yes24_list = crawl_yes24(keyword, yes24_pages)
    aladin_list = crawl_aladin(keyword, aladin_pages)

    df_yes24  = pd.DataFrame(yes24_list)
    df_aladin = pd.DataFrame(aladin_list)

    # 엑셀로 저장
    ensure_dir("data")
    out = os.path.join("data", f"{keyword}_books.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df_yes24.to_excel(writer, sheet_name="yes24", index=False)
        df_aladin.to_excel(writer, sheet_name="aladin", index=False)

    print(f"크롤링 완료! 결과 파일: {out}")

if __name__ == "__main__":
    run_crawl("프로그래밍", yes24_pages=3, aladin_pages=4)
