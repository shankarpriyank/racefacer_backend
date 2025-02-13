from fastapi import FastAPI, HTTPException
import requests
from bs4 import BeautifulSoup
import json
import logging
import urllib.parse
from typing import Dict, List, Optional

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
        self.username = urllib.parse.quote(username)
        self.base_url = "https://www.racefacer.com/en/profile"
        logger.info(f"Initialized RaceDataExtractor for user: {username}")

    def extract_lap_times(self, session_container) -> List:
        """Extract lap times from session container"""
        lap_times = []
        lap_rows = session_container.select('.tab_laps .table_content .row')
        
        for row in lap_rows:
            lap_name = row.select_one('.lap-name')
            if not lap_name:
                continue
                
            time_element = row.select_one('.time_laps.first')
            if time_element:
                time = time_element.get_text(strip=True)
                lap_times.append([lap_name.text, time])
        
        return lap_times

    def get_profile_data(self) -> Dict:
        """Fetch and parse profile data"""
        logger.info(f"Fetching data for user: {self.username}")
        url = f"{self.base_url}/{self.username}/sessions"
        
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            if not soup.select_one('.username'):
                logger.error("Profile not found")
                raise HTTPException(status_code=404, detail="Profile not found")

            # Extract profile information
            profile_info = {
                "Driver Name": soup.select_one('.username').text.strip(),
                "Location": soup.select_one('.profile-more-info span').text.strip(', '),
                "Statistics": {
                    "Total Distance": soup.select_one('.total_distance .value').text.strip(),
                    "Total Drive Hours": soup.select_one('.total_time .value').text.strip(),
                    "Preferred Track": soup.select_one('.favorite_track .value').text.strip()
                }
            }

            # Extract races data
            races_data = []
            session_containers = soup.select('.session-result-container')
            
            for container in session_containers:
                race = {
                    'race_id': container['data-session-uuid'],
                    'position': container.select_one('.top .position.inline').text.strip(),
                    'date': container.select_one('.minified-stat.date .date').text.strip(),
                    'time': "at " + container.select_one('.minified-stat.date .clock').text.strip(),
                    'track': container.select_one('.minified-stat.track-kart .track-name').text.strip(),
                    'kart': container.select('.minified-stat.track-kart div')[-1].text.strip(),
                    'lap_times': self.extract_lap_times(container),
                    'best_time': container.select_one('.minified-stat.time .minified-stat-value').text.strip()
                }
                races_data.append(race)

            # Add total races count
            profile_info["Total Races"] = len(races_data)

            return {
                "profile_info": profile_info,
                "races_data": races_data
            }

        except requests.RequestException as e:
            logger.error(f"Request failed: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch data: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing data: {str(e)}")
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

@app.get("/race-data/{username}")
async def get_race_data(username: str):
    """API endpoint to get race data for a specific user"""
    logger.info(f"Received request for user: {username}")
    
    try:
        extractor = RaceDataExtractor(username)
        data = extractor.get_profile_data()
        logger.info(f"Successfully processed data for user: {username}")
        return data
    
    except HTTPException as e:
        raise e
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
