import type { Theme, EnhanceAppContext } from 'vitepress'
import DefaultTheme from 'vitepress/theme'
import { initLightbox } from './utils/lightboxManager'

// Import lightbox styles
import './css/lightbox.css'

export default {
    ...DefaultTheme,
    enhanceApp(ctx: EnhanceAppContext) {
        DefaultTheme.enhanceApp?.(ctx)

        if (typeof window !== 'undefined') {
            const initAll = () => {
                // Initialize lightbox with a small delay to ensure DOM is ready
                setTimeout(() => {
                    try {
                        initLightbox();
                    } catch (error) {
                        console.error('Error initializing lightbox:', error);
                    }
                }, 100);
            };

            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', initAll);
            } else {
                initAll();
            }

            // Retry initialization after a short time
            setTimeout(() => {
                try {
                    initLightbox();
                } catch (error) {
                    console.error('Error reinitializing lightbox:', error);
                }
            }, 500);

            // Another retry for dynamically loaded content
            setTimeout(() => {
                try {
                    initLightbox();
                } catch (error) {
                    console.error('Error reinitializing lightbox (second attempt):', error);
                }
            }, 1500);

            // Listen for route changes to reinitialize lightbox
            window.addEventListener('vitepress:afterRouteChanged', () => {
                setTimeout(() => {
                    try {
                        initLightbox()
                    } catch (error) {
                        console.error('Error reinitializing lightbox after route change:', error)
                    }
                }, 300)
            })
        }
    }
} satisfies Theme
