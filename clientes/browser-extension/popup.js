document.addEventListener('DOMContentLoaded', () => {
    const btnUrl = document.getElementById('sendBtn');
    const resultDiv = document.getElementById('result');
    const warningMsg = document.getElementById('warning-msg');
    const openSettingsBtn = document.getElementById('openSettings');

    // Comprobar variables, si estan vacías mostrar warning
    chrome.storage.sync.get(['tenantId', 'baseUrl'], (items) => {
        if (!items.tenantId || !items.baseUrl) {
            warningMsg.style.display = 'block';
            btnUrl.disabled = true;
            btnUrl.style.background = '#6c757d';
        }
    });

    openSettingsBtn.addEventListener('click', () => {
        if (chrome.runtime.openOptionsPage) {
            chrome.runtime.openOptionsPage();
        } else {
            window.open(chrome.runtime.getURL('options.html'));
        }
    });

    btnUrl.addEventListener('click', async () => {
        // Deshabilitar botón durante proceso
        btnUrl.disabled = true;
        resultDiv.textContent = 'Enviando...';
        resultDiv.style.color = '#ffc107';

        chrome.tabs.query({active: true, currentWindow: true}, function(tabs) {
            const activeTab = tabs[0];
            const activeUrl = activeTab.url;
            
            // Mandar mensaje al Service Worker de Chromium para hacer el fetch y bypassear CORS puramente front.
            chrome.runtime.sendMessage(
                { action: 'ingest_url', url: activeUrl },
                function(response) {
                    btnUrl.disabled = false;
                    if (response.error) {
                        resultDiv.textContent = '❌ Error: ' + response.error;
                        resultDiv.style.color = '#dc3545';
                    } else if (response.status === 'success') {
                        let resData = response.data;
                        if (resData.status === 'error') {
                            resultDiv.textContent = '❌ Error del servidor.';
                            resultDiv.style.color = '#dc3545';
                        } else {
                            resultDiv.textContent = '✅ Recibido y Encolado';
                            resultDiv.style.color = '#28a745';
                            // Autocierre luego de exito
                            setTimeout(() => {
                                window.close();
                            }, 1500);
                        }
                    } else {
                        resultDiv.textContent = '❌ Respuesta no esperada';
                        resultDiv.style.color = '#dc3545';
                    }
                }
            );
        });
    });
});