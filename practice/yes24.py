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
import urllib.parse

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

def crawl_kyobo_fixed(keyword, pages):
    """실제 HTML 구조 기반 교보문고 크롤러"""
    if pages <= 0:
        return []
    
    driver = create_driver()
    wait = WebDriverWait(driver, 20)
    data = []
    
    try:
        # 방법 1: 직접 검색 결과 URL로 이동 (가장 안전)
        encoded_keyword = urllib.parse.quote(keyword)
        search_url = f"https://search.kyobobook.co.kr/search?keyword={encoded_keyword}&gbCode=TOT&target=total"
        
        logger.info(f"교보문고 직접 검색 URL 접속: {search_url}")
        driver.get(search_url)
        time.sleep(5)
        
        # 검색 결과가 로드되었는지 확인
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            page_text = driver.find_element(By.TAG_NAME, "body").text
            
            if "검색결과가 없습니다" in page_text or "결과가 없습니다" in page_text:
                logger.warning("교보문고에서 검색 결과가 없습니다.")
                return data
            
            logger.info("✅ 교보문고 검색 결과 페이지 로딩 완료")
            
        except Exception as e:
            logger.warning(f"교보문고 페이지 로딩 확인 중 오류: {e}")
            
            # 방법 2: 메인 페이지에서 검색창 이용
            logger.info("대안 방법: 메인 페이지에서 검색창 이용")
            try:
                driver.get("http://www.kyobobook.co.kr/")
                time.sleep(3)
                
                # 검색창 찾기 - 실제 구조 기반
                search_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input#searchKeyword")))
                logger.info("✅ 교보문고 검색창 발견: input#searchKeyword")
                
                search_input.clear()
                search_input.send_keys(keyword)
                search_input.send_keys(Keys.ENTER)  # Enter 키로 검색
                time.sleep(5)
                
            except Exception as e2:
                logger.error(f"교보문고 대안 방법도 실패: {e2}")
                return data
        
        # 페이지별 크롤링
        for page in range(1, pages + 1):
            logger.info(f"교보문고 {page}페이지 크롤링 중...")
            
            if page > 1:
                # 페이지 이동 - 여러 방법 시도
                page_moved = False
                
                # 방법 1: 직접 URL 이동
                try:
                    current_url = driver.current_url
                    if "page=" in current_url:
                        new_url = current_url.replace(f"page={page-1}", f"page={page}")
                    else:
                        separator = "&" if "?" in current_url else "?"
                        new_url = current_url + f"{separator}page={page}"
                    
                    driver.get(new_url)
                    time.sleep(3)
                    page_moved = True
                    logger.info(f"✅ URL 직접 이동으로 {page}페이지 이동 성공")
                    
                except Exception as e:
                    logger.warning(f"URL 직접 이동 실패: {e}")
                
                # 방법 2: 페이지 링크 클릭
                if not page_moved:
                    page_selectors = [
                        f"a[href*='page={page}']",
                        f".pagination a:contains('{page}')",
                        f".paging a[href*='page={page}']"
                    ]
                    
                    for selector in page_selectors:
                        try:
                            nav = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
                            nav.click()
                            time.sleep(3)
                            page_moved = True
                            logger.info(f"✅ 링크 클릭으로 {page}페이지 이동 성공")
                            break
                        except:
                            continue
                
                if not page_moved:
                    logger.warning(f"교보문고 {page}페이지로 이동할 수 없습니다.")
                    break
            
            # 상품 목록 찾기 - 다양한 셀렉터 시도
            items = []
            item_selectors = [
                ".prod_item",                    # 상품 아이템
                ".product_list .item",           # 상품 목록의 아이템
                ".search_list .item",            # 검색 목록의 아이템
                "[class*='prod'][class*='item']", # prod와 item이 포함된 클래스
                ".list_search_result li",        # 검색 결과 리스트
                ".search_result .product",       # 검색 결과의 상품
            ]
            
            for selector in item_selectors:
                try:
                    items = driver.find_elements(By.CSS_SELECTOR, selector)
                    if items:
                        logger.info(f"✅ 교보문고 아이템 발견: '{selector}' - {len(items)}개")
                        break
                except:
                    continue
            
            if not items:
                logger.warning(f"교보문고 {page}페이지에서 아이템을 찾을 수 없습니다.")
                
                # 디버깅: 페이지 구조 확인
                logger.info("페이지 구조 분석 중...")
                try:
                    all_elements = driver.find_elements(By.CSS_SELECTOR, "[class*='prod'], [class*='item'], [class*='book']")
                    logger.info(f"prod/item/book 관련 요소 {len(all_elements)}개 발견")
                    
                    for i, elem in enumerate(all_elements[:5]):  # 처음 5개만
                        class_name = elem.get_attribute("class")
                        tag_name = elem.tag_name
                        logger.info(f"  요소 {i+1}: <{tag_name} class='{class_name}'>")
                        
                except Exception as e:
                    logger.warning(f"페이지 구조 분석 실패: {e}")
                
                continue
            
            # 데이터 추출
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
                
                # 제목 추출 - 다양한 셀렉터 시도
                title_selectors = [
                    ".prod_name",                # 상품명
                    ".book_title",               # 책 제목
                    "a[class*='title']",         # 제목 링크
                    ".title",                    # 일반 제목
                    "h3 a",                      # h3 안의 링크
                    "a[href*='/product/']",      # 상품 페이지 링크
                ]
                
                for sel in title_selectors:
                    try:
                        title_element = item.find_element(By.CSS_SELECTOR, sel)
                        title_text = title_element.text.strip()
                        if title_text:
                            row["책제목"] = title_text
                            break
                    except:
                        continue
                
                # 저자 추출
                author_selectors = [
                    ".author",                   # 저자
                    ".writer",                   # 작가
                    "[class*='author']",         # author가 포함된 클래스
                    ".prod_author",              # 상품 저자
                ]
                
                for sel in author_selectors:
                    try:
                        author_element = item.find_element(By.CSS_SELECTOR, sel)
                        author_text = author_element.text.strip()
                        if author_text:
                            row["저자"] = author_text
                            break
                    except:
                        continue
                
                # 출판사 추출
                publisher_selectors = [
                    ".publisher",                # 출판사
                    ".prod_publisher",           # 상품 출판사
                    "[class*='publish']",        # publish가 포함된 클래스
                    ".company",                  # 회사
                ]
                
                for sel in publisher_selectors:
                    try:
                        publisher_element = item.find_element(By.CSS_SELECTOR, sel)
                        publisher_text = publisher_element.text.strip()
                        if publisher_text:
                            row["출판사"] = publisher_text
                            break
                    except:
                        continue
                
                # 출판일 추출
                date_selectors = [
                    ".date",                     # 날짜
                    ".publish_date",             # 출판일
                    "[class*='date']",           # date가 포함된 클래스
                    ".prod_date",                # 상품 날짜
                ]
                
                for sel in date_selectors:
                    try:
                        date_element = item.find_element(By.CSS_SELECTOR, sel)
                        date_text = date_element.text.strip()
                        if date_text:
                            row["출판일"] = date_text
                            break
                    except:
                        continue
                
                # 가격 추출
                price_selectors = [
                    ".price",                    # 가격
                    ".prod_price",               # 상품 가격
                    "[class*='price']",          # price가 포함된 클래스
                    ".cost",                     # 비용
                    "em[class*='price']",        # price가 포함된 em
                ]
                
                for sel in price_selectors:
                    try:
                        price_element = item.find_element(By.CSS_SELECTOR, sel)
                        price_text = price_element.text.replace(",", "").strip()
                        if price_text:
                            row["가격"] = price_text
                            break
                    except:
                        continue
                
                # 이미지 추출
                img_selectors = [
                    "img[class*='prod']",        # prod가 포함된 이미지
                    ".prod_img img",             # 상품 이미지
                    ".book_img img",             # 책 이미지
                    "img[alt*='표지']",          # 표지 이미지
                    "img",                       # 모든 이미지
                ]
                
                for sel in img_selectors:
                    try:
                        img_element = item.find_element(By.CSS_SELECTOR, sel)
                        img_url = img_element.get_attribute("data-src") or img_element.get_attribute("src")
                        if img_url and img_url.startswith("http"):
                            row["이미지"] = download_image(img_url, "kyobo", row["책제목"], page, idx)
                            break
                    except:
                        continue
                
                data.append(row)
            
            logger.info(f"✅ 교보문고 {page}페이지 완료: {len(items)}개 아이템 처리")
            time.sleep(random.uniform(2, 4))
            
    except Exception as e:
        logger.error(f"교보문고 크롤링 중 전체 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        driver.quit()
    
    return data

def test_kyobo(keyword, pages):
    """교보문고 테스트"""
    logger.info(f"=== 교보문고 테스트 시작: '{keyword}' ===")
    
    results = crawl_kyobo_fixed(keyword, pages)
    
    if results:
        logger.info("=== 교보문고 크롤링 결과 분석 ===")
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
        path = os.path.join("data", f"{keyword}_kyobo_fixed.xlsx")
        
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
        logger.warning("교보문고에서 수집된 데이터가 없습니다.")

if __name__ == "__main__":
    # 교보문고 테스트
    test_kyobo("파이썬", 2)
