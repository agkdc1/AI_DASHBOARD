/**
 * Shinbee AI Navigator — Background Service Worker
 *
 * Handles communication between popup, content script, and AI backend.
 */

const AI_BASE_URL = 'https://ai.your-domain.com';

/**
 * Capture a screenshot of the active tab.
 * @returns {Promise<string>} Base64-encoded screenshot (without data URI prefix)
 */
async function captureScreenshot() {
  const dataUrl = await chrome.tabs.captureVisibleTab(null, {
    format: 'png',
    quality: 80,
  });
  // Strip "data:image/png;base64," prefix
  return dataUrl.replace(/^data:image\/\w+;base64,/, '');
}

/**
 * Get simplified DOM summary from the content script.
 * @param {number} tabId
 * @returns {Promise<string>}
 */
async function getDomSummary(tabId) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      // Capture a simplified DOM tree (tags, ids, classes, text, hrefs)
      function summarize(el, depth = 0) {
        if (depth > 5) return '';
        const parts = [];
        const tag = el.tagName?.toLowerCase();
        if (!tag || ['script', 'style', 'noscript', 'svg', 'path'].includes(tag)) return '';

        let line = tag;
        if (el.id) line += `#${el.id}`;
        if (el.className && typeof el.className === 'string') {
          const cls = el.className.trim().split(/\s+/).slice(0, 3).join('.');
          if (cls) line += `.${cls}`;
        }
        if (el.href) line += ` href="${el.href}"`;
        if (el.getAttribute?.('role')) line += ` role="${el.getAttribute('role')}"`;
        if (el.getAttribute?.('aria-label')) line += ` aria="${el.getAttribute('aria-label')}"`;

        const text = el.textContent?.trim().slice(0, 80);
        if (text && el.children.length === 0) line += ` "${text}"`;

        parts.push('  '.repeat(depth) + line);

        for (const child of el.children) {
          const childSummary = summarize(child, depth + 1);
          if (childSummary) parts.push(childSummary);
        }
        return parts.join('\n');
      }

      const summary = summarize(document.body);
      // Limit to ~10KB
      return summary.slice(0, 10240);
    },
  });
  return results?.[0]?.result || '';
}

/**
 * Send navigation request to AI backend.
 */
async function sendToAI(message, screenshot, domSummary, currentUrl, history) {
  const resp = await fetch(`${AI_BASE_URL}/assistant/navigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      screenshot_base64: screenshot,
      dom_summary: domSummary,
      current_url: currentUrl,
      conversation_history: history || [],
    }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`AI request failed (${resp.status}): ${text}`);
  }

  return resp.json();
}

/**
 * Execute actions returned by AI on the target tab.
 */
async function executeActions(tabId, actions) {
  for (const action of actions) {
    switch (action.type) {
      case 'navigate':
        if (action.url) {
          // Resolve relative URLs against current tab
          const tab = await chrome.tabs.get(tabId);
          const fullUrl = new URL(action.url, tab.url).href;
          await chrome.tabs.update(tabId, { url: fullUrl });
        }
        break;

      case 'highlight':
        if (action.selector) {
          await chrome.tabs.sendMessage(tabId, {
            type: 'highlight',
            selector: action.selector,
            label: action.label || '',
          });
        }
        break;

      case 'click':
        if (action.selector) {
          await chrome.tabs.sendMessage(tabId, {
            type: 'click',
            selector: action.selector,
          });
        }
        break;

      case 'scroll':
        if (action.selector) {
          await chrome.tabs.sendMessage(tabId, {
            type: 'scroll',
            selector: action.selector,
          });
        }
        break;
    }
  }
}

// Listen for messages from popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.type === 'navigate-query') {
    handleNavigateQuery(request.message, request.history)
      .then(sendResponse)
      .catch((err) => sendResponse({ error: err.message }));
    return true; // async response
  }

  if (request.type === 'clear-highlights') {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]) {
        chrome.tabs.sendMessage(tabs[0].id, { type: 'clear' });
      }
    });
    return false;
  }
});

async function handleNavigateQuery(message, history) {
  // Get active tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error('No active tab');

  // Capture screenshot + DOM in parallel
  const [screenshot, domSummary] = await Promise.all([
    captureScreenshot(),
    getDomSummary(tab.id),
  ]);

  // Send to AI
  const result = await sendToAI(message, screenshot, domSummary, tab.url, history);

  // Execute actions
  if (result.actions?.length > 0) {
    await executeActions(tab.id, result.actions);
  }

  return result;
}
