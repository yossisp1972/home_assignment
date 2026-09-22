from app.services.weather import CITIES
from app.services.agent import detect_city

def test_five_cities():
    assert len(CITIES) == 5
    assert "Rome" in CITIES

def test_detect_city():
    assert detect_city("What is the weather tomorrow in Rome?") == "Rome"
    assert detect_city("Tell me about Mars") is None
