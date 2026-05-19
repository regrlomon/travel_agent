import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from tools.flight_scraper import scrape_price_calendar, scrape_flight_details


@pytest.mark.asyncio
async def test_price_calendar_returns_date_price_map(mocker):
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    cell1 = MagicMock()
    cell1.get_attribute = AsyncMock(side_effect=lambda attr: "2026-07-01" if attr == "data-date" else "980")
    cell2 = MagicMock()
    cell2.get_attribute = AsyncMock(side_effect=lambda attr: "2026-07-02" if attr == "data-date" else "1200")
    mock_page.query_selector_all = AsyncMock(return_value=[cell1, cell2])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.flight_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)
        result = await scrape_price_calendar("PVG", "DCY", "ctrip")

    assert date(2026, 7, 1) in result
    assert result[date(2026, 7, 1)] == 980


@pytest.mark.asyncio
async def test_scrape_flight_details_returns_flights(mocker):
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_selector = AsyncMock()
    row = MagicMock()
    row.inner_text = AsyncMock(return_value="MU2345\t08:30\t11:00\t¥980")
    mock_page.query_selector_all = AsyncMock(return_value=[row])
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("tools.flight_scraper.async_playwright") as mock_apt:
        mock_apt.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_apt.return_value.__aexit__ = AsyncMock(return_value=False)
        flights = await scrape_flight_details("PVG", "DCY", date(2026, 7, 1), "ctrip")

    assert len(flights) >= 1
