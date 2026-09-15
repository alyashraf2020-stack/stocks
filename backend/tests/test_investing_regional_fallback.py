from app.services.data_provider.investing_provider import InvestingHistoricalProvider


def test_regional_historical_urls_prefer_au_and_include_www():
    urls = InvestingHistoricalProvider._regional_historical_urls(
        "https://www.investing.com/equities/taaleem-management-services"
    )
    assert urls[0] == "https://au.investing.com/equities/taaleem-management-services-historical-data"
    assert "https://www.investing.com/equities/taaleem-management-services-historical-data" in urls


def test_parse_exact_historical_session_row():
    html = """
    <table>
      <tr>
        <td>13/09/2026</td><td>18.19</td><td>18.00</td>
        <td>18.29</td><td>17.61</td><td>59.78K</td><td>+1.06%</td>
      </tr>
    </table>
    """
    bar = InvestingHistoricalProvider._parse_historical_session_row(
        html,
        ticker="TALM",
        session_date="2026-09-13",
        host="au.investing.com",
    )
    assert bar is not None
    assert bar["session_date"] == "2026-09-13"
    assert bar["open"] == 18.00
    assert bar["high"] == 18.29
    assert bar["low"] == 17.61
    assert bar["close"] == 18.19
    assert bar["volume"] == 59780.0
    assert "au.investing.com" in bar["actual_provider"]


def test_parser_never_relabels_a_different_session():
    html = """
    <table>
      <tr>
        <td>10/09/2026</td><td>18.00</td><td>18.34</td>
        <td>18.34</td><td>17.95</td><td>1.01M</td><td>-1.10%</td>
      </tr>
    </table>
    """
    bar = InvestingHistoricalProvider._parse_historical_session_row(
        html,
        ticker="TALM",
        session_date="2026-09-13",
        host="au.investing.com",
    )
    assert bar is None
