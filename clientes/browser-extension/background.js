chrome.runtime.onInstalled.addListener(() => {
    console.log('Extensión Cerebro instalada/actualizada.');
});

// Listener para peticiones de nuestro popup u otros contextos
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'ingest_url') {
        const targetUrl = request.url;
        
        chrome.storage.sync.get(['tenantId', 'baseUrl'], (items) => {
            const tenantId = items.tenantId;
            const baseUrl = items.baseUrl;

            if (!tenantId || !baseUrl) {
                sendResponse({ error: 'Configuración incompleta.' });
                return;
            }

            const apiEndpoint = `${baseUrl}/webhook/external?tenant_id=${tenantId}`;
            
            // Payload para Ingestion Genérico
            const payload = {
                url: targetUrl
            };

            fetch(apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Inyeccción éxitosa:', data);
                sendResponse({ status: 'success', data: data });
            })
            .catch(err => {
                console.error('Inyeccción fallida:', err);
                sendResponse({ error: err.message });
            });
        });

        // Retornar 'true' habilita la respuesta de la promesa de forma asíncrona para sendResponse
        return true;
    }
});