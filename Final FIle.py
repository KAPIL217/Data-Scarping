import pandas as pd
import time
import re
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import logging
from datetime import datetime

class FlipkartScraper:
    def __init__(self):
        self.setup_driver()
        self.setup_logging()
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_driver(self):
        """Setup Chrome driver with appropriate options"""
        chrome_options = Options()
        # chrome_options.add_argument("--headless")  # Remove for debugging
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    def find_average_rating(self):
        """Find average rating using multiple strategies"""
        try:
            # Strategy 1: Look for the main average rating element
            avg_selectors = [
                "//div[contains(@class, '_3LWZlK')]",  # Main rating class
                "//div[contains(@class, '_2d4LTz')]",  # Alternative rating class
                "//span[contains(@class, '_2_R_DZ')]/preceding-sibling::div",  # Before ratings text
                "//div[contains(text(), 'Ratings')]/preceding-sibling::div",  # Before "Ratings"
                "//div[contains(@class, 'XQDdHH')]",  # Another possible rating class
                "//span[contains(@class, '_1lRcqv')]",  # Yet another rating class
            ]
            
            for selector in avg_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text.strip()
                        # Look for patterns like "4.2", "3.7", etc.
                        if text and re.match(r'^\d+\.\d+$', text):
                            self.logger.info(f"Found average rating with selector '{selector}': {text}")
                            return float(text)
                except Exception as e:
                    continue
            
            # Strategy 2: Look in the ratings header section
            try:
                rating_headers = self.driver.find_elements(By.XPATH, "//div[contains(@class, '_3uSWxT')] | //div[contains(@class, '_2pgHN-')] | //div[contains(@class, 'gUuXy-')]")
                for header in rating_headers:
                    text = header.text
                    # Look for rating pattern in header text
                    rating_match = re.search(r'(\d+\.\d+)', text)
                    if rating_match:
                        self.logger.info(f"Found average rating in header: {rating_match.group(1)}")
                        return float(rating_match.group(1))
            except:
                pass
            
            # Strategy 3: Look near the ratings count text
            try:
                # Find the ratings count element and look for rating nearby
                ratings_elements = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'ratings')]")
                for ratings_element in ratings_elements:
                    # Look at parent element and siblings
                    parent = ratings_element.find_element(By.XPATH, "./..")
                    parent_text = parent.text
                    rating_match = re.search(r'(\d+\.\d+)', parent_text)
                    if rating_match:
                        self.logger.info(f"Found average rating near ratings text: {rating_match.group(1)}")
                        return float(rating_match.group(1))
                    
                    # Look at previous sibling
                    try:
                        previous_sibling = ratings_element.find_element(By.XPATH, "./preceding-sibling::div[1]")
                        sibling_text = previous_sibling.text
                        if sibling_text and re.match(r'^\d+\.\d+$', sibling_text):
                            self.logger.info(f"Found average rating in previous sibling: {sibling_text}")
                            return float(sibling_text)
                    except:
                        pass
            except:
                pass
            
            self.logger.warning("Could not find average rating")
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding average rating: {e}")
            return None
    
    def extract_rating_counts(self, rating_text):
        """Extract ratings count and reviews count from text"""
        try:
            self.logger.info(f"Extracting counts from: {rating_text}")
            
            # Pattern for "12,579 ratings and 743 reviews"
            pattern = r'([\d,]+)\s+ratings?\s+and\s+([\d,]+)\s+reviews?'
            match = re.search(pattern, rating_text, re.IGNORECASE)
            
            if match:
                ratings_count = int(match.group(1).replace(',', ''))
                reviews_count = int(match.group(2).replace(',', ''))
                return ratings_count, reviews_count
            
            # Alternative pattern if "and" is missing
            alt_pattern = r'([\d,]+)\s+ratings?\s+([\d,]+)\s+reviews?'
            alt_match = re.search(alt_pattern, rating_text, re.IGNORECASE)
            
            if alt_match:
                ratings_count = int(alt_match.group(1).replace(',', ''))
                reviews_count = int(alt_match.group(2).replace(',', ''))
                return ratings_count, reviews_count
            
            return None, None
            
        except Exception as e:
            self.logger.error(f"Error extracting rating counts: {e}")
            return None, None
    
    def scrape_product_data(self, url, fsn):
        """Scrape product rating data from Flipkart URL"""
        try:
            self.logger.info(f"Scraping data for FSN: {fsn}")
            self.driver.get(url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Wait a bit more for dynamic content
            time.sleep(3)
            
            # First, find the average rating
            self.logger.info("Looking for average rating...")
            avg_rating = self.find_average_rating()
            
            # Then find ratings and reviews count
            rating_text = None
            selectors = [
                "//span[contains(text(), 'ratings') and contains(text(), 'reviews')]",
                "//div[contains(text(), 'ratings') and contains(text(), 'reviews')]",
                "//span[contains(@class, '_2_R_DZ')]",
                "//div[contains(@class, 'row _2afbiS')]",
            ]
            
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        text = element.text.strip()
                        if text and ('rating' in text.lower() and 'review' in text.lower()):
                            rating_text = text
                            self.logger.info(f"Found ratings text with selector '{selector}': {rating_text}")
                            break
                    if rating_text:
                        break
                except Exception as e:
                    continue
            
            ratings_count = None
            reviews_count = None
            
            if rating_text:
                ratings_count, reviews_count = self.extract_rating_counts(rating_text)
            
            # If we still don't have average rating, try one more approach
            if not avg_rating:
                self.logger.info("Trying alternative method to find average rating...")
                avg_rating = self.find_average_rating_alternative()
            
            return {
                'FSN': fsn,
                'Average RATING': avg_rating,
                'RATING': ratings_count,
                'REVIEWS': reviews_count
            }
                
        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return {
                'FSN': fsn,
                'Average RATING': None,
                'RATING': None,
                'REVIEWS': None
            }
    
    def find_average_rating_alternative(self):
        """Alternative method to find average rating"""
        try:
            # Look for the ratings and reviews section specifically
            section_selectors = [
                "//div[contains(text(), 'Ratings & Reviews')]",
                "//span[contains(text(), 'Ratings & Reviews')]",
                "//div[contains(@class, '_3UAT2v')]",
                "//div[contains(@class, '_2s4It8')]",
            ]
            
            for selector in section_selectors:
                try:
                    sections = self.driver.find_elements(By.XPATH, selector)
                    for section in sections:
                        # Look in the section and nearby elements for rating
                        parent = section.find_element(By.XPATH, "./..")
                        parent_text = parent.text
                        rating_match = re.search(r'(\d+\.\d+)', parent_text)
                        if rating_match:
                            self.logger.info(f"Found average rating in section: {rating_match.group(1)}")
                            return float(rating_match.group(1))
                except:
                    continue
            
            return None
        except Exception as e:
            self.logger.error(f"Error in alternative rating search: {e}")
            return None
    
    def save_results(self, results, output_file):
        """Save results to Excel with proper error handling"""
        try:
            # Create output DataFrame
            output_df = pd.DataFrame(results)
            
            # Format Average RATING to 2 decimal places - FIXED
            if 'Average RATING' in output_df.columns:
                output_df['Average RATING'] = output_df['Average RATING'].apply(
                    lambda x: round(float(x), 2) if pd.notna(x) and x != '' and str(x).strip() != '' else x
                )
            
            # Save to Excel
            output_df.to_excel(output_file, index=False)
            self.logger.info(f"Data successfully saved to: {output_file}")
            return output_file, output_df
            
        except Exception as e:
            self.logger.error(f"Error saving to {output_file}: {e}")
            # Try to save with a different name
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                alternative_file = f"D:\\KAPIL\\BIA\\Data scraping\\V\\Scraped_Results_{timestamp}.xlsx"
                output_df = pd.DataFrame(results)
                
                # Format Average RATING to 2 decimal places for alternative file too
                if 'Average RATING' in output_df.columns:
                    output_df['Average RATING'] = output_df['Average RATING'].apply(
                        lambda x: round(float(x), 2) if pd.notna(x) and x != '' and str(x).strip() != '' else x
                    )
                    
                output_df.to_excel(alternative_file, index=False)
                self.logger.info(f"Data saved to alternative location: {alternative_file}")
                return alternative_file, output_df
            except Exception as e2:
                self.logger.error(f"Failed to save to alternative location: {e2}")
                return None, pd.DataFrame(results)
    
    def process_excel_file(self):
        """Main function to process the Excel file and scrape data"""
        try:
            # Read input file with better error handling
            input_file = r"D:\KAPIL\BIA\Data scraping\V\Input.xlsx"
            
            # Check if input file exists
            if not os.path.exists(input_file):
                self.logger.error(f"Input file not found: {input_file}")
                self.logger.info("Please make sure the Input.xlsx file exists in the specified path")
                return None
            
            self.logger.info(f"Reading input file: {input_file}")
            df = pd.read_excel(input_file)
            
            # Check if required columns exist
            if 'FSN' not in df.columns or 'Link' not in df.columns:
                self.logger.error("Input file must contain 'FSN' and 'Link' columns")
                return None
            
            results = []
            total_products = len(df)
            
            # Generate timestamped output filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"D:\\KAPIL\\BIA\\Data scraping\\V\\Output_{timestamp}.xlsx"
            
            for index, row in df.iterrows():
                fsn = row['FSN']
                url = row['Link']
                
                self.logger.info(f"Processing {index + 1}/{total_products}: {fsn}")
                
                # Scrape data
                product_data = self.scrape_product_data(url, fsn)
                results.append(product_data)
                
                # Add delay to be respectful to the server
                time.sleep(3)
            
            # Save results with error handling
            saved_file, output_df = self.save_results(results, output_file)
            
            if saved_file:
                # Print summary
                successful_scrapes = output_df[output_df['RATING'].notna()].shape[0]
                avg_rating_found = output_df[output_df['Average RATING'].notna()].shape[0]
                
                self.logger.info(f"Successfully scraped {successful_scrapes} out of {total_products} products")
                self.logger.info(f"Found average rating for {avg_rating_found} out of {total_products} products")
                self.logger.info(f"Output saved as: {saved_file}")
                
                return output_df
            else:
                self.logger.error("Failed to save results to file")
                return pd.DataFrame(results)
            
        except Exception as e:
            self.logger.error(f"Error processing Excel file: {e}")
            return None
    
    def close(self):
        """Close the browser driver"""
        if self.driver:
            self.driver.quit()

# Main execution
if __name__ == "__main__":
    scraper = FlipkartScraper()
    
    try:
        result_df = scraper.process_excel_file()
        if result_df is not None:
            print("\nScraping completed successfully!")
            print("\nResults:")
            print(result_df)
            
            # Print summary
            successful = result_df[result_df['RATING'].notna()].shape[0]
            avg_found = result_df[result_df['Average RATING'].notna()].shape[0]
            
            print(f"\nSuccessfully scraped: {successful}/{len(result_df)} products")
            print(f"Average rating found: {avg_found}/{len(result_df)} products")
            
            # Also display the actual data
            print("\nDetailed Results:")
            for index, row in result_df.iterrows():
                print(f"FSN: {row['FSN']}")
                print(f"  Average Rating: {row['Average RATING']}")
                print(f"  Ratings Count: {row['RATING']}")
                print(f"  Reviews Count: {row['REVIEWS']}")
                print()
                
        else:
            print("Scraping failed!")
    
    except Exception as e:
        print(f"An error occurred: {e}")
    
    finally:
        scraper.close()