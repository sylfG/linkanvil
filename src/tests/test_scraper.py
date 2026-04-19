import pytest
from unittest.mock import AsyncMock, patch

from src.scraper.strategy import ScraperContext, BasicHttpStrategy, PuppeteerStrategy, AiProxyStrategy

@pytest.mark.asyncio
async def test_scraper_strategy_routing_happy_path():
    """
    F-02.1: Determina si el Patrón Strategy evalúa y enruta correctamente (múltiples orígenes/heurísticas).
    """
    ctx = ScraperContext(default_strategy=AsyncMock(spec=BasicHttpStrategy))
    
    # 1. Rutéo Dinámico por Heurística de Source Explicit (SPA -> Puppeteer)
    strat1 = ctx._determine_strategy(url="https://js-rendered.com", source="js_heavy")
    assert isinstance(strat1, PuppeteerStrategy)

    # 2. Rutéo Dinámico Inspecting URL (Contiene anti-bots -> AI Proxy)
    strat2 = ctx._determine_strategy(url="https://www.cloudflare.com/captcha/page", source="browser")
    assert isinstance(strat2, AiProxyStrategy)

    # 3. Default Strategy para URL cruda plana
    strat3 = ctx._determine_strategy(url="https://regular-blog.com/post/1")
    assert isinstance(strat3, AsyncMock) # Mapeamos al default
    
    # 4. Probar ejecución simulada del context para AiProxy

    with patch("src.scraper.strategy.AiProxyStrategy.extract", new_callable=AsyncMock) as ai_mock:
        ai_mock.return_value = "<html>Contenido interpretado por IA</html>"
        html = await ctx.execute("https://cloudflare.com/captcha/1")
        assert "IA" in html or "Proxy" in html

@patch('src.scraper.strategy.AsyncFetcher.fetch', new_callable=AsyncMock, create=True)
@pytest.mark.asyncio
async def test_scraper_basic_http_successful_extraction(mock_fetch):
    """
    F-02.1 Requisito técnico: Extraer sin bloqueo.
    """
    from unittest.mock import MagicMock
    mock_response = MagicMock()
    mock_response.html = "<html><body>El Texto Extraído</body></html>"
    # BasicHttpStrategy calls page.css('body').get()
    mock_css = MagicMock()
    mock_css.get.return_value = "<body>El Texto Extraído</body>"
    mock_response.css.return_value = mock_css
    
    mock_fetch.return_value = mock_response
    
    basic = BasicHttpStrategy()
    content = await basic.extract("https://foo.com")
    
    assert "El Texto Extraído" in content

@patch('src.scraper.strategy.AsyncFetcher.fetch', new_callable=AsyncMock, create=True)
@patch('src.scraper.strategy.httpx.AsyncClient.get')
@pytest.mark.asyncio
async def test_scraper_fallback_on_crash(mock_get, mock_fetch):
    import httpx
    
    # 1. Fallo en scrapling
    mock_fetch.side_effect = Exception("Fallo interno de Scrapling")
    
    # 2. Timeout en httpx
    mock_get.side_effect = httpx.TimeoutException("Timeout crónico")
    basic = BasicHttpStrategy()
    
    with pytest.raises(httpx.TimeoutException):
        await basic.extract("https://foo.com")