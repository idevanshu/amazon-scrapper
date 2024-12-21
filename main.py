import time
import csv
import logging
import random
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


# Initialize logging
logging.basicConfig(
    filename='amazon_scraper.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6)",
]

category_urls = {
    "kitchen": "https://www.amazon.in/gp/bestsellers/kitchen/ref=zg_bs_nav_kitchen_0",
    "shoes": "https://www.amazon.in/gp/bestsellers/shoes/ref=zg_bs_nav_shoes_0",
    "computers": "https://www.amazon.in/gp/bestsellers/computers/ref=zg_bs_nav_computers_0",
    "electronics": "https://www.amazon.in/gp/bestsellers/electronics/ref=zg_bs_nav_electronics_0"
}


def get_webdriver():
    user_agent = random.choice(USER_AGENTS)
    chrome_options = Options()
    chrome_options.add_argument("--incognito")
    chrome_options.add_argument(f"user-agent={user_agent}")
    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver


def wait_for_element(driver, by, selector, timeout=10):
    """Wait for a specific element to appear and return it, or None if not found."""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )
        return element
    except:
        return None


def login_amazon(driver, email, password):
    # Go to Amazon home page
    driver.get("https://www.amazon.in/")

    # Click on the account list link to go to login page
    account_link = wait_for_element(driver, By.ID, "nav-link-accountList", timeout=20)
    if account_link:
        account_link.click()
    else:
        logging.error("Account link not found on homepage.")
        return

    # Enter email
    email_field = wait_for_element(driver, By.ID, "ap_email", timeout=20)
    if email_field:
        email_field.send_keys(email)
    else:
        logging.error("Email field not found.")
        return

    continue_button = wait_for_element(driver, By.ID, "continue", timeout=20)
    if continue_button:
        continue_button.click()
    else:
        logging.error("Continue button not found after entering email.")
        return

    # Enter password
    password_field = wait_for_element(driver, By.ID, "ap_password", timeout=20)
    if password_field:
        password_field.send_keys(password)
    else:
        logging.error("Password field not found.")
        return

    sign_in_button = wait_for_element(driver, By.ID, "signInSubmit", timeout=20)
    if sign_in_button:
        sign_in_button.click()
    else:
        logging.error("Sign-in button not found after entering password.")
        return

    # If OTP is required, give time to the user to complete it
    # Wait for 2 minutes to allow user to enter OTP and complete sign-in
    logging.info("Waiting 2 minutes for OTP entry. Please complete OTP verification in the opened browser.")
    time.sleep(120)  # Wait 2 mins for manual OTP entry


def parse_product_details(soup, category_name, driver):
    # Product Name
    title_el = soup.select_one("#productTitle")
    product_name = title_el.get_text(strip=True) if title_el else "N/A"

    # Price
    price_el = soup.select_one("#corePrice_feature_div .a-offscreen, #apex_desktop .a-offscreen")
    product_price = price_el.get_text(strip=True) if price_el else "N/A"

    # Rating (detailed rating)
    rating_el = soup.select_one("span[data-hook='rating-out-of-text']")
    rating = rating_el.get_text(strip=True) if rating_el else "N/A"

    # Best Seller Rating
    best_seller_rating = "N/A"
    detail_wrapper = soup.select_one("#detailBulletsWrapper_feature_div")
    if detail_wrapper:
        detail_text = detail_wrapper.get_text(" ", strip=True)
        if "Best Sellers Rank" in detail_text:
            for line in detail_text.split("\n"):
                if "Best Sellers Rank" in line:
                    best_seller_rating = line.strip()
                    break

    # Ship From and Sold By
    ship_from = "N/A"
    sold_by = "N/A"

    # Try tabular buybox first
    tabular_box = soup.select_one("#tabular-buybox")
    if tabular_box:
        tb_text = tabular_box.get_text(" ", strip=True)
        if "Ships from" in tb_text:
            idx = tb_text.find("Ships from")
            line = tb_text[idx:].split(" ")[2:]  # after 'Ships from'
            ship_from_candidate = " ".join(line).strip()
            if ship_from_candidate:
                ship_from = ship_from_candidate.split("Sold")[0].strip()

        if "Sold by" in tb_text:
            idx = tb_text.find("Sold by")
            line = tb_text[idx:].split(" ")[2:]  # after 'Sold by'
            sold_by_candidate = " ".join(line).strip()
            sold_by_candidate = sold_by_candidate.replace("Fulfilled by Amazon", "").strip()
            if sold_by_candidate:
                sold_by = sold_by_candidate
    else:
        merchant_info = soup.select_one("#merchant-info")
        if merchant_info:
            m_text = merchant_info.get_text(" ", strip=True)
            if "Sold by" in m_text:
                parts = m_text.split("Sold by")
                if len(parts) > 1:
                    sold_part = parts[1].strip()
                    sold_part = sold_part.replace("Fulfilled by Amazon", "").strip()
                    if sold_part:
                        sold_by = sold_part
            if "Ships from" in m_text:
                if "Amazon" in m_text:
                    ship_from = "Amazon"

    # Product Description
    product_description = "N/A"
    feature_bullets = soup.select_one("#feature-bullets")
    if feature_bullets:
        bullets = feature_bullets.select("li")
        bullet_points = [b.get_text(strip=True) for b in bullets if b.get_text(strip=True)]
        if bullet_points:
            product_description = "\n".join(bullet_points)
    else:
        desc_fallback = soup.select_one("#productDescription")
        if desc_fallback:
            desc_text = desc_fallback.get_text(" ", strip=True)
            if desc_text:
                product_description = desc_text

    # Number Bought in the Past Month (Not always present)
    number_bought = "N/A"
    page_source = driver.page_source
    if "bought in past month" in page_source:
        for line in page_source.split("\n"):
            if "bought in past month" in line:
                number_bought_val = line.strip()
                number_bought = number_bought_val if number_bought_val else "N/A"
                break

    image_elements = soup.select("#imageBlockContainer img")
    image_urls = []
    for img in image_elements:
        src = img.get("src")
        if src and "data:image" not in src:
            image_urls.append(src)

    images_multiline = "\n".join(list(set(image_urls))) if image_urls else "N/A"

    return {
        "Category Name": category_name,
        "Product Name": product_name,
        "Product Price": product_price,
        "Best Seller Rating": best_seller_rating,
        "Ship From": ship_from,
        "Sold By": sold_by,
        "Rating": rating,
        "Product Description": product_description,
        "Number Bought in the Past Month": number_bought,
        "All Available Images": images_multiline
    }


def get_product_details(driver, product_url, category_name, retries=2):
    """Scrape detailed information from product detail page with retry logic."""
    for attempt in range(retries):
        try:
            driver.get(product_url)
            element = wait_for_element(driver, By.ID, "productTitle", timeout=10)
            if not element:
                logging.warning(f"Product title not found at {product_url}, attempt {attempt+1}")
                time.sleep(2)
                continue  # Retry

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            details = parse_product_details(soup, category_name, driver)
            return details
        except Exception as e:
            logging.error(f"Error getting product details for {product_url}: {e}", exc_info=True)
            time.sleep(2)
    return {
        "Category Name": category_name,
        "Product Name": "N/A",
        "Product Price": "N/A",
        "Best Seller Rating": "N/A",
        "Ship From": "N/A",
        "Sold By": "N/A",
        "Rating": "N/A",
        "Product Description": "N/A",
        "Number Bought in the Past Month": "N/A",
        "All Available Images": "N/A"
    }


def get_category_products(driver, category_name, category_url, limit=10):
    """Get product URLs from a category page."""
    logging.info(f"Scraping category: {category_name}")
    products_data = []
    try:
        driver.get(category_url)
        # Wait for products to appear
        product_element = wait_for_element(driver, By.CSS_SELECTOR, "div.zg-grid-general-faceout")
        if not product_element:
            logging.warning(f"No products found on category page: {category_url}")
            return products_data

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        products = soup.select("div.zg-grid-general-faceout")[:limit]

        for prod in products:
            link_el = prod.select_one("a.a-link-normal")
            if not link_el:
                continue
            product_url = "https://www.amazon.in" + link_el.get("href")
            product_details = get_product_details(driver, product_url, category_name)
            products_data.append(product_details)
            # Random sleep to reduce suspicion
            time.sleep(random.uniform(2, 4))

    except Exception as e:
        logging.error(f"Error scraping category {category_name}: {e}", exc_info=True)

    return products_data


def main():
    """
    email = os.environ.get("AMAZON_EMAIL", "your_email@example.com")
    password = os.environ.get("AMAZON_PASSWORD", "your_password")
    """
    email = "your_email"
    password = "your_password"
    driver = get_webdriver()
    all_data = []

    try:
        # Login before scraping
        login_amazon(driver, email, password)

        for category_name, category_url in category_urls.items():
            category_data = get_category_products(driver, category_name, category_url, limit=10)
            all_data.extend(category_data)
    finally:
        driver.quit()

    logging.info("Scraping completed.")

    fieldnames = [
        "Category Name",
        "Product Name",
        "Product Price",
        "Best Seller Rating",
        "Ship From",
        "Sold By",
        "Rating",
        "Product Description",
        "Number Bought in the Past Month",
        "All Available Images"
    ]

    with open("amazon_bestsellers_data.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for item in all_data:
            writer.writerow(item)

    logging.info("Data saved to amazon_bestsellers_data.csv")


if __name__ == "__main__":
    main()
