from fastapi import FastAPI, HTTPException
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from typing import Dict, Tuple, List
import time
import logging
from pydantic import BaseModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('race_extractor.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI()

class RaceDataExtractor:
    def __init__(self, username: str):
        self.username = username
        self.chrome_options = webdriver.ChromeOptions()
        self.chrome_options.add_argument('--start-maximized')
        self.chrome_options.add_argument('--headless')  # Run in headless mode for server
        self.chrome_options.add_argument('--no-sandbox')
        self.chrome_options.add_argument('--disable-dev-shm-usage')
        self.driver = None
        self.base_url = "https://www.racefacer.com/en/profile"
        self.races_data = []
        self.profile_info = {}
        logger.info(f"Initialized RaceDataExtractor for user: {username}")

    def setup_driver(self):
        """Initialize the webdriver and handle cookies"""
        logger.info("Setting up webdriver")
        try:
            self.driver = webdriver.Chrome(options=self.chrome_options)
            self.driver.get(f"{self.base_url}/{self.username}/sessions/")
            self._handle_cookies()
            logger.info("Webdriver setup successful")
        except Exception as e:
            logger.error(f"Error setting up webdriver: {e}")
            raise

    def _handle_cookies(self):
        """Handle cookie popup if present"""
        logger.info("Handling cookies popup")
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "button-close-cookies"))
            ).click()
            logger.info("Cookie popup handled successfully")
        except TimeoutException:
            logger.info("No cookie popup found")
            pass

    def get_session_data(self) -> Tuple[Dict, Dict]:
        """Extract positions and dates for all races"""
        logger.info("Extracting session data")
        positions = {}
        dates = {}

        try:
            sessions = self.driver.find_elements(By.CLASS_NAME, "session-result-container")
            for session in sessions:
                try:
                    race_id = session.get_attribute("data-session-uuid")
                    position = session.find_element(By.CLASS_NAME, "position.inline").text.strip()
                    positions[race_id] = position

                    date_elem = session.find_element(By.CLASS_NAME, "date")
                    date_spans = date_elem.find_elements(By.TAG_NAME, "span")
                    dates[race_id] = (date_spans[0].text.strip(), date_spans[1].text.strip())
                    logger.debug(f"Extracted data for race ID: {race_id}")
                except (NoSuchElementException, IndexError) as e:
                    logger.warning(f"Error extracting individual session data: {e}")
                    continue
        except Exception as e:
            logger.error(f"Error getting session data: {e}")
            raise

        return positions, dates

    def get_profile_info(self):
        """Extract user profile information"""
        logger.info("Extracting profile information")
        try:
            name = self.driver.find_element(By.CLASS_NAME, "username").text.strip()
            location = self.driver.find_element(By.CLASS_NAME, "profile-more-info").find_elements(By.TAG_NAME, "span")[0].text.strip()
            
            logger.info(f"Found profile - Name: {name}, Location: {location}")
            
            self.profile_info["Driver Name"] = name
            self.profile_info["Location"] = location

            stats = {
                'Total Distance': 'total_distance',
                'Total Drive Hours': 'total_time',
                'Preferred Track': 'favorite_track'
            }
            
            self.profile_info["Statistics"] = {}

            for label, class_name in stats.items():
                value = self.driver.find_element(By.CLASS_NAME, class_name).find_element(By.CLASS_NAME, "value").text.strip()
                self.profile_info["Statistics"][label] = value
                logger.debug(f"Extracted stat: {label}: {value}")
                
        except Exception as e:
            logger.error(f"Error getting profile info: {e}")
            raise

    def get_lap_data(self, race_id: str, positions: Dict, dates: Dict):
        """Extract detailed lap data for a specific race"""
        logger.info(f"Extracting lap data for race ID: {race_id}")
        self.driver.get(f"{self.base_url}/{self.username}/sessions/{race_id}/#laps")

        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "table_content.session_content"))
            )

            position = positions.get(race_id, 'Not found')
            date_val, time_val = dates.get(race_id, ('Not found', 'Not found'))

            track_kart = self.driver.find_element(By.CLASS_NAME, "track-kart")
            track = track_kart.find_element(By.CLASS_NAME, 'track-name').text.strip()
            kart = track_kart.find_elements(By.TAG_NAME, 'div')[-1].text.strip()

            lap_times = self._extract_lap_times()

            if lap_times:
                best_time = min(lap_times, key=lambda x: x[1])
                best_time_val = best_time[1]
            else:
                logger.warning(f"No lap times found for race ID: {race_id}")
                best_time_val = "Not found"

            race_info = {
                "race_id": race_id,
                "position": position,
                "date": date_val,
                "time": time_val,
                "track": track,
                "kart": kart,
                "lap_times": lap_times,
                "best_time": best_time_val
            }
            self.races_data.append(race_info)
            logger.info(f"Successfully extracted lap data for race ID: {race_id}")

        except Exception as e:
            logger.error(f"Error getting lap data for race ID {race_id}: {e}")
            raise

    def _extract_lap_times(self) -> List[Tuple[str, str]]:
        """Helper method to extract lap times"""
        logger.info("Extracting lap times")
        lap_times = []
        lap_rows = self.driver.find_elements(By.CSS_SELECTOR, ".tab_laps .row")

        for row in lap_rows:
            try:
                lap_num = row.find_element(By.CLASS_NAME, "lap-name").text
                time_elem = row.find_element(By.CSS_SELECTOR, ".time_laps.first")

                if "pit" not in time_elem.get_attribute("class").lower():
                    lap_time = time_elem.find_element(By.TAG_NAME, "span").text
                    if lap_num and lap_time:
                        lap_times.append((lap_num, lap_time))
                        logger.debug(f"Extracted lap time - Lap {lap_num}: {lap_time}")
            except NoSuchElementException:
                continue

        return lap_times

    def process_races(self) -> Dict:
        """Main method to process all races and return data"""
        logger.info(f"Starting race processing for user: {self.username}")
        try:
            self.setup_driver()
            positions, dates = self.get_session_data()
            self.get_profile_info()

            sessions = self.driver.find_elements(By.CLASS_NAME, "session-result-container")
            race_ids = [s.get_attribute("data-session-uuid") for s in sessions if s.get_attribute("data-session-uuid")]
            
            logger.info(f"Found {len(race_ids)} races")
            self.profile_info["Total Races"] = len(race_ids)

            for race_id in race_ids:
                logger.info(f"Processing race ID: {race_id}")
                self.get_lap_data(race_id, positions, dates)
                time.sleep(2)

            return {
                "profile_info": self.profile_info,
                "races_data": self.races_data
            }

        except Exception as e:
            logger.error(f"Error in process_races: {e}")
            raise
        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Webdriver closed")

@app.get("/race-data/{username}")
async def get_race_data(username: str):
    """API endpoint to get race data for a specific user"""
    logger.info(f"Received request for user: {username}")
    
    try:
        extractor = RaceDataExtractor(username)
        data = extractor.process_races()
        logger.info(f"Successfully processed data for user: {username}")
        return data
    
    except Exception as e:
        logger.error(f"Error processing request for user {username}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)