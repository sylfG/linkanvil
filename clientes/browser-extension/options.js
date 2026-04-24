document.addEventListener('DOMContentLoaded', () => {
    const tenantIdInput = document.getElementById('tenantId');
    const baseUrlInput = document.getElementById('baseUrl');
    const saveBtn = document.getElementById('saveBtn');
    const statusMsg = document.getElementById('status');

    // Cargar config actual de chrome.storage
    chrome.storage.sync.get(['tenantId', 'baseUrl'], (items) => {
        tenantIdInput.value = items.tenantId || '';
        baseUrlInput.value = items.baseUrl || 'http://ingest.localhost';
    });

    // Guardar cambios
    saveBtn.addEventListener('click', () => {
        let tenantId = tenantIdInput.value.trim();
        let baseUrl = baseUrlInput.value.trim();

        if(!tenantId || !baseUrl) {
            alert('Ambos campos son obligatorios');
            return;
        }

        // Limpiar slash final
        if(baseUrl.endsWith('/')) {
            baseUrl = baseUrl.slice(0, -1);
        }

        chrome.storage.sync.set({ tenantId, baseUrl }, () => {
            statusMsg.style.display = 'block';
            setTimeout(() => {
                statusMsg.style.display = 'none';
            }, 2000);
        });
    });
});