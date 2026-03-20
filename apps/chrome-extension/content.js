/**
 * Shinbee AI Navigator — Content Script
 *
 * Injected into your-domain.com pages. Handles highlight overlays,
 * element scrolling, and click injection.
 */

const HIGHLIGHT_CLASS = 'shinbee-ai-highlight';
const TOOLTIP_CLASS = 'shinbee-ai-tooltip';

/**
 * Remove all existing highlights from the page.
 */
function clearHighlights() {
  document.querySelectorAll(`.${HIGHLIGHT_CLASS}`).forEach((el) => el.remove());
  document.querySelectorAll(`.${TOOLTIP_CLASS}`).forEach((el) => el.remove());
  // Remove highlight outline from elements
  document.querySelectorAll('[data-shinbee-highlighted]').forEach((el) => {
    el.style.removeProperty('outline');
    el.style.removeProperty('outline-offset');
    el.removeAttribute('data-shinbee-highlighted');
  });
}

/**
 * Highlight an element with a pulsing ring and optional label tooltip.
 * @param {string} selector CSS selector for the target element
 * @param {string} label Tooltip text to show
 */
function highlightElement(selector, label) {
  clearHighlights();

  const target = document.querySelector(selector);
  if (!target) {
    console.warn(`[Shinbee AI] Element not found: ${selector}`);
    return;
  }

  // Scroll into view
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });

  // Apply highlight outline
  target.setAttribute('data-shinbee-highlighted', 'true');
  target.style.outline = '3px solid #2563eb';
  target.style.outlineOffset = '4px';

  // Create pulsing ring overlay
  const ring = document.createElement('div');
  ring.className = HIGHLIGHT_CLASS;
  const rect = target.getBoundingClientRect();
  Object.assign(ring.style, {
    position: 'fixed',
    top: `${rect.top - 8}px`,
    left: `${rect.left - 8}px`,
    width: `${rect.width + 16}px`,
    height: `${rect.height + 16}px`,
    border: '3px solid #2563eb',
    borderRadius: '8px',
    pointerEvents: 'none',
    zIndex: '2147483646',
    animation: 'shinbee-pulse 1.5s ease-in-out infinite',
  });
  document.body.appendChild(ring);

  // Create tooltip label
  if (label) {
    const tooltip = document.createElement('div');
    tooltip.className = TOOLTIP_CLASS;
    tooltip.textContent = label;
    Object.assign(tooltip.style, {
      position: 'fixed',
      top: `${rect.top - 40}px`,
      left: `${rect.left}px`,
      background: '#2563eb',
      color: '#fff',
      padding: '4px 12px',
      borderRadius: '6px',
      fontSize: '13px',
      fontWeight: '500',
      zIndex: '2147483647',
      pointerEvents: 'none',
      whiteSpace: 'nowrap',
      boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
    });
    document.body.appendChild(tooltip);
  }

  // Auto-remove after 8 seconds
  setTimeout(clearHighlights, 8000);
}

/**
 * Scroll to an element.
 * @param {string} selector CSS selector
 */
function scrollToElement(selector) {
  const target = document.querySelector(selector);
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
}

/**
 * Click an element.
 * @param {string} selector CSS selector
 */
function clickElement(selector) {
  const target = document.querySelector(selector);
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => target.click(), 500);
  }
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  switch (request.type) {
    case 'highlight':
      highlightElement(request.selector, request.label);
      sendResponse({ ok: true });
      break;

    case 'click':
      clickElement(request.selector);
      sendResponse({ ok: true });
      break;

    case 'scroll':
      scrollToElement(request.selector);
      sendResponse({ ok: true });
      break;

    case 'clear':
      clearHighlights();
      sendResponse({ ok: true });
      break;

    default:
      sendResponse({ ok: false, error: 'Unknown action' });
  }
});
