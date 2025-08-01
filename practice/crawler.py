import os
import time
import random
import requests
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def create_driver():
    options = webdriver.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        '''
    })
    driver.maximize_window()
    return driver

def download_image(url, folder, title, page, idx):
    """이미지 다운로드"""
    if not url or not url.startswith("http"):
        return ""
    
    ensure_dir(f"images/{folder}")
    safe_title = "".join(c for c in title if c.isalnum() or c in [' ', '-', '_'])[:15]
    if not safe_title:
        safe_title = "untitled"
    filename = f"{safe_title}_{page}_{idx}.jpg"
    path = os.path.join("images", folder, filename)
    
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()
        
        with open(path, "wb") as f:
            f.write(resp.content)
        logger.debug(f"이미지 다운로드 성공: {path}")
        return path
    except Exception as e:
        logger.warning(f"이미지 다운로드 실패: {url}, 오류: {e}")
        return ""

def crawl_yes24_fixed(keyword, pages):
    """1페이지 문제를 해결한 예스24 크롤러"""
    if pages <= 0:
        return []
    
    driver = create_driver()
    wait = WebDriverWait(driver, 25)  # 대기 시간 더 증가
    data = []
    
    try:
        for page in range(1, pages + 1):
            logger.info(f"예스24 {page}페이지 크롤링 중...")
            
            # 1페이지와 다른 페이지 URL 다르게 처리
            if page == 1:
                # 1페이지는 page 파라미터 없이 접속
                url = f"http://www.yes24.com/Product/Search?domain=BOOK&query={keyword}"
                logger.info(f"1페이지 특별 처리 URL: {url}")
            else:
                # 2페이지부터는 page 파라미터 포함
                url = f"http://www.yes24.com/Product/Search?domain=BOOK&query={keyword}&page={page}"
                logger.info(f"{page}페이지 일반 URL: {url}")
            
            driver.get(url)
            
            # 1페이지는 더 오래 기다리기
            if page == 1:
                logger.info("1페이지 로딩 - 추가 대기 시간 적용")
                time.sleep(8)  # 1페이지는 8초 대기
            else:
                time.sleep(5)  # 다른 페이지는 5초 대기
            
            # 페이지 로딩 확인
            try:
                # 페이지가 완전히 로드될 때까지 기다리기
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                
                # 검색 결과가 있는지 확인
                page_text = driver.find_element(By.TAG_NAME, "body").text
                if "검색결과가 없습니다" in page_text or "결과가 없습니다" in page_text:
                    logger.warning(f"{page}페이지에 검색 결과가 없습니다.")
                    continue
                    
                logger.info(f"{page}페이지 로딩 완료 확인")
                
            except Exception as e:
                logger.warning(f"{page}페이지 로딩 확인 중 오류: {e}")
            
            # 여러 번 시도해서 아이템 찾기
            items = []
            max_attempts = 5  # 시도 횟수 증가
            
            for attempt in range(max_attempts):
                try:
                    logger.info(f"{page}페이지 아이템 찾기 시도 {attempt+1}/{max_attempts}")
                    
                    # 다양한 방법으로 요소 대기
                    if attempt == 0:
                        # 첫 번째 시도: itemUnit 직접 대기
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.itemUnit")))
                    elif attempt == 1:
                        # 두 번째 시도: 검색 결과 영역 대기
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#yesSchList")))
                    elif attempt == 2:
                        # 세 번째 시도: 상품 목록 영역 대기
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".goodsList")))
                    else:
                        # 나머지 시도: 단순 대기
                        time.sleep(3)
                    
                    # 아이템 찾기
                    items = driver.find_elements(By.CSS_SELECTOR, "div.itemUnit")
                    
                    if items:
                        logger.info(f"✅ {page}페이지 시도 {attempt+1}: {len(items)}개 아이템 발견")
                        break
                    else:
                        logger.warning(f"❌ {page}페이지 시도 {attempt+1}: 아이템이 없음")
                        
                        # 페이지 소스 일부 확인 (디버깅용)
                        if attempt == 2:
                            page_source_sample = driver.page_source[:500]
                            logger.debug(f"페이지 소스 샘플: {page_source_sample}")
                        
                        time.sleep(2)
                        
                except TimeoutException:
                    logger.warning(f"❌ {page}페이지 시도 {attempt+1}: 타임아웃")
                    time.sleep(2)
                    continue
                except Exception as e:
                    logger.warning(f"❌ {page}페이지 시도 {attempt+1}: 오류 - {e}")
                    time.sleep(2)
                    continue
            
            if not items:
                logger.error(f"❌ {page}페이지에서 {max_attempts}번 시도 후에도 책 목록을 찾을 수 없습니다.")
                
                # 현재 페이지 정보 출력 (디버깅용)
                logger.info(f"현재 URL: {driver.current_url}")
                logger.info(f"페이지 제목: {driver.title}")
                
                # 1페이지에서 실패하면 다른 방법 시도
                if page == 1:
                    logger.info("1페이지 대안 방법 시도...")
                    try:
                        # 검색 페이지로 직접 이동해서 검색하기
                        driver.get("http://www.yes24.com/")
                        time.sleep(3)
                        
                        # 검색창 찾기
                        search_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='query']")))
                        search_input.clear()
                        search_input.send_keys(keyword)
                        search_input.send_keys(Keys.ENTER)
                        time.sleep(5)
                        
                        # 다시 아이템 찾기
                        items = driver.find_elements(By.CSS_SELECTOR, "div.itemUnit")
                        if items:
                            logger.info(f"✅ 1페이지 대안 방법 성공: {len(items)}개 아이템 발견")
                        else:
                            logger.error("❌ 1페이지 대안 방법도 실패")
                            continue
                            
                    except Exception as e:
                        logger.error(f"1페이지 대안 방법 오류: {e}")
                        continue
                else:
                    continue
            
            # 데이터 추출
            logger.info(f"{page}페이지 데이터 추출 시작 - 총 {len(items)}개 아이템")
            
            for idx, item in enumerate(items, start=1):
                row = {
                    "검색어": keyword, 
                    "책제목": "", 
                    "저자": "", 
                    "가격": "", 
                    "출판사": "", 
                    "출판일": "", 
                    "이미지": ""
                }
                
                # 책 제목: a.gd_name
                try:
                    title_element = item.find_element(By.CSS_SELECTOR, "a.gd_name")
                    row["책제목"] = title_element.text.strip()
                except:
                    pass
                
                # 저자: span.authPub.info_auth a
                try:
                    author_element = item.find_element(By.CSS_SELECTOR, "span.authPub.info_auth a")
                    row["저자"] = author_element.text.strip()
                except:
                    pass
                
                # 출판사: span.authPub.info_pub a
                try:
                    publisher_element = item.find_element(By.CSS_SELECTOR, "span.authPub.info_pub a")
                    row["출판사"] = publisher_element.text.strip()
                except:
                    pass
                
                # 출판일: span.authPub.info_date
                try:
                    date_element = item.find_element(By.CSS_SELECTOR, "span.authPub.info_date")
                    row["출판일"] = date_element.text.strip()
                except:
                    pass
                
                # 가격: strong.txt_num em.yes_b
                try:
                    price_element = item.find_element(By.CSS_SELECTOR, "strong.txt_num em.yes_b")
                    row["가격"] = price_element.text.strip()
                except:
                    pass
                
                # 이미지: div.item_img img
                try:
                    img_element = item.find_element(By.CSS_SELECTOR, "div.item_img img")
                    img_url = img_element.get_attribute("src")
                    if img_url:
                        row["이미지"] = download_image(img_url, "yes24", row["책제목"], page, idx)
                except:
                    pass
                
                data.append(row)
            
            logger.info(f"✅ {page}페이지 완료: {len(items)}개 아이템 처리")
            
            # 페이지 간 대기
            time.sleep(random.uniform(3, 5))
            
    except Exception as e:
        logger.error(f"예스24 크롤링 중 전체 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        driver.quit()
    
    return data

def test_yes24_pages(keyword, pages):
    """예스24 페이지별 테스트"""
    logger.info(f"=== 예스24 페이지별 테스트 시작: '{keyword}' ===")
    
    results = crawl_yes24_fixed(keyword, pages)
    
    if results:
        logger.info("=== 크롤링 결과 분석 ===")
        total_items = len(results)
        items_with_title = sum(1 for item in results if item['책제목'])
        items_with_author = sum(1 for item in results if item['저자'])
        items_with_publisher = sum(1 for item in results if item['출판사'])
        items_with_date = sum(1 for item in results if item['출판일'])
        items_with_price = sum(1 for item in results if item['가격'])
        items_with_image = sum(1 for item in results if item['이미지'])
        
        logger.info(f"총 아이템: {total_items}")
        logger.info(f"제목: {items_with_title}/{total_items} ({items_with_title/total_items*100:.1f}%)")
        logger.info(f"저자: {items_with_author}/{total_items} ({items_with_author/total_items*100:.1f}%)")
        logger.info(f"출판사: {items_with_publisher}/{total_items} ({items_with_publisher/total_items*100:.1f}%)")
        logger.info(f"출판일: {items_with_date}/{total_items} ({items_with_date/total_items*100:.1f}%)")
        logger.info(f"가격: {items_with_price}/{total_items} ({items_with_price/total_items*100:.1f}%)")
        logger.info(f"이미지: {items_with_image}/{total_items} ({items_with_image/total_items*100:.1f}%)")
        
        # 엑셀 저장
        ensure_dir("data")
        path = os.path.join("data", f"{keyword}_yes24_fixed.xlsx")
        
        df = pd.DataFrame(results)
        df.to_excel(path, index=False)
        
        logger.info(f"✅ 결과 저장 완료: {path}")
        
        # 샘플 데이터 출력
        logger.info("=== 샘플 데이터 (처음 3개) ===")
        for i, item in enumerate(results[:3], 1):
            logger.info(f"아이템 {i}:")
            logger.info(f"  제목: {item['책제목']}")
            logger.info(f"  저자: {item['저자']}")
            logger.info(f"  출판사: {item['출판사']}")
            logger.info(f"  가격: {item['가격']}")
    else:
        logger.warning("수집된 데이터가 없습니다.")

if __name__ == "__main__":
    # 예스24 1페이지 문제 해결 테스트
    test_yes24_pages("파이썬", 3)
