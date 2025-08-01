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
        logger.warning(f"이미지 다운로드 실패: {url}")
        return ""

def crawl_yes24(keyword, pages):
    """예스24 크롤러 (메인 페이지 검색창 방식)"""
    if pages <= 0:
        return []
    
    driver = create_driver()
    wait = WebDriverWait(driver, 30)
    data = []
    
    try:
        # 메인 페이지로 이동
        logger.info("예스24 메인 페이지 접속...")
        driver.get("http://www.yes24.com/")
        time.sleep(5)
        
        # 검색창 찾기 및 검색
        try:
            # 정확한 셀렉터로 검색창 찾기
            search_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#query")))
            search_input.clear()
            search_input.send_keys(keyword)
            
            # 정확한 셀렉터로 검색 버튼 클릭
            try:
                search_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit'][title='검색']")
                search_btn.click()
            except:
                # 대체 방법: Enter 키 사용
                search_input.send_keys(Keys.ENTER)
            
            time.sleep(8)
            logger.info("✅ 예스24 검색 완료")
            
        except Exception as e:
            logger.error(f"❌ 예스24 검색 실패: {e}")
            return data
        
        # 페이지별 크롤링
        for page in range(1, pages + 1):
            logger.info(f"예스24 {page}페이지 크롤링 중...")
            
            # 2페이지부터는 페이지 이동
            if page > 1:
                try:
                    # 페이지 번호 클릭
                    page_link = wait.until(EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, f"a[href*='page={page}'], .yesUI_pagenS a:contains('{page}')")
                    ))
                    page_link.click()
                    time.sleep(5)
                    logger.info(f"✅ {page}페이지로 이동")
                except:
                    try:
                        current_url = driver.current_url
                        if "page=" in current_url:
                            new_url = current_url.replace(f"page={page-1}", f"page={page}")
                        else:
                            separator = "&" if "?" in current_url else "?"
                            new_url = current_url + f"{separator}page={page}"
                        
                        driver.get(new_url)
                        time.sleep(5)
                        logger.info(f"✅ URL로 {page}페이지 이동")
                    except:
                        logger.warning(f"❌ {page}페이지 이동 실패")
                        break
            
            # 검색 결과 확인
            page_text = driver.find_element(By.TAG_NAME, "body").text
            if "검색결과가 없습니다" in page_text or "결과가 없습니다" in page_text:
                logger.warning(f"❌ {page}페이지: 검색 결과 없음")
                continue
            
            # 아이템 찾기 (여러 번 시도)
            items = []
            max_attempts = 8
            
            for attempt in range(max_attempts):
                try:
                    logger.info(f"아이템 찾기 시도 {attempt+1}/{max_attempts}")
                    
                    # 다양한 셀렉터 시도
                    selectors_to_try = [
                        "div.itemUnit",
                        "#yesSchList div.itemUnit", 
                        ".goodsList .itemUnit",
                        "[class*='itemUnit']",
                        ".search_list .item",
                        ".goods_list .item",
                        ".prod_item"
                    ]
                    
                    for selector in selectors_to_try:
                        try:
                            if attempt < 3:
                                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                            
                            items = driver.find_elements(By.CSS_SELECTOR, selector)
                            if items:
                                logger.info(f"✅ 아이템 발견: '{selector}' - {len(items)}개")
                                break
                        except:
                            continue
                    
                    if items:
                        break
                    else:
                        logger.warning(f"시도 {attempt+1}: 아이템 없음, 재시도...")
                        time.sleep(3)
                        
                        # 중간에 페이지 새로고침
                        if attempt == 4:
                            logger.info("페이지 새로고침...")
                            driver.refresh()
                            time.sleep(5)
                        
                except Exception as e:
                    logger.warning(f"시도 {attempt+1} 오류: {e}")
                    time.sleep(2)
                    continue
            
            if not items:
                logger.error(f"❌ {page}페이지: {max_attempts}번 시도 후에도 아이템을 찾을 수 없음")
                
                # 디버깅 정보
                logger.info(f"현재 URL: {driver.current_url}")
                logger.info(f"페이지 제목: {driver.title}")
                continue
            
            # 데이터 추출
            logger.info(f"{page}페이지 데이터 추출 - 총 {len(items)}개 아이템")
            
            for idx, item in enumerate(items, start=1):
                # 검색어 확실히 저장
                current_keyword = str(keyword).strip()  # 문자열로 변환하고 공백 제거
                
                row = {
                    "사이트": "예스24",
                    "검색어": current_keyword,  # 확실히 저장
                    "페이지": page,
                    "책제목": "", 
                    "저자": "", 
                    "가격": "", 
                    "출판사": "", 
                    "출판일": "", 
                    "이미지": ""
                }
                
                # 책 제목
                title_selectors = [
                    "a.gd_name",
                    ".gd_name", 
                    "a[class*='name']",
                    ".book_title",
                    "h3 a"
                ]
                
                for sel in title_selectors:
                    try:
                        title_element = item.find_element(By.CSS_SELECTOR, sel)
                        row["책제목"] = title_element.text.strip()
                        break
                    except:
                        continue
                
                # 저자
                author_selectors = [
                    "span.authPub.info_auth a",
                    ".info_auth a",
                    ".author",
                    "[class*='author']"
                ]
                
                for sel in author_selectors:
                    try:
                        author_element = item.find_element(By.CSS_SELECTOR, sel)
                        row["저자"] = author_element.text.strip()
                        break
                    except:
                        continue
                
                # 출판사
                publisher_selectors = [
                    "span.authPub.info_pub a",
                    ".info_pub a",
                    ".publisher",
                    "[class*='publish']"
                ]
                
                for sel in publisher_selectors:
                    try:
                        publisher_element = item.find_element(By.CSS_SELECTOR, sel)
                        row["출판사"] = publisher_element.text.strip()
                        break
                    except:
                        continue
                
                # 출판일
                date_selectors = [
                    "span.authPub.info_date",
                    ".info_date",
                    ".date",
                    "[class*='date']"
                ]
                
                for sel in date_selectors:
                    try:
                        date_element = item.find_element(By.CSS_SELECTOR, sel)
                        row["출판일"] = date_element.text.strip()
                        break
                    except:
                        continue
                
                # 가격
                price_selectors = [
                    "strong.txt_num em.yes_b",
                    ".txt_num em",
                    ".price",
                    "[class*='price']"
                ]
                
                for sel in price_selectors:
                    try:
                        price_element = item.find_element(By.CSS_SELECTOR, sel)
                        row["가격"] = price_element.text.strip()
                        break
                    except:
                        continue
                
                # 이미지
                img_selectors = [
                    "div.item_img img",
                    ".item_img img",
                    ".book_img img",
                    "img"
                ]
                
                for sel in img_selectors:
                    try:
                        img_element = item.find_element(By.CSS_SELECTOR, sel)
                        img_url = img_element.get_attribute("src")
                        if img_url:
                            row["이미지"] = download_image(img_url, "yes24", row["책제목"], page, idx)
                            break
                    except:
                        continue
                
                data.append(row)
            
            logger.info(f"✅ {page}페이지 완료: {len(items)}개 아이템 처리")
            time.sleep(random.uniform(3, 6))
            
    except Exception as e:
        logger.error(f"예스24 크롤링 중 전체 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        driver.quit()
    
    return data

def crawl_kyobo(keyword, pages):
    """교보문고 크롤러 (직접 검색 URL 방식)"""
    if pages <= 0:
        return []
    
    driver = create_driver()
    wait = WebDriverWait(driver, 20)
    data = []
    
    try:
        encoded_keyword = urllib.parse.quote(keyword)
        search_url = f"https://search.kyobobook.co.kr/search?keyword={encoded_keyword}&gbCode=TOT&target=total"
        
        logger.info(f"교보문고 검색 URL 접속...")
        driver.get(search_url)
        time.sleep(5)
        
        for page in range(1, pages + 1):
            logger.info(f"교보문고 {page}페이지 크롤링 중...")
            
            if page > 1:
                # URL 직접 이동
                try:
                    current_url = driver.current_url
                    separator = "&" if "?" in current_url else "?"
                    new_url = current_url + f"{separator}page={page}"
                    driver.get(new_url)
                    time.sleep(3)
                except:
                    logger.warning(f"교보문고 {page}페이지 이동 실패")
                    break
            
            # 아이템 찾기
            items = []
            item_selectors = [
                ".prod_item",
                ".product_list .item", 
                ".search_list .item",
                "[class*='prod'][class*='item']"
            ]
            
            for selector in item_selectors:
                try:
                    items = driver.find_elements(By.CSS_SELECTOR, selector)
                    if items:
                        logger.info(f"✅ 교보문고 {page}페이지: {len(items)}개 아이템 발견")
                        break
                except:
                    continue
            
            if not items:
                logger.warning(f"❌ 교보문고 {page}페이지: 아이템을 찾을 수 없음")
                continue
            
            # 데이터 추출
            for idx, item in enumerate(items, start=1):
                row = {
                    "사이트": "교보문고",
                    "검색어": keyword, 
                    "페이지": page,
                    "책제목": "", 
                    "저자": "", 
                    "가격": "", 
                    "출판사": "", 
                    "출판일": "", 
                    "이미지": ""
                }
                
                title_selectors = [
                    "a.prod_info",             
                    ".prod_info a",               
                    "a[href*='/product/']",     
                    "strong a",                 
                    ".info_title a",            
                    ".prod_name",               
                    ".book_title", 
                    "a[class*='title']",
                    "h3 a",                     
                    ".title a",                 
                    "span[id^='cmdtName_']",
                    ".prod_title",              
                    ".book_name"                
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
                
                # 저자
                for sel in [".author", ".writer", "[class*='author']"]:
                    try:
                        row["저자"] = item.find_element(By.CSS_SELECTOR, sel).text.strip()
                        break
                    except: continue
                
                # 출판사
                for sel in [".publisher", ".prod_publisher", "[class*='publish']"]:
                    try:
                        row["출판사"] = item.find_element(By.CSS_SELECTOR, sel).text.strip()
                        break
                    except: continue
                
                # 출판일
                for sel in [".date", ".publish_date", "[class*='date']"]:
                    try:
                        row["출판일"] = item.find_element(By.CSS_SELECTOR, sel).text.strip()
                        break
                    except: continue
                
                # 가격
                for sel in [".price", ".prod_price", "[class*='price']"]:
                    try:
                        row["가격"] = item.find_element(By.CSS_SELECTOR, sel).text.replace(",", "").strip()
                        break
                    except: continue
                
                # 이미지
                for sel in ["img[class*='prod']", ".prod_img img", "img"]:
                    try:
                        img_element = item.find_element(By.CSS_SELECTOR, sel)
                        img_url = img_element.get_attribute("data-src") or img_element.get_attribute("src")
                        if img_url and img_url.startswith("http"):
                            row["이미지"] = download_image(img_url, "kyobo", row["책제목"], page, idx)
                            break
                    except: continue
                
                data.append(row)
            
            time.sleep(random.uniform(2, 4))
            
    except Exception as e:
        logger.error(f"교보문고 크롤링 오류: {e}")
    finally:
        driver.quit()
    
    return data

def crawl_aladin(keyword, pages):
    """알라딘 크롤러"""
    if pages <= 0:
        return []
    
    driver = create_driver()
    wait = WebDriverWait(driver, 20)
    data = []
    
    try:
        driver.get("https://www.aladin.co.kr/home/welcome.aspx")
        time.sleep(5)
        
        # 검색
        try:
            search_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#SearchWord")))
            search_input.clear()
            search_input.send_keys(keyword)
            
            search_btn = driver.find_element(By.CSS_SELECTOR, "button.search_btn")
            search_btn.click()
            time.sleep(5)
        except:
            logger.error("알라딘 검색 실패")
            return data
        
        for page in range(1, pages + 1):
            logger.info(f"알라딘 {page}페이지 크롤링 중...")
            
            if page > 1:
                # URL 직접 이동
                try:
                    current_url = driver.current_url
                    if "page=" in current_url:
                        new_url = current_url.replace(f"page={page-1}", f"page={page}")
                    else:
                        new_url = current_url + f"&page={page}"
                    driver.get(new_url)
                    time.sleep(3)
                except:
                    logger.warning(f"알라딘 {page}페이지 이동 실패")
                    break
            
            # 아이템 찾기
            try:
                items = driver.find_elements(By.CSS_SELECTOR, "div.ss_book_box")
                if not items:
                    items = driver.find_elements(By.CSS_SELECTOR, ".book_box")
                
                if items:
                    logger.info(f"✅ 알라딘 {page}페이지: {len(items)}개 아이템 발견")
                else:
                    logger.warning(f"❌ 알라딘 {page}페이지: 아이템을 찾을 수 없음")
                    continue
            except:
                logger.warning(f"❌ 알라딘 {page}페이지: 아이템 찾기 실패")
                continue
            
            # 데이터 추출
            for idx, item in enumerate(items, start=1):
                row = {
                    "사이트": "알라딘",
                    "검색어": keyword, 
                    "페이지": page,
                    "책제목": "", 
                    "저자": "", 
                    "가격": "", 
                    "출판사": "", 
                    "출판일": "", 
                    "이미지": ""
                }
                
                # 제목
                try:
                    row["책제목"] = item.find_element(By.CSS_SELECTOR, "a.bo3").text.strip()
                except: pass
                
                # 저자, 출판사, 출판일
                try:
                    info_elements = item.find_elements(By.CSS_SELECTOR, ".ss_book_list ul li")
                    if len(info_elements) > 1:
                        info_text = info_elements[1].text
                        parts = [p.strip() for p in info_text.split("|")]
                        row["저자"] = parts[0] if len(parts) > 0 else ""
                        row["출판사"] = parts[1] if len(parts) > 1 else ""
                        row["출판일"] = parts[2] if len(parts) > 2 else ""
                except: pass
                
                # 가격
                try:
                    row["가격"] = item.find_element(By.CSS_SELECTOR, "span.ss_p2 em").text.strip()
                except: pass
                
                # 이미지
                try:
                    img_url = item.find_element(By.CSS_SELECTOR, "div.cover_area img").get_attribute("src")
                    if img_url:
                        row["이미지"] = download_image(img_url, "aladin", row["책제목"], page, idx)
                except: pass
                
                data.append(row)
            
            time.sleep(random.uniform(2, 4))
            
    except Exception as e:
        logger.error(f"알라딘 크롤링 오류: {e}")
    finally:
        driver.quit()
    
    return data

def crawl_all_sites(keyword, yes24_pages=3, kyobo_pages=3, aladin_pages=3):
    """모든 사이트 통합 크롤링"""
    logger.info(f"통합 크롤링 시작: '{keyword}'")
    logger.info(f"계획: 예스24({yes24_pages}페이지), 교보문고({kyobo_pages}페이지), 알라딘({aladin_pages}페이지)")
    
    all_data = []
    
    # 예스24
    if yes24_pages > 0:
        logger.info("=" * 50)
        logger.info("예스24 크롤링 시작")
        logger.info("=" * 50)
        yes24_data = crawl_yes24(keyword, yes24_pages)
        all_data.extend(yes24_data)
        logger.info(f"✅ 예스24 완료: {len(yes24_data)}개 데이터 수집")
    
    # 교보문고
    if kyobo_pages > 0:
        logger.info("=" * 50)
        logger.info("교보문고 크롤링 시작")
        logger.info("=" * 50)
        kyobo_data = crawl_kyobo(keyword, kyobo_pages)
        all_data.extend(kyobo_data)
        logger.info(f"✅ 교보문고 완료: {len(kyobo_data)}개 데이터 수집")
    
    # 알라딘
    if aladin_pages > 0:
        logger.info("=" * 50)
        logger.info("알라딘 크롤링 시작")
        logger.info("=" * 50)
        aladin_data = crawl_aladin(keyword, aladin_pages)
        all_data.extend(aladin_data)
        logger.info(f"✅ 알라딘 완료: {len(aladin_data)}개 데이터 수집")
    
    # 결과 저장
    if all_data:
        logger.info("=" * 50)
        logger.info("결과 저장 중...")
        logger.info("=" * 50)
        
        df = pd.DataFrame(all_data)
        
        # crawl.xlsx로 저장
        ensure_dir("data")
        output_path = os.path.join("data", "crawl.xlsx")
        
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            
            df.to_excel(writer, sheet_name="전체", index=False)
            
            for site in ["예스24", "교보문고", "알라딘"]:
                site_data = df[df["사이트"] == site]
                if not site_data.empty:
                    site_data.to_excel(writer, sheet_name=site, index=False)
        
        # 통계 출력
        logger.info("크롤링 완료!")
        logger.info(f"총 수집 데이터: {len(all_data)}개")
        
        site_stats = df["사이트"].value_counts()
        for site, count in site_stats.items():
            logger.info(f"   {site}: {count}개")
        
        # 데이터 분석
        logger.info("데이터 품질 분석:")
        total = len(all_data)
        with_title = sum(1 for item in all_data if item['책제목'])
        with_author = sum(1 for item in all_data if item['저자'])
        with_publisher = sum(1 for item in all_data if item['출판사'])
        with_date = sum(1 for item in all_data if item['출판일'])
        with_price = sum(1 for item in all_data if item['가격'])
        with_image = sum(1 for item in all_data if item['이미지'])
        
        logger.info(f"   제목: {with_title}/{total} ({with_title/total*100:.1f}%)")
        logger.info(f"   저자: {with_author}/{total} ({with_author/total*100:.1f}%)")
        logger.info(f"   출판사: {with_publisher}/{total} ({with_publisher/total*100:.1f}%)")
        logger.info(f"   출판일: {with_date}/{total} ({with_date/total*100:.1f}%)")
        logger.info(f"   가격: {with_price}/{total} ({with_price/total*100:.1f}%)")
        logger.info(f"   이미지: {with_image}/{total} ({with_image/total*100:.1f}%)")
        
        logger.info(f"결과 파일: {output_path}")
        
        logger.info("샘플 데이터:")
        for i, item in enumerate(all_data[:3], 1):
            logger.info(f"   {i}. [{item['사이트']}] {item['책제목']} - {item['저자']} ({item['가격']})")
        
    else:
        logger.warning("수집된 데이터가 없습니다.")

if __name__ == "__main__":
    crawl_all_sites(
        keyword="파이썬",     
        yes24_pages=3,         
        kyobo_pages=5,         
        aladin_pages=4         
    )
