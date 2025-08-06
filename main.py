from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from pydantic import BaseModel
import feedparser
import re
import logging
import time

app = FastAPI()

# Allow CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Replace with specific domain(s) in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("travel_deal_sniper.log"),
        logging.StreamHandler()
    ]
)

class UserPreferences(BaseModel):
    departure_airports: List[str]
    destination_keywords: List[str]
    max_price: Optional[float] = None
    currency: Optional[str] = "USD"

class TravelDeal(BaseModel):
    title: str
    link: str
    price: Optional[float] = None
    currency: Optional[str] = None
    departure: Optional[str] = None
    destination: Optional[str] = None

cache = {
    "secret_flying": {"timestamp": 0, "data": []},
    "the_flight_deal": {"timestamp": 0, "data": []}
}
CACHE_TTL = 300

def scrape_secret_flying() -> List[TravelDeal]:
    current_time = time.time()
    if current_time - cache["secret_flying"]["timestamp"] < CACHE_TTL:
        logging.info("Using cached SecretFlying data.")
        return cache["secret_flying"]["data"]

    try:
        url = "https://www.secretflying.com/feed/"
        feed = feedparser.parse(url)
        deals = []

        for entry in feed.entries:
            deal = parse_deal(entry.title, entry.link)
            if deal:
                deals.append(deal)

        cache["secret_flying"] = {"timestamp": current_time, "data": deals}
        logging.info(f"Fetched {len(deals)} deals from SecretFlying.")
        return deals
    except Exception as e:
        logging.error(f"Error scraping SecretFlying: {e}")
        return []

def scrape_the_flight_deal() -> List[TravelDeal]:
    current_time = time.time()
    if current_time - cache["the_flight_deal"]["timestamp"] < CACHE_TTL:
        logging.info("Using cached The Flight Deal data.")
        return cache["the_flight_deal"]["data"]

    try:
        url = "https://feeds.feedburner.com/theflightdeal"
        feed = feedparser.parse(url)
        deals = []

        for entry in feed.entries:
            deal = parse_deal(entry.title, entry.link)
            if deal:
                deals.append(deal)

        cache["the_flight_deal"] = {"timestamp": current_time, "data": deals}
        logging.info(f"Fetched {len(deals)} deals from The Flight Deal.")
        return deals
    except Exception as e:
        logging.error(f"Error scraping The Flight Deal: {e}")
        return []

def parse_deal(title: str, link: str) -> Optional[TravelDeal]:
    try:
        match = re.search(r"([A-Za-z\s]+) to ([A-Za-z,\s]+).*?\$(\d+)", title)
        if match:
            departure = match.group(1).strip()
            destination = match.group(2).strip()
            price = float(match.group(3))

            logging.debug(f"Parsed deal: {title}")
            return TravelDeal(
                title=title,
                link=link,
                price=price,
                currency="USD",
                departure=departure,
                destination=destination
            )
    except Exception as e:
        logging.warning(f"Failed to parse deal title '{title}': {e}")
    return None

def filter_deals(deals: List[TravelDeal], prefs: UserPreferences) -> List[TravelDeal]:
    filtered = []
    for deal in deals:
        if deal.departure and deal.departure not in prefs.departure_airports:
            continue
        if deal.destination and not any(kw.lower() in deal.destination.lower() for kw in prefs.destination_keywords):
            continue
        if prefs.max_price and deal.price and deal.price > prefs.max_price:
            continue
        filtered.append(deal)
    logging.info(f"Filtered {len(filtered)} deals matching user preferences out of {len(deals)} total.")
    return filtered

@app.post("/find-deals", response_model=List[TravelDeal])
def find_deals(prefs: UserPreferences):
    try:
        logging.info(f"Received request with preferences: {prefs}")
        all_deals = scrape_secret_flying() + scrape_the_flight_deal()
        if not all_deals:
            logging.warning("No deals fetched — returning empty list.")
            return []
        matching_deals = filter_deals(all_deals, prefs)
        logging.info(f"Returning {len(matching_deals)} matching deals.")
        return matching_deals
    except Exception as e:
        logging.error(f"Unexpected error in /find-deals: {e}")
        raise HTTPException(status_code=500, detail="Internal server error while finding deals.")
